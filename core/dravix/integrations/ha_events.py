"""Home Assistant link: ONE websocket that feeds the state mirror, the event bus and writes.

Connects to HA's WebSocket API and keeps one long-lived session that:

- runs ``subscribe_entities`` — the full state set once per connection, then compressed
  diffs — into a :class:`~.ha_state.StateMirror`, so every ``states()`` / ``get_state()`` in
  dravix is a memory read instead of a REST call (the old ``GET /api/states`` dump every few
  seconds made dravix the top source of HA core load);
- republishes the interesting transitions onto dravix's event bus (``ha.motion``,
  ``presence.detected``, ``ha.door``, the robot's touch / isLocal / privacy switches) —
  derived from the mirror's merged old/new states, so a diff that only carries the changed
  fields still maps correctly. (This replaces the old ``subscribe_events state_changed``,
  which streamed every change in the house as full old+new state objects.);
- subscribes to the robot's own ``esphome.dravix_*`` events (card taps, climate buttons,
  Approve/Reject);
- carries ``call_service`` writes (pipelined on the same socket — no HTTP request each).

Reconnects with backoff and never blocks startup. The mapping logic (``map_state_changed``)
is pure and unit-tested; the session loop is the only side-effecting part.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

from ..events import EventBus
from ..logging import get_logger
from .ha_state import StateMirror

log = get_logger("ha.events")


class HALinkDown(ConnectionError):
    """The websocket isn't connected — the caller may fall back to REST (nothing was sent)."""


class HAServiceError(RuntimeError):
    """Home Assistant answered a websocket ``call_service`` with ``success: false``."""

# States that count as "activated" for a sensor/binary_sensor.
ACTIVE_STATES = {"on", "open", "home", "detected", "True", "true"}

# "Not touched" states for the StackChan capacitive touch text-sensors.
_NO_TOUCH = {"No touch", "none", "off", "0", "unknown", "unavailable", ""}

# device_class -> event type for binary_sensors (when not explicitly mapped).
_DEVICE_CLASS_EVENT = {
    "motion": "ha.motion",
    "occupancy": "presence.detected",
    "presence": "presence.detected",
    "door": "ha.door",
    "window": "ha.door",
    "opening": "ha.door",
    "garage_door": "ha.door",
}


def map_state_changed(
    data: dict[str, Any], explicit_map: dict[str, str] | None = None
) -> tuple[str, dict[str, Any]] | None:
    """Map a HA ``state_changed`` event payload to ``(event_type, payload)`` or ``None``.

    - Explicit map (entity_id -> event_type) wins; fires on transition into an active state.
    - Otherwise, ``binary_sensor`` entities turning on map by ``device_class``.
    """
    explicit_map = explicit_map or {}
    eid = data.get("entity_id", "")
    new = data.get("new_state") or {}
    old = data.get("old_state") or {}
    state = new.get("state")
    if state is None:
        return None  # entity removed
    became_active = state in ACTIVE_STATES and (old.get("state") not in ACTIVE_STATES)

    if eid in explicit_map:
        if became_active:
            return explicit_map[eid], {"entity_id": eid, "state": state}
        return None

    domain, _, object_id = eid.partition(".")
    # Someone arrived home — the welcome mode celebrates. Fires only on a REAL
    # transition into "home" (not on restart/unknown noise).
    if domain == "person" and state == "home" and old.get("state") not in (None, "home", "unknown", "unavailable"):
        return "presence.home", {"entity_id": eid, "person": object_id}

    # The robot's "Local only" switch — republish EVERY real on/off transition (both
    # directions, unlike the became-active events): the user's isLocal choice made ON
    # the robot must flow back into dravix. app.py's watcher applies it.
    if domain == "switch" and (object_id == "local_only" or object_id.endswith("_local_only")):
        if state in ("on", "off") and old.get("state") in ("on", "off") and old.get("state") != state:
            return "islocal.set", {"entity_id": eid, "enabled": state == "on"}

    # The robot's "Privacy mode" switch — same both-direction republish. app.py's watcher
    # detaches/re-attaches the camera at the HA level, no matter WHERE the flip came from
    # (robot screen, HA UI, or the dashboard).
    if domain == "switch" and (object_id == "privacy_mode" or object_id.endswith("_privacy_mode")):
        if state in ("on", "off") and old.get("state") in ("on", "off") and old.get("state") != state:
            return "privacy.set", {"entity_id": eid, "private": state == "on"}

    if domain == "binary_sensor" and became_active:
        device_class = (new.get("attributes") or {}).get("device_class")
        event_type = _DEVICE_CLASS_EVENT.get(device_class or "")
        if event_type:
            return event_type, {"entity_id": eid, "device_class": device_class}
        # The robot's dedicated touch zone → treat as a pet (the mood engine loves it).
        # Deliberately narrow ("touch_sensor" in the object_id) — a loose "head"/"touch"
        # substring also matched things like binary_sensor.bathroom_overhead_motion.
        if "touch_sensor" in object_id:
            return "touch.pet", {"entity_id": eid}

    # StackChan capacitive touch zones are *text* sensors: "No touch" -> "LOW"/"MEDIUM"/"HIGH".
    # Fire a pet when one transitions from no-touch to touched.
    if domain == "sensor" and "touch_sensor" in object_id:
        if state not in _NO_TOUCH and (old.get("state") in _NO_TOUCH):
            return "touch.pet", {"entity_id": eid, "state": state}
    return None


