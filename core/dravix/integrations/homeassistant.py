"""Home Assistant client (states, services, conversation/Assist).

Used by the AI router (Assist), the HA robot driver, and modes that react to HA events.

In the add-on, :meth:`attach_link` connects this client to the one long-lived websocket
(:class:`~.ha_events.HAEventBridge`). From then on:

- ``states()`` / ``get_state()`` read the in-memory state mirror — no REST at all. While the
  mirror isn't synced (HA restarting), ``get_state()`` falls back to ONE cached
  ``GET /api/states/<entity_id>`` and ``states()`` waits briefly or fails — the full
  ``GET /api/states`` dump is never used (it serialised ~3,000 entities per call and made
  dravix the top source of HA core load);
- ``call_service()`` goes through the write gate (:mod:`.ha_writes`: no writes to
  unavailable entities, only on change, ≤1/s per entity, backoff) and travels over the
  websocket, falling back to REST only when the socket is down.

Without a link (the standalone ``python -m dravix.mcpserver``) it is the plain REST client
it always was.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import httpx

from ..logging import get_logger
from .ha_writes import MISSING, WriteGate

if TYPE_CHECKING:
    from .ha_events import HAEventBridge

log = get_logger("ha")

_REST_TTL_S = 2.0          # a fallback GET answers every reader for this long
_REST_UNAVAILABLE_MAX_S = 60.0


class HAStatesUnavailable(RuntimeError):
    """The state mirror isn't synced and the full REST dump is deliberately not used."""


class HAEntityNotFound(LookupError):
    """Home Assistant has no such entity (the mirror's answer to a REST 404)."""


