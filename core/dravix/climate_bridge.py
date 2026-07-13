"""The robot's on-screen CLIMATE page ⇄ the configured AC.

The robot's swipe-to CLIMATE page shows the AC you picked in the dashboard's Climate tab
(store ``climate_entity``) and its buttons fire ``esphome.dravix_climate`` events. This
bridges both ways:

- ``push_status`` writes the AC's live state into the firmware's climate text slots
  (name / big target / info line), refreshed on a timer;
- ``handle_control`` performs the matching Home Assistant service call for a tapped
  button (temperature ±, HVAC mode, on/off, fan-speed cycle).

Everything is capability-/support-guarded and best-effort — a missing AC, an unsupported
mode, or an offline robot just no-ops with a debug log.
"""
from __future__ import annotations

from .logging import get_logger

log = get_logger("climate")

# HVAC modes the mode buttons can request (validated against the AC's hvac_modes).
_MODE_ACTIONS = {"cool", "heat", "fan_only", "dry", "auto", "off", "heat_cool"}


def _fmt_temp(v) -> str:
    try:
        return f"{float(v):.0f}°"
    except (TypeError, ValueError):
        return "--°"


# last values we wrote per slot — push_status runs every 5s and unconditional writes were
# constant HA→robot traffic (and recorder DB growth) even while nothing changed. The cache
# is dropped every ~10 min so a rebooted robot (whose optimistic slots reset) self-heals.
_last_pushed: dict[str, str] = {}
_last_forced: float = 0.0


async def _set_text(ha, entity_id: str, value: str) -> None:
    if _last_pushed.get(entity_id) == value:
        return
    await ha.call_service("text", "set_value", {"entity_id": entity_id, "value": value})
    _last_pushed[entity_id] = value


async def push_status(ha, entity: str, discovered: dict) -> None:
    """Write the configured AC's live state into the climate name/set/info text slots
    (diffed — only slots whose value actually changed are written)."""
    global _last_forced
    import time as _time

    now = _time.monotonic()
    if now - _last_forced > 600:
        _last_pushed.clear()
        _last_forced = now
    name_e = (discovered or {}).get("climate_name_text")
    set_e = (discovered or {}).get("climate_set_text")
    info_e = (discovered or {}).get("climate_info_text")
    if ha is None or not (name_e and set_e and info_e):
        return
    if not entity:
        # no AC configured → tell the page so (the diff makes this a true write-once)
        try:
            await _set_text(ha, name_e, "")
            await _set_text(ha, set_e, "--°")
            await _set_text(ha, info_e, "")
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        st = await ha.get_state(entity)
    except Exception as exc:  # noqa: BLE001
        log.debug("climate push: %s", exc)
        return
    attrs = st.get("attributes") or {}
    from .bidi import for_robot  # Hebrew AC names → visual order (the robot's LVGL has no BiDi)

    name = str(attrs.get("friendly_name") or entity)[:24]
    mode = str(st.get("state") or "")
    info = f"now {_fmt_temp(attrs.get('current_temperature'))}   {mode}"
    fan = attrs.get("fan_mode")
    if fan:
        info += f"   fan: {fan}"
    big = "off" if mode in ("off", "") else _fmt_temp(attrs.get("temperature"))
    try:
        await _set_text(ha, name_e, for_robot(name))
        await _set_text(ha, set_e, big)
        await _set_text(ha, info_e, for_robot(info[:60]))
    except Exception as exc:  # noqa: BLE001
        log.debug("climate push write: %s", exc)


async def handle_control(ha, entity: str, action: str) -> None:
    """Perform the HA service call for a tapped climate button."""
    if ha is None or not entity:
        return
    try:
        attrs = (await ha.get_state(entity)).get("attributes") or {}
        if action in ("temp_up", "temp_down"):
            target = attrs.get("temperature")
            if target is None:
                return
            step = float(attrs.get("target_temp_step") or 1.0)
            new = float(target) + (step if action == "temp_up" else -step)
            lo, hi = attrs.get("min_temp"), attrs.get("max_temp")
            if lo is not None:
                new = max(float(lo), new)
            if hi is not None:
                new = min(float(hi), new)
            await ha.call_service(
                "climate", "set_temperature", {"entity_id": entity, "temperature": new}
            )
        elif action == "fan_cycle":
            modes = attrs.get("fan_modes") or []
            if modes:
                cur = attrs.get("fan_mode")
                i = (modes.index(cur) + 1) % len(modes) if cur in modes else 0
                await ha.call_service(
                    "climate", "set_fan_mode", {"entity_id": entity, "fan_mode": modes[i]}
                )
        elif action in _MODE_ACTIONS:
            supported = attrs.get("hvac_modes") or []
            mode = action
            # some ACs call the combined mode "heat_cool" rather than "auto"
            if mode == "auto" and "auto" not in supported and "heat_cool" in supported:
                mode = "heat_cool"
            if supported and mode not in supported:
                log.info("climate %s has no %s mode (has %s)", entity, mode, supported)
                return
            await ha.call_service(
                "climate", "set_hvac_mode", {"entity_id": entity, "hvac_mode": mode}
            )
    except Exception as exc:  # noqa: BLE001 — a climate tap must not crash anything
        log.warning("climate control %r failed: %s", action, exc)
