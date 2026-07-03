"""Home Assistant event bridge.

Connects to HA's WebSocket API, subscribes to ``state_changed``, and republishes the
interesting transitions onto dravix's event bus (e.g. ``ha.motion``, ``presence.detected``,
``ha.door``). Modes like ``guard`` react to those. Reconnects with backoff and never blocks
startup — if HA is unreachable it just keeps retrying in the background.

The mapping logic (``map_state_changed``) is pure and unit-tested; the connection loop is the
only side-effecting part.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

from ..events import EventBus
from ..logging import get_logger

log = get_logger("ha.events")

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
    # The robot's "Local only" switch — republish EVERY real on/off transition (both
    # directions, unlike the became-active events): the user's isLocal choice made ON
    # the robot must flow back into dravix. app.py's watcher applies it.
    if domain == "switch" and (object_id == "local_only" or object_id.endswith("_local_only")):
        if state in ("on", "off") and old.get("state") in ("on", "off") and old.get("state") != state:
            return "islocal.set", {"entity_id": eid, "enabled": state == "on"}

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
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/api/websocket"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + "/api/websocket"
    return base + "/api/websocket"


class HAEventBridge:
    def __init__(
        self,
        ws_url: str,
        token: str,
        bus: EventBus,
        explicit_map: dict[str, str] | None = None,
        reconnect_max: float = 30.0,
    ) -> None:
        self._url = ws_url
        self._token = token
        self._bus = bus
        self._map = explicit_map or {}
        self._reconnect_max = reconnect_max
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="dravix-ha-bridge")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        backoff = 1.0
        while True:
            try:
                await self._session()
                backoff = 1.0  # reset after a clean session
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep retrying
                log.warning("HA event bridge disconnected (%s); retrying in %.0fs", exc, backoff)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(self._reconnect_max, backoff * 2)

    async def _session(self) -> None:
        async with websockets.connect(self._url, max_size=4_000_000) as ws:
            # Auth handshake.
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError(f"unexpected first frame: {hello.get('type')}")
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"auth failed: {auth.get('type')}")
            # Subscribe.
            await ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
            log.info("HA event bridge connected and subscribed")
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") != "event":
                    continue
                data = (msg.get("event") or {}).get("data") or {}
                mapped = map_state_changed(data, self._map)
                if mapped:
                    event_type, payload = mapped
                    await self._bus.publish(event_type, **payload)
                    log.debug("HA -> %s %s", event_type, payload)
