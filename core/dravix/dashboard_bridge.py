"""Push the configured Dashboard URL into the robot's firmware text slot.

The robot's swipe-to 🌐 page shows a live screenshot from this URL (e.g. rendered by the
community "Puppet" HA add-on). The firmware's ``Dashboard URL`` text slot is optimistic and
resets to empty on reboot, so we re-push it on a timer with a diff cache (cleared every
~10 min) — that way a rebooted robot self-heals and the page rejoins its swipe cycle, while
an unchanged URL doesn't spam HA→robot traffic. Same pattern as :mod:`climate_bridge`.
"""
from __future__ import annotations

from .logging import get_logger

log = get_logger("dashboard")

# last value we wrote (per entity id); dropped every ~10 min so a rebooted robot recovers.
_last_pushed: dict[str, str] = {}
_last_forced: float = 0.0


async def push_url(ha, url: str, discovered: dict, *, force: bool = False) -> bool:
    """Write ``url`` into the firmware's Dashboard URL slot (diffed; no-ops when unchanged).

    ``force`` writes even when the value looks unchanged — used on an explicit Save so the
    robot updates immediately even if it rebooted (and reset the slot) since our last push.

    Returns True if the value is on the robot (written now, or already there per the cache),
    False if it couldn't be delivered — no HA / no discovered slot, or the write raised."""
    global _last_forced
    import time as _time

    ent = (discovered or {}).get("dash_url_text")
    if ha is None or not ent:
        return False
    now = _time.monotonic()
    if now - _last_forced > 600:
        _last_pushed.clear()
        _last_forced = now
    value = (url or "").strip()[:255]
    if not force and _last_pushed.get(ent) == value:
        return True  # already on the robot — nothing to write
    try:
        await ha.call_service("text", "set_value", {"entity_id": ent, "value": value})
        _last_pushed[ent] = value
        return True
    except Exception as exc:  # noqa: BLE001 — best effort, never break the push loop
        log.debug("dashboard url push failed: %s", exc)
        return False
