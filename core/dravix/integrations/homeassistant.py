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
