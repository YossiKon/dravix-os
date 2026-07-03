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

    async def latest_person(
        self,
        camera: str,
        label: str = "person",
        box_format: str = "xywh",
        frame: tuple[int, int] = (320, 240),
    ) -> tuple[float, float] | None:
        """Where is the tracked ``label`` right now, as a normalised centre ``(cx, cy)`` in
        0..1 of the frame — or ``None`` if nothing is currently detected on ``camera``.

        Uses Frigate's events API (``/api/events?...&in_progress=1``), so it needs a DIRECT
        Frigate base URL (Home Assistant's camera proxy has no events endpoint). Polling this
        at ~2 Hz is plenty — the robot's servo bus can't turn faster than that anyway.
        Frigate's ``data.box`` is normally ``[x, y, w, h]``; pass ``box_format='xyxy'`` if
        yours is ``[x1, y1, x2, y2]``. Pixel boxes are auto-normalised via ``frame``.
        """
        if not self._base:
            return None
        client = self._client or httpx.AsyncClient(timeout=5.0)
        try:
            r = await client.get(
                f"{self._base}/api/events",
                params={
                    "camera": camera,
                    "label": label,
                    "in_progress": 1,
                    "limit": 1,
                    "include_thumbnails": 0,
                },
            )
            r.raise_for_status()
            events = r.json()
        except Exception as e:  # noqa: BLE001 — a poll failure just means "no target this tick"
            log.debug("frigate latest_person(%s/%s) failed: %s", camera, label, e)
            return None
        finally:
            if self._client is None:
                await client.aclose()
        if not events:
            return None
        box = (events[0].get("data") or {}).get("box") or events[0].get("box")
        if not box or len(box) < 4:
            return None
        a, b, c, d = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        if max(a, b, c, d) > 1.5:  # pixel coords → normalise to 0..1
            fw, fh = frame
            a, c = a / fw, c / fw
            b, d = b / fh, d / fh
        if box_format == "xyxy":
            cx, cy = (a + c) / 2.0, (b + d) / 2.0
        else:  # xywh (Frigate default): top-left + size
            cx, cy = a + c / 2.0, b + d / 2.0
        return (min(1.0, max(0.0, cx)), min(1.0, max(0.0, cy)))