class HomeAssistant:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        self.link: HAEventBridge | None = None
        self.writes: WriteGate | None = None
        # per-entity fallback cache while the mirror is down: eid → (expires, state|None, backoff)
        self._rest_cache: dict[str, tuple[float, dict | None, float]] = {}
        self._rest_inflight: dict[str, asyncio.Future] = {}

    def attach_link(self, link: "HAEventBridge") -> None:
        """Serve reads from ``link``'s state mirror and gate every write (the add-on path)."""
        self.link = link
        self.writes = WriteGate(self._send, self._lookup_for_gate)
        link.mirror.add_listener(self.writes.on_state)
        link.mirror.add_resync_listener(self.writes.on_resync)
        # an outage's REST answers (and their unavailable-backoff) must not outlive it
        link.mirror.add_resync_listener(self._rest_cache.clear)

    @property
    def mirror_synced(self) -> bool:
        return self.link is not None and self.link.mirror.synced

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._token)

    async def close(self) -> None:
        if self.writes is not None:
            self.writes.close()
        await self._client.aclose()

    async def ping(self) -> bool:
        """Return True if the API is reachable and the token is valid."""
        try:
            r = await self._client.get("/api/")
            return r.status_code == 200
        except httpx.HTTPError as exc:
            log.warning("HA ping failed: %s", exc)
            return False

    async def core_config(self) -> dict[str, Any]:
        """HA's /api/config — version, location, internal/external URLs."""
        r = await self._client.get("/api/config")
        r.raise_for_status()
        return r.json()

    async def states(self) -> list[dict[str, Any]]:
        """Every entity's state. From the mirror when linked (waits up to 10 s for a sync,
        then raises :class:`HAStatesUnavailable` — callers already treat a failed fetch as
        "try again next tick"); plain REST only for the unlinked standalone client."""
        if self.link is not None:
            if not await self.link.mirror.wait_ready(10.0):
                raise HAStatesUnavailable("Home Assistant websocket not synced yet")
            return self.link.mirror.all()
        r = await self._client.get("/api/states")
        r.raise_for_status()
        return r.json()

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """One entity's state — a mirror lookup when synced, else one cached REST GET."""
        if self.link is not None and self.link.mirror.synced:
            st = self.link.mirror.get(entity_id)
            if st is None:
                raise HAEntityNotFound(entity_id)
            return st
        if self.link is None:
            r = await self._client.get(f"/api/states/{entity_id}")
            r.raise_for_status()
            return r.json()
        st = await self._get_state_cached(entity_id)
        if st is None:
            raise HAEntityNotFound(entity_id)
        return st

    async def _get_state_cached(self, entity_id: str) -> dict[str, Any] | None:
        """The mirror is down: ONE ``GET /api/states/<entity_id>``, shared by every reader for
        ``_REST_TTL_S``; an entity reported unavailable is re-checked with exponential
        backoff (2 s → 60 s) instead of on every read. None = HA has no such entity."""
        now = time.monotonic()
        hit = self._rest_cache.get(entity_id)
        if hit is not None and now < hit[0]:
            return hit[1]
        inflight = self._rest_inflight.get(entity_id)
        if inflight is not None:  # another reader is already asking — share its answer
            return await asyncio.shield(inflight)
        task = asyncio.ensure_future(self._fetch_state(entity_id, hit))
        self._rest_inflight[entity_id] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                self._rest_inflight.pop(entity_id, None)
            else:
                task.add_done_callback(lambda _t: self._rest_inflight.pop(entity_id, None))

    async def _fetch_state(self, entity_id: str, hit: tuple | None) -> dict[str, Any] | None:
        now = time.monotonic()
        r = await self._client.get(f"/api/states/{entity_id}")
        if r.status_code == 404:
            self._rest_cache[entity_id] = (now + _REST_TTL_S, None, 0.0)
            return None
        r.raise_for_status()
        st = r.json()
        backoff = 0.0
        ttl = _REST_TTL_S
        if isinstance(st, dict) and st.get("state") == "unavailable":
            prev = hit[2] if hit is not None else 0.0
            backoff = min(_REST_UNAVAILABLE_MAX_S, max(_REST_TTL_S, prev * 2))
            ttl = backoff
        self._rest_cache[entity_id] = (now + ttl, st, backoff)
        return st

    async def _lookup_for_gate(self, entity_id: str) -> Any:
        """The gate's view of a target: state dict, MISSING (no such entity), or None
        (can't tell — the write goes through, as it always did)."""
        try:
            return await self.get_state(entity_id)
        except HAEntityNotFound:
            return MISSING
        except Exception:  # noqa: BLE001 — HA unreachable: don't block on a guess
            return None

    async def history(self, entity_ids: list[str], hours: int = 24) -> list[list[dict[str, Any]]]:
        """Recorder history for a few entities: one list per entity of ``{entity_id, state,
        last_changed}`` rows (minimal response — no attributes). What HA has been quietly
        recording all along; the robot's reboot log lives here before dravix ever ran."""
        import datetime as _dt

        start = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        r = await self._client.get(
            f"/api/history/period/{start}",
            params={"filter_entity_id": ",".join(entity_ids), "minimal_response": "", "no_attributes": ""},
        )
        r.raise_for_status()
        return r.json()

    async def call_service(
        self, domain: str, service: str, data: dict[str, Any] | None = None
    ) -> Any:
        if self.writes is not None:
            return await self.writes.call(domain, service, data or {})
        return await self._send(domain, service, data or {})

    async def call_service_many(self, calls: list[tuple[str, str, dict[str, Any]]]) -> list[Any]:
        """Several writes as one batch (gated individually, sent together). Results — or
        the exception a write raised — in order."""
        if self.writes is not None:
            return await self.writes.call_many(calls)
        out: list[Any] = []
        for domain, service, data in calls:
            try:
                out.append(await self._send(domain, service, data))
            except Exception as exc:  # noqa: BLE001 — reported in the list, like gather()
                out.append(exc)
        return out

    async def _send(self, domain: str, service: str, data: dict[str, Any]) -> Any:
        """Deliver one service call: over the websocket when it is up, else REST."""
        if self.link is not None:
            from .ha_events import HALinkDown

            try:
                return await self.link.call_service(domain, service, data)
            except HALinkDown:
                pass  # nothing was sent — REST is safe
        r = await self._client.post(f"/api/services/{domain}/{service}", json=data)
        r.raise_for_status()
        return r.json()

    async def _ws_command(self, message: dict[str, Any]) -> Any:
        """An ADMIN call over HA's WebSocket API — for registry operations the REST API
        can't do. Rides the live link when there is one; otherwise opens, authenticates,
        sends, returns the result, closes (trying the Supervisor's other websocket path
        if the first one refuses)."""
        if self.link is not None:
            from .ha_events import HALinkDown

            try:
                return await self.link.command(message)
            except HALinkDown:
                pass
        from .ha_events import ha_ws_url, ws_url_candidates

        last: Exception | None = None
        for url in ws_url_candidates(ha_ws_url(self.base_url)):
            try:
                return await self._ws_oneshot(url, message)
            except RuntimeError:
                raise  # HA answered (auth/command error) — the URL was right
            except Exception as exc:  # noqa: BLE001 — handshake failed: try the other path
                last = exc
        assert last is not None
        raise last

    async def _ws_oneshot(self, url: str, message: dict[str, Any]) -> Any:
        import json

        import websockets

        async with websockets.connect(url, max_size=None) as ws:
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError(f"unexpected first frame: {hello.get('type')}")
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"HA websocket auth failed: {auth.get('type')}")
            await ws.send(json.dumps({"id": 1, **message}))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == 1 and resp.get("type") == "result":
                    if not resp.get("success"):
                        raise RuntimeError(str(resp.get("error")))
                    return resp.get("result")

    async def set_entity_enabled(self, entity_id: str, enabled: bool) -> None:
        """Enable/disable an entity in HA's registry (dravix's privacy mode uses this to
        REALLY detach the robot's camera — a disabled entity is removed from HA at once,
        so nothing can snapshot or stream it). Re-enabling reloads the entity's
        integration so it comes back without a restart."""
        await self._ws_command({
            "type": "config/entity_registry/update",
            "entity_id": entity_id,
            "disabled_by": None if enabled else "user",
        })
        if enabled:
            # a re-enabled entity only returns after its config entry reloads
            try:
                await self.call_service(
                    "homeassistant", "reload_config_entry", {"entity_id": entity_id}
                )
            except Exception as exc:  # noqa: BLE001 — worst case it appears after a restart
                log.warning("config-entry reload for %s failed: %s", entity_id, exc)

    async def camera_snapshot(self, entity_id: str) -> bytes:
        """Fetch the current JPEG frame for a camera entity via HA's camera proxy (local)."""
        r = await self._client.get(f"/api/camera_proxy/{entity_id}")
        r.raise_for_status()
        return r.content

    async def conversation(
        self, text: str, agent_id: str | None = None, conversation_id: str | None = None
    ) -> dict[str, Any]:
        """Send text through HA's Assist conversation pipeline."""
        payload: dict[str, Any] = {"text": text}
        if agent_id:
            payload["agent_id"] = agent_id
        if conversation_id:
            payload["conversation_id"] = conversation_id
        r = await self._client.post("/api/conversation/process", json=payload)
        r.raise_for_status()
        return r.json()
