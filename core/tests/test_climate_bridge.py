"""The robot-screen climate bridge: button actions → the right HA service calls."""
from __future__ import annotations

from dravix.climate_bridge import handle_control, push_status


class _HA:
    def __init__(self, state: str, attrs: dict) -> None:
        self._state = state
        self._attrs = attrs
        self.calls: list = []

    async def get_state(self, entity_id):
        return {"state": self._state, "attributes": self._attrs}

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))


_AC = {
    "friendly_name": "Living Room AC",
    "current_temperature": 24.0,
    "temperature": 21.0,
    "hvac_modes": ["off", "cool", "heat", "fan_only", "dry", "heat_cool"],
    "min_temp": 16.0,
    "max_temp": 30.0,
    "target_temp_step": 1.0,
    "fan_mode": "low",
    "fan_modes": ["low", "medium", "high", "auto"],
}


async def test_temp_up_down_respects_step_and_bounds():
    ha = _HA("cool", {**_AC, "temperature": 29.0})
    await handle_control(ha, "climate.ac", "temp_up")
    # 29 + 1 = 30 (== max), allowed
    assert ha.calls[-1] == ("climate", "set_temperature", {"entity_id": "climate.ac", "temperature": 30.0})

    ha = _HA("cool", {**_AC, "temperature": 30.0})
    await handle_control(ha, "climate.ac", "temp_up")
    assert ha.calls[-1][2]["temperature"] == 30.0  # clamped at max

    ha = _HA("cool", {**_AC})
    await handle_control(ha, "climate.ac", "temp_down")
    assert ha.calls[-1] == ("climate", "set_temperature", {"entity_id": "climate.ac", "temperature": 20.0})


async def test_mode_buttons_set_hvac_mode_and_guard_unsupported():
    ha = _HA("cool", _AC)
    await handle_control(ha, "climate.ac", "heat")
    assert ha.calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "heat"})

    await handle_control(ha, "climate.ac", "off")
    assert ha.calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "off"})

    # "auto" → mapped to the AC's "heat_cool"
    await handle_control(ha, "climate.ac", "auto")
    assert ha.calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "heat_cool"})

    # an unsupported mode is skipped (no call added)
    n = len(ha.calls)
    ha2 = _HA("cool", {**_AC, "hvac_modes": ["off", "cool"]})
    await handle_control(ha2, "climate.ac", "heat")
    assert ha2.calls == []


async def test_fan_cycle_advances_through_fan_modes():
    ha = _HA("cool", _AC)  # current fan_mode "low" → next "medium"
    await handle_control(ha, "climate.ac", "fan_cycle")
    assert ha.calls[-1] == ("climate", "set_fan_mode", {"entity_id": "climate.ac", "fan_mode": "medium"})


async def test_push_status_writes_the_three_slots():
    ha = _HA("cool", _AC)
    discovered = {
        "climate_name_text": "text.dravix_climate_name",
        "climate_set_text": "text.dravix_climate_set",
        "climate_info_text": "text.dravix_climate_info",
    }
    await push_status(ha, "climate.ac", discovered)
    writes = {d["entity_id"]: d["value"] for _, _, d in ha.calls}
    assert writes["text.dravix_climate_name"] == "Living Room AC"
    assert writes["text.dravix_climate_set"] == "21°"
    assert "now 24°" in writes["text.dravix_climate_info"]
    # "mode|" prefix (fw 30+) — the firmware strips it and lights the matching mode pill
    assert writes["text.dravix_climate_info"].startswith("cool|")


async def test_control_noops_without_entity():
    ha = _HA("cool", _AC)
    await handle_control(ha, "", "heat")
    assert ha.calls == []
