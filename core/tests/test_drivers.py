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

    async def get_state(self, entity_id):
        # yaw centered (±164); pitch asymmetric (0..90, center 45), step 5
        if "servo_x" in entity_id:
            return {"attributes": {"min": -164, "max": 164, "step": 5}}
        return {"attributes": {"min": 0, "max": 90, "step": 5}}

    async def camera_snapshot(self, entity_id):
        return b"JPEG-bytes"


async def test_ha_driver_move_head_offsets_to_servo_center():
    """dravix sends head angles relative to 0; pitch (0..90) must offset to its center (45)."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    await d.move_head(0, 0)  # "look center"
    assert ha.calls[-2][2]["value"] == 0.0    # yaw center stays 0
    assert ha.calls[-1][2]["value"] == 45.0   # pitch center = (0+90)/2 = 45 (not 0/down)

    await d.move_head(20, -20)
    assert ha.calls[-2][2]["value"] == 20.0   # yaw 0+20
    assert ha.calls[-1][2]["value"] == 25.0   # pitch 45-20 = 25


async def test_ha_driver_head_calibration_center_and_invert():
    """Dashboard calibration: a custom center fixes a head that 'falls', invert flips direction."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha,
        entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"},
        # pitch neutral is really 20 (not the 45 midpoint), and its direction is flipped.
        calibration={"pitch": {"center": 20, "invert": True}},
    )
    await d.move_head(0, 0)  # look straight
    assert ha.calls[-1][2]["value"] == 20.0   # pitch sits at the calibrated neutral, not 45
    await d.move_head(0, 10)  # command "up" 10°
    assert ha.calls[-1][2]["value"] == 10.0   # inverted: 20 - 10 = 10 (snapped to step 5)
    await d.move_head(0, -100)  # over-drive down → clamps to the servo max (90)
    assert ha.calls[-1][2]["value"] == 90.0


class _FlakyHA(_FakeHA):
    """Fails the first `fail_times` number.set_value calls (simulates a serial-bus NAK)."""

    def __init__(self, fail_times: int = 2) -> None:
        super().__init__()
        self._fail_times = fail_times
        self._attempts = 0

    async def call_service(self, domain, service, data=None):
        if domain == "number" and service == "set_value":
            self._attempts += 1
            if self._attempts <= self._fail_times:
                raise RuntimeError("500 Internal Server Error (serial bus NAK)")
        await super().call_service(domain, service, data)


async def test_ha_driver_head_retries_transient_500():
    """A servo write that NAKs (HA 500) is retried and succeeds — control stays reliable."""
    ha = _FlakyHA(fail_times=2)  # first two writes fail, third succeeds
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    d._SET_RETRY_DELAY = 0  # don't sleep in the test
    await d.move_head(0, 0)  # yaw retries twice then lands; pitch lands first try
    writes = [c for c in ha.calls if c[1] == "set_value"]
    assert len(writes) == 2  # both axes ultimately written


async def test_ha_driver_head_raises_after_exhausting_retries():
    ha = _FlakyHA(fail_times=99)  # never recovers
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    d._SET_RETRY_DELAY = 0
    import pytest

    with pytest.raises(RuntimeError):
        await d.move_head(0, 0)


async def test_ha_driver_say_via_assist_satellite():
    """An assist_satellite.* TTS entity speaks via announce (no media_player needed)."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha, entities={"tts_engine": "assist_satellite.dravix_assist_satellite"}
    )
    assert await d.capabilities() == {CAP_SAY}  # satellite alone enables speech
    await d.say("hi there")
    assert ha.calls[-1] == (
        "assist_satellite", "announce",
        {"entity_id": "assist_satellite.dravix_assist_satellite", "message": "hi there"},
    )


async def test_ha_driver_screen_number_get_set():
    """Screensaver/sleep timers map to number entities dravix can read + write."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha,
        entities={"screensaver_number": "number.servo_y", "sleep_number": "number.servo_x"},
    )
    await d.set_number("screensaver_number", 7)  # range 0..90 step 5 → 5
    assert ha.calls[-1] == ("number", "set_value", {"entity_id": "number.servo_y", "value": 5.0})


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
