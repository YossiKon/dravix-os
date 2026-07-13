"""The master isLocal flag — one shared "apply" used by every entry point.

isLocal means: EVERYTHING stays inside the home network — nothing goes out and nothing
comes in from outside. It is the USER's explicit on/off choice, persisted, and never
flipped automatically. The user can choose it from any of:

- the dashboard toggle           (PUT /api/config/local_only)
- the robot itself               (the LOCAL button on its status bar → its switch)
- Home Assistant                 (the robot's "Local only" switch entity)

and all of them stay in sync: the dashboard/API path pushes the choice to the robot's
switch; flipping the switch on the robot (or in HA) flows back here through the HA
event bridge (see integrations/ha_events.py + the watcher in app.py).

Applying ON:  cloud AI providers blocked · the cloud MCP bridge disconnected ·
              external (non-LAN) image URLs rejected · release update-checks stopped.
Applying OFF: everything back to normal. Applied live — no restart.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .logging import get_logger

log = get_logger("localmode")

# Serializes concurrent applies (dashboard toggle + the robot switch's echo can land
# almost together) — without it, two OFF applies could both see xiaozhi=None and leak
# a second cloud bridge.
_apply_lock = asyncio.Lock()


async def apply_local_only(s: Any, enabled: bool, *, push_to_robot: bool = True) -> dict:
    """Persist + enforce the user's isLocal choice on app state ``s`` (= app.state).

    ``push_to_robot=False`` when the change CAME from the robot's switch (avoid echo).
    Returns the payload the API responds with; never raises — errors are surfaced in it.
    """
    async with _apply_lock:
        return await _apply(s, enabled, push_to_robot=push_to_robot)


async def _apply(s: Any, enabled: bool, *, push_to_robot: bool) -> dict:
    s.store.set_local_only(enabled)

    # 1 · the cloud MCP bridge follows the choice, live
    bridge_error: str | None = None
    try:
        if enabled and getattr(s, "xiaozhi", None) is not None:
            await s.xiaozhi.stop()
            s.xiaozhi = None
        elif not enabled and getattr(s, "xiaozhi", None) is None and s.settings.xiaozhi_mcp_url:
            from .integrations.xiaozhi_bridge import XiaoZhiBridge
            from .mcpserver.server import build_server

            include_robot = (s.store.robot_driver() or s.settings.robot_driver).lower() != "mock"
            s.xiaozhi = XiaoZhiBridge(
                s.settings.xiaozhi_mcp_url,
                lambda: build_server(
                    s.robot, s.engine, s.ai, ha=s.ha, store=s.store, mood=s.mood,
                    weather_entity=s.settings.weather_entity,
                    include_robot_control=include_robot,
                ),
            )
            await s.xiaozhi.start()
    except Exception as exc:  # noqa: BLE001 — the choice itself was saved; surface the rest
        bridge_error = str(exc)

    # 2 · cloud AI providers are (un)blocked by rebuilding against the new choice
    ai_error: str | None = None
    try:
        from .app import build_ai

        s.ai = build_ai(s.settings, s.store, s.ha)
    except Exception as exc:  # noqa: BLE001
        s.ai = None
        ai_error = str(exc)
    s.runtime.ai_provider = s.store.ai_provider() or s.settings.ai_provider

    # 3 · mirror the choice onto the robot's own "Local only" switch (unless it came
    #     from there) so the LOCAL button on the robot always shows the truth
    if push_to_robot and s.ha is not None:
        eid = (getattr(s, "discovered_entities", None) or {}).get("islocal_switch")
        if eid:
            try:
                await s.ha.call_service(
                    "switch", "turn_on" if enabled else "turn_off", {"entity_id": eid}
                )
            except Exception as exc:  # noqa: BLE001 — robot may be offline; not fatal
                log.debug("couldn't mirror isLocal to the robot switch: %s", exc)

    return {
        "local_only": enabled,
        "ai_available": s.ai is not None,
        "cloud_bridge_connected": getattr(s, "xiaozhi", None) is not None,
        "error": ai_error or bridge_error,
    }
