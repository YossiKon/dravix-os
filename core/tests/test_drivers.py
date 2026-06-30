"""Tests for driver wiring (the HA fallback driver's capabilities from configured entities)."""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_PHOTO, CAP_SAY, Expression
from dravix.dal.ha_driver import HARobotDriver


async def test_ha_driver_capabilities_from_entities():
    d = HARobotDriver(
        ha=None,
        entities={
            "media_player": "media_player.stackchan",
            "tts_engine": "tts.piper",
            "led_light": "light.stackchan",
            "head_yaw": "number.yaw",
            "head_pitch": "number.pitch",
        },
    )
    assert await d.capabilities() == {CAP_SAY, CAP_LEDS, CAP_HEAD}


async def test_ha_driver_say_needs_a_tts_engine():
    # media_player alone is not enough for CAP_SAY — a tts engine is required.
    d = HARobotDriver(ha=None, entities={"media_player": "media_player.stackchan"})
    assert await d.capabilities() == set()


async def test_ha_driver_no_entities_is_empty():
    d = HARobotDriver(ha=None, entities={})
    assert await d.capabilities() == set()


class _FakeHA:
    def __init__(self) -> None:
        self.calls: list = []

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))

    async def camera_snapshot(self, entity_id):
        return b"JPEG-bytes"


async def test_ha_driver_stackchan_esphome_entities():
    """The full StackChan ESPHome entity set: face (select) + camera add CAP_FACE/CAP_PHOTO."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha,
        entities={
            "face_select": "select.stackchan_face",
            "head_yaw": "number.yaw",
            "head_pitch": "number.pitch",
            "media_player": "media_player.stackchan",
            "tts_engine": "tts.piper",
            "led_light": "light.stackchan",
            "camera": "camera.stackchan",
        },
    )
    assert await d.capabilities() == {CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, CAP_PHOTO}

    await d.set_face(Expression.HAPPY)
    assert ha.calls[-1] == (
        "select", "select_option",
        {"entity_id": "select.stackchan_face", "option": "happy"},
    )

    await d.say("hello")
    assert ha.calls[-1] == (
        "tts", "speak",
        {"entity_id": "tts.piper", "media_player_entity_id": "media_player.stackchan",
         "message": "hello"},
    )

    assert await d.take_photo() == b"JPEG-bytes"
