"""Tests for the suffix-anchored robot entity auto-discovery."""
from __future__ import annotations

from dravix.discovery import discover_from_states


def _states(*ids: str) -> list[dict]:
    return [{"entity_id": e} for e in ids]


def test_discovery_full_robot():
    found = discover_from_states(_states(
        "select.dravix_face", "select.dravix_mode", "select.other_mode",
        "number.dravix_servo_x_angle", "number.dravix_head_pitch",
        "number.dravix_screensaver_after_min", "number.dravix_sleep_after_min",
        "light.dravix_stackchan_light_bar", "media_player.dravix_media_player",
        "camera.dravix_camera", "sensor.dravix_state", "sensor.kitchen_state",
        "sensor.dravix_last_heard", "sensor.dravix_last_reply",
        "text.dravix_show_image_url", "switch.dravix_privacy_mode",
        "tts.piper",
    ))
    assert found["face_select"] == "select.dravix_face"
    assert found["mode_select"] == "select.dravix_mode"          # not select.other_mode
    assert found["state_sensor"] == "sensor.dravix_state"        # not sensor.kitchen_state
    assert found["head_yaw"] == "number.dravix_servo_x_angle"
    assert found["head_pitch"] == "number.dravix_head_pitch"
    assert found["led_light"] == "light.dravix_stackchan_light_bar"
    assert found["media_player"] == "media_player.dravix_media_player"
    assert found["camera"] == "camera.dravix_camera"
    assert found["image_url_text"] == "text.dravix_show_image_url"
    assert found["privacy_switch"] == "switch.dravix_privacy_mode"
    assert found["screensaver_number"] == "number.dravix_screensaver_after_min"
    assert found["sleep_number"] == "number.dravix_sleep_after_min"
    assert found["tts_engine"] == "tts.piper"


def test_discovery_renamed_prefix():
    # After an HA device/area rename some entities live under "<area>_<device>" — both
    # prefixes must be recognized as the robot.
    found = discover_from_states(_states(
        "number.study_room_dravix_head_pitch",
        "number.study_room_dravix_screensaver_after_min",
        "text.study_room_dravix_show_image_url",
        "select.study_room_dravix_mode",
        "sensor.study_room_dravix_state",
        "switch.dravix_privacy_mode",
        "sensor.dravix_last_heard",
        "number.dravix_servo_x_angle",
    ))
    assert found["head_pitch"] == "number.study_room_dravix_head_pitch"
    assert found["mode_select"] == "select.study_room_dravix_mode"
    assert found["state_sensor"] == "sensor.study_room_dravix_state"
    assert found["privacy_switch"] == "switch.dravix_privacy_mode"
    assert found["head_yaw"] == "number.dravix_servo_x_angle"


def test_discovery_empty_house():
    assert discover_from_states(_states("light.kitchen", "sensor.outdoor_temp")) == {}