def ha_ws_url(base_url: str) -> str:
    """HA's websocket URL for a REST base URL.

    A direct HA URL (``http://homeassistant:8123``) serves it at ``/api/websocket``. The
    add-on's zero-config path goes through the Supervisor proxy (``http://supervisor/core``),
    whose REST API lives under ``/core/api/…`` but whose websocket is documented at
    ``/core/websocket`` — so a ``…/core`` base maps there (see :func:`ws_url_candidates` for
    the fallback)."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    if base.endswith("/core"):
        return base + "/websocket"
    return base + "/api/websocket"


def ws_url_candidates(ws_url: str) -> list[str]:
    """The URL to try first, plus the Supervisor proxy's other websocket path (it has
    served both ``/core/websocket`` and ``/core/api/websocket``) — tried once when the
    first handshake fails, so one wrong guess can't leave the mirror dark forever."""
    out = [ws_url]
    if ws_url.endswith("/core/websocket"):
        out.append(ws_url[: -len("/websocket")] + "/api/websocket")
    elif ws_url.endswith("/core/api/websocket"):
        out.append(ws_url[: -len("/api/websocket")] + "/websocket")
    return out


# The robot's own HA events (fired by the dravix firmware) → dravix bus events.
_ESPHOME_EVENTS = ("esphome.dravix_card", "esphome.dravix_climate", "esphome.dravix_permission")


