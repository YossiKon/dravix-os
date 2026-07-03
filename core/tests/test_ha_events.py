"""Tests for the HA event bridge's pure mapping logic (no network)."""
from __future__ import annotations

from dravix.integrations.ha_events import ha_ws_url, map_state_changed


def _changed(eid, old, new, device_class=None):
    new_state = {"state": new}
    if device_class is not None:
        new_state["attributes"] = {"device_class": device_class}
    return {"entity_id": eid, "old_state": {"state": old}, "new_state": new_state}


def test_binary_sensor_motion_maps():
    out = map_state_changed(_changed("binary_sensor.office", "off", "on", "motion"))
    assert out == ("ha.motion", {"entity_id": "binary_sensor.office", "device_class": "motion"})


def test_door_maps():
    out = map_state_changed(_changed("binary_sensor.front", "off", "on", "door"))
    assert out[0] == "ha.door"


def test_no_fire_when_already_active():
    assert map_state_changed(_changed("binary_sensor.office", "on", "on", "motion")) is None


def test_head_touch_maps_to_pet():
    out = map_state_changed(_changed("binary_sensor.stackchan_touch_sensor_head", "off", "on"))
    assert out == ("touch.pet", {"entity_id": "binary_sensor.stackchan_touch_sensor_head"})


def test_loose_head_or_touch_names_do_not_map():
    # Only a real "*touch_sensor*" object_id counts — not any entity with "head"/"touch" in it.
    assert map_state_changed(_changed("binary_sensor.bathroom_overhead_motion", "off", "on")) is None
    assert map_state_changed(_changed("binary_sensor.door_touched", "off", "on")) is None
    assert map_state_changed(_changed("sensor.kitchen_touchpad", "No touch", "HIGH")) is None


def test_stackchan_text_touch_sensor_maps_to_pet():
    # The StackChan touch zones are text sensors: "No touch" -> "MEDIUM" means a pet.
    out = map_state_changed(_changed("sensor.dravix_touch_sensor_1", "No touch", "MEDIUM"))
    assert out == ("touch.pet", {"entity_id": "sensor.dravix_touch_sensor_1", "state": "MEDIUM"})


def test_text_touch_sensor_no_fire_when_still_touched():
    assert map_state_changed(_changed("sensor.dravix_touch_sensor_1", "LOW", "HIGH")) is None
    assert map_state_changed(_changed("sensor.dravix_touch_sensor_1", "HIGH", "No touch")) is None


def test_explicit_map_wins():
    out = map_state_changed(
        _changed("sensor.custom", "idle", "on"), {"sensor.custom": "presence.detected"}
    )
    assert out == ("presence.detected", {"entity_id": "sensor.custom", "state": "on"})


def test_unmapped_returns_none():
    assert map_state_changed(_changed("light.kitchen", "off", "on")) is None


def test_removed_entity_returns_none():
    assert map_state_changed({"entity_id": "binary_sensor.x", "new_state": None}) is None


def test_ws_url_derivation():
    assert ha_ws_url("https://ha.example.com") == "wss://ha.example.com/api/websocket"
    assert ha_ws_url("http://homeassistant.local:8123/") == "ws://homeassistant.local:8123/api/websocket"
