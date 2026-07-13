"""Minimal Home Assistant REST client (states, services, conversation/Assist).

Used by the AI router (Assist), the HA robot driver, and modes that react to HA events.
WebSocket event streaming is added in a later phase.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging import get_logger

log = get_logger("ha")


class HomeAssistant:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._token)

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        """Return True if the API is reachable and the token is valid."""
        try:
            r = await self._client.get("/api/")
            return r.status_code == 200
        except httpx.HTTPError as exc:
            log.warning("HA ping failed: %s", exc)
            return False

    async def states(self) -> list[dict[str, Any]]:
        r = await self._client.get("/api/states")
        r.raise_for_status()
        return r.json()

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        r = await self._client.get(f"/api/states/{entity_id}")
        r.raise_for_status()
        return r.json()

    async def call_service(
        self, domain: str, service: str, data: dict[str, Any] | None = None
    ) -> Any:
        r = await self._client.post(f"/api/services/{domain}/{service}", json=data or {})
        r.raise_for_status()
        return r.json()

    async def _ws_command(self, message: dict[str, Any]) -> Any:
        """A one-shot ADMIN call over HA's WebSocket API — for registry operations the
        REST API can't do. Opens, authenticates, sends, returns the result, closes."""
        import json

        import websockets

        from .ha_events import ha_ws_url

        url = ha_ws_url(self.base_url)
        async with websockets.connect(url, max_size=1_000_000) as ws:
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