class HAEventBridge:
    """The one long-lived websocket to Home Assistant (state mirror + events + writes)."""

    def __init__(
        self,
        ws_url: str,
        token: str,
        bus: EventBus | None,
        explicit_map: dict[str, str] | None = None,
        reconnect_max: float = 30.0,
        *,
        mirror: StateMirror | None = None,
        publish_events: bool = True,
    ) -> None:
        self._urls = ws_url_candidates(ws_url)
        self._url_idx = 0
        self._token = token
        self._bus = bus
        self._map = explicit_map or {}
        self._reconnect_max = reconnect_max
        self._publish = publish_events and bus is not None
        self._task: asyncio.Task | None = None
        self.mirror = mirror or StateMirror()
        self.connected = False
        self.last_error = ""
        self._ws: Any = None
        self._next_id = 1
        self._results: dict[int, asyncio.Future] = {}
        self._entities_sub: int | None = None
        self._outage_logged = False
        self._session_synced = False  # did THIS session deliver its snapshot?

    @property
    def url(self) -> str:
        return self._urls[self._url_idx]

    def status(self) -> dict[str, Any]:
        """For /api/status: is the link up, is the mirror trustworthy, how big is it."""
        return {
            "connected": self.connected,
            "synced": self.mirror.synced,
            "entities": len(self.mirror),
            "resyncs": self.mirror.resyncs,
            "url": self.url,
            "last_error": self.last_error,
        }

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="dravix-ha-bridge")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # the cancelled session never reached its own clean-up: fail in-flight commands
        # and stop readers trusting a frozen mirror during the rest of shutdown
        self._drop_session()

    # ── commands over the live socket ────────────────────────────────────────────
    async def command(self, message: dict[str, Any], timeout: float = 15.0) -> Any:
        """Send one websocket command and return its ``result``. Raises :class:`HALinkDown`
        when nothing could be sent (safe to retry over REST), :class:`HAServiceError` when HA
        answered ``success: false``, and ``ConnectionError`` / ``TimeoutError`` when the fate
        of a SENT command is unknown (never resend those — the write may have happened)."""
        ws = self._ws
        if ws is None or not self.connected:
            raise HALinkDown("HA websocket not connected")
        msg_id = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._results[msg_id] = fut
        try:
            try:
                await ws.send(json.dumps({"id": msg_id, **message}))
            except Exception as exc:  # noqa: BLE001 — the socket died under us; nothing was sent
                raise HALinkDown(str(exc)) from exc
            resp = await asyncio.wait_for(fut, timeout)
        finally:
            self._results.pop(msg_id, None)
        if not resp.get("success"):
            err = resp.get("error") or {}
            raise HAServiceError(f"{err.get('code', 'error')}: {err.get('message', '')}".strip())
        return resp.get("result")

    async def call_service(self, domain: str, service: str, data: dict[str, Any] | None = None) -> Any:
        return await self.command({
            "type": "call_service", "domain": domain, "service": service, "service_data": data or {},
        })

    # ── session loop ─────────────────────────────────────────────────────────────
    async def _run(self) -> None:
        backoff = 1.0
        while True:
            authed = False
            self._session_synced = False
            try:
                authed = await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep retrying
                self.last_error = f"{type(exc).__name__}: {exc}"
                authed = authed or self.connected
            if self._session_synced:
                backoff = 1.0  # a session that really worked ended — reconnect promptly
            # (a socket that authenticates and closes before the snapshot — the Supervisor
            # does that while its own link to core is down — keeps backing off instead of
            # reconnecting every second and re-requesting the full snapshot each time)
            self._drop_session()
            if not authed and len(self._urls) > 1:
                self._url_idx = (self._url_idx + 1) % len(self._urls)  # try the other proxy path
            # ONE warning per outage (the old bridge logged one per retry, forever)
            if not self._outage_logged:
                log.warning("Home Assistant websocket lost (%s) — reads fall back to per-entity "
                            "REST until it is back; retrying (next: %s)", self.last_error or "closed", self.url)
                self._outage_logged = True
            else:
                log.debug("HA websocket retry in %.0fs (%s)", backoff, self.last_error)
            await asyncio.sleep(backoff)
            backoff = min(self._reconnect_max, backoff * 2)

    def _drop_session(self) -> None:
        self.connected = False
        self._ws = None
        self.mirror.mark_stale()
        for fut in self._results.values():
            if not fut.done():
                fut.set_exception(ConnectionError("HA websocket closed before Home Assistant answered"))
        self._results.clear()

    async def _session(self) -> bool:
        # max_size=None: the first subscribe_entities frame carries EVERY entity in one
        # message (several MB on a big install) — a size cap would close the socket (1009)
        # and loop in backoff forever. The peer is the local HA, trusted.
        async with websockets.connect(self.url, max_size=None) as ws:
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError(f"unexpected first frame: {hello.get('type')}")
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"auth failed: {auth.get('type')}")
            self._ws = ws
            self._next_id = 1
            self.mirror.begin_sync()
            self._entities_sub = self._next_id
            self._next_id += 1
            await ws.send(json.dumps({"id": self._entities_sub, "type": "subscribe_entities"}))
            event_subs: dict[int, str] = {}
            for event_type in _ESPHOME_EVENTS:
                event_subs[self._next_id] = event_type
                await ws.send(json.dumps({"id": self._next_id, "type": "subscribe_events", "event_type": event_type}))
                self._next_id += 1
            self.connected = True
            log.info("HA link connected (%s) — waiting for the state snapshot", self.url)
            async for raw in ws:
                # One malformed frame must not unwind the whole session — a session drop
                # loses events during the reconnect backoff.
                try:
                    parsed = json.loads(raw)
                    for msg in parsed if isinstance(parsed, list) else (parsed,):
                        await self._dispatch(msg, event_subs)
                except asyncio.CancelledError:
                    raise
                except _SubscriptionRefused:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.debug("HA link: bad frame skipped (%s)", exc)
        return True

    async def _dispatch(self, msg: dict[str, Any], event_subs: dict[int, str]) -> None:
        kind = msg.get("type")
        msg_id = msg.get("id")
        if kind == "result":
            fut = self._results.get(msg_id)
            if fut is not None and not fut.done():
                fut.set_result(msg)
            elif msg_id == self._entities_sub and not msg.get("success"):
                raise _SubscriptionRefused(str(msg.get("error")))
            return
        if kind != "event":
            return
        event = msg.get("event") or {}
        if msg_id == self._entities_sub:
            was_synced = self.mirror.synced
            changes = self.mirror.apply(event)
            if not was_synced and self.mirror.synced:
                self._on_synced()
            if self._publish:
                for eid, old, new in changes:
                    mapped = map_state_changed(
                        {"entity_id": eid, "old_state": old, "new_state": new}, self._map
                    )
                    if mapped:
                        event_type, payload = mapped
                        await self._bus.publish(event_type, **payload)  # type: ignore[union-attr]
                        log.debug("HA -> %s %s", event_type, payload)
            return
        if not self._publish or msg_id not in event_subs:
            return
        data = event.get("data") or {}
        etype = event.get("event_type") or event_subs[msg_id]
        bus = self._bus
        assert bus is not None
        if etype == "esphome.dravix_card":
            # A tap on one of the robot's card rows → dravix performs the action.
            await bus.publish("card.tap", card=int(data.get("card") or 0), row=int(data.get("row") or 0))
        elif etype == "esphome.dravix_climate":
            # A tap on the robot's CLIMATE page → dravix controls the configured AC.
            await bus.publish("climate.control", action=str(data.get("action") or ""))
        elif etype == "esphome.dravix_permission":
            # A tap on the robot's Approve/Reject buttons → resolve the pending permission.
            await bus.publish("agent.permission_decision", decision=str(data.get("decision") or ""))


    def _on_synced(self) -> None:
        """The snapshot of a fresh session arrived — only NOW is the link really back."""
        self._session_synced = True
        self.last_error = ""
        if self._outage_logged:
            log.warning("Home Assistant websocket back (%s, %d entities)", self.url, len(self.mirror))
        else:
            log.info("HA state mirror synced (%d entities)", len(self.mirror))
        self._outage_logged = False


class _SubscriptionRefused(RuntimeError):
    """HA refused subscribe_entities — end the session (and retry) instead of running blind."""


