"""Frigate integration — fully local.

Fetches camera snapshots and lists cameras either through Home Assistant's camera proxy
(works for any camera entity, including Frigate's) or directly from a Frigate server on the
LAN. No cloud involved — Frigate and HA both run on the user's own box.
"""
from __future__ import annotations

import httpx

from ..logging import get_logger

log = get_logger("frigate")


class Frigate:
    def __init__(self, ha, base_url: str = "", client: httpx.AsyncClient | None = None) -> None:
        self._ha = ha  # HomeAssistant client (may be None)
        self._base = base_url.rstrip("/")
        self._client = client  # only needed for direct Frigate access

    @property
    def configured(self) -> bool:
        return self._ha is not None or bool(self._base)

    async def cameras(self) -> list[str]:
        """List available camera entity ids from Home Assistant (``camera.*``)."""
        if self._ha is None:
            return []
        states = await self._ha.states()
        return sorted(s["entity_id"] for s in states if s.get("entity_id", "").startswith("camera."))

    async def snapshot(self, camera: str) -> bytes:
        """Return a current JPEG for ``camera``.

        - ``camera.<name>`` → fetched via HA's camera proxy (local).
        - a bare Frigate camera name → fetched from ``<frigate>/api/<name>/latest.jpg`` if a
          direct Frigate base URL is configured.
        """
        if camera.startswith("camera.") and self._ha is not None:
            return await self._ha.camera_snapshot(camera)
        if self._base:
            client = self._client or httpx.AsyncClient(timeout=10.0)
            try:
                r = await client.get(f"{self._base}/api/{camera}/latest.jpg")
                r.raise_for_status()
                return r.content
            finally:
                if self._client is None:
                    await client.aclose()
        if self._ha is not None:
            return await self._ha.camera_snapshot(camera)
        raise RuntimeError("Frigate not configured (need a HomeAssistant client or DRAVIX_FRIGATE_URL)")
