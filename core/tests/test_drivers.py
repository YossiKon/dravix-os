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
            return {"state": "12", "attributes": {"min": -164, "max": 164, "step": 5}}
        return {"state": "45", "attributes": {"min": 0, "max": 90, "step": 5}}

    async def camera_snapshot(self, entity_id):
        return b"JPEG-bytes"


async def test_ha_driver_move_head_normalized_full_travel():
    """Normalised head: 0 = servo midpoint, +1 = max, -1 = min (uses the full travel)."""
    ha = _FakeHA()  # servo_x -164..164 (mid 0), servo_y 0..90 (mid 45), both step 5
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    await d.move_head(0, 0)
    assert ha.calls[-2][2]["value"] == 0.0     # yaw centre
    assert ha.calls[-1][2]["value"] == 45.0    # pitch centre (midpoint)
    await d.move_head(1, 1)
    assert ha.calls[-2][2]["value"] == 164.0   # yaw max
    assert ha.calls[-1][2]["value"] == 90.0    # pitch max
    await d.move_head(-1, -1)
    assert ha.calls[-2][2]["value"] == -164.0  # yaw min
    assert ha.calls[-1][2]["value"] == 0.0     # pitch min


async def test_ha_driver_head_calibration_center_and_invert():
    """Calibrated centre = 'look straight'; invert flips; travel spans centre→each real end."""
    ha = _FakeHA()  # servo_y 0..90 step 5
    d = HARobotDriver(
        ha=ha,
        entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"},
        # pitch's straight-ahead is really 20 (not the 45 midpoint), and it's flipped.
        calibration={"pitch": {"center": 20, "invert": True}},
    )
    await d.move_head(0, 0)   # straight → the calibrated centre
    assert ha.calls[-1][2]["value"] == 20.0
    await d.move_head(0, 1)   # "up", inverted → toward min: 20 + (-1)*(20-0) = 0
    assert ha.calls[-1][2]["value"] == 0.0
    await d.move_head(0, -1)  # "down", inverted → toward max: 20 + 1*(90-20) = 90
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
    d._MIN_BUS_SPACING = 0
    await d.move_head(0, 0)  # yaw retries twice then lands; pitch lands first try
    writes = [c for c in ha.calls if c[1] == "set_value"]
    assert len(writes) == 2  # both axes ultimately written


async def test_ha_driver_head_raises_after_exhausting_retries():
    ha = _FlakyHA(fail_times=99)  # never recovers
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    d._SET_RETRY_DELAY = 0
    d._MIN_BUS_SPACING = 0
    import pytest

    with pytest.raises(RuntimeError):
        await d.move_head(0, 0)


async def test_ha_driver_read_head_raw():
    """'Set current as home' reads the servos' live raw angles."""
    ha = _FakeHA()
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    assert await d.read_head_raw() == {"yaw": 12.0, "pitch": 45.0}


async def test_ha_driver_head_always_in_range():
    """Any command (even over-driven) stays within the servo's real range — never a 500."""
    ha = _FakeHA()  # servo_y real range 0..90
    d = HARobotDriver(
        ha=ha, entities={"head_yaw": "number.servo_x", "head_pitch": "number.servo_y"}
    )
    await d.move_head(0, 5)    # 5 clamps to +1 → the real max (90)
    assert ha.calls[-1][2]["value"] == 90.0
    await d.move_head(0, -5)   # -5 clamps to -1 → the real min (0)
    assert ha.calls[-1][2]["value"] == 0.0


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


async def test_ha_driver_get_text_live_sensors():
    """Live-state sensors (state/heard/reply) read as plain text; unmapped/unavailable → None."""
    class _TextHA(_FakeHA):
        async def get_state(self, entity_id):
            if entity_id == "sensor.state":
                return {"state": "listening", "attributes": {}}
            return {"state": "unavailable", "attributes": {}}

    d = HARobotDriver(
        ha=_TextHA(),
        entities={"state_sensor": "sensor.state", "heard_sensor": "sensor.heard"},
    )
    assert await d.get_text("state_sensor") == "listening"
    assert await d.get_text("heard_sensor") is None   # unavailable → None
    assert await d.get_text("reply_sensor") is None   # not mapped → None


async def test_ha_driver_leds_off():
    """color='off' (or zero brightness) turns the light off instead of turn_on."""
    ha = _FakeHA()
    d = HARobotDriver(ha=ha, entities={"led_light": "light.bar"})
    await d.set_leds("off")
    assert ha.calls[-1] == ("light", "turn_off", {"entity_id": "light.bar"})
    await d.set_leds("red", 0)
    assert ha.calls[-1] == ("light", "turn_off", {"entity_id": "light.bar"})
    await d.set_leds("red", 0.5)
    assert ha.calls[-1][1] == "turn_on"


async def test_ha_driver_privacy():
    """Privacy: read the switch state; set via switch.turn_on/off; unmapped = never private."""
    class _PrivHA(_FakeHA):
        async def get_state(self, entity_id):
            if entity_id == "switch.priv":
                return {"state": "on", "attributes": {}}
            return await super().get_state(entity_id)

    ha = _PrivHA()
    d = HARobotDriver(ha=ha, entities={"privacy_switch": "switch.priv"})
    assert await d.is_private() is True
    await d.set_privacy(False)
    assert ha.calls[-1] == ("switch", "turn_off", {"entity_id": "switch.priv"})
    await d.set_privacy(True)
    assert ha.calls[-1] == ("switch", "turn_on", {"entity_id": "switch.priv"})
    assert await HARobotDriver(ha=ha, entities={}).is_private() is False


async def test_ha_driver_show_image_url():
    """Image-by-URL lands in the firmware's Show-image text slot (text.set_value)."""
    ha = _FakeHA()
    d = HARobotDriver(ha=ha, entities={"image_url_text": "text.dravix_show_image_url"})
    await d.show_image_url("http://frigate:5000/api/door/latest.jpg?height=240")
    assert ha.calls[-1] == (
        "text", "set_value",
        {"entity_id": "text.dravix_show_image_url",
         "value": "http://frigate:5000/api/door/latest.jpg?height=240"},
    )
    import pytest

    with pytest.raises(NotImplementedError):
        await HARobotDriver(ha=ha, entities={}).show_image_url("http://x/y.jpg")


async def test_ha_driver_set_mode_via_select():
    """Sleep/wake maps to select.select_option on the mode_select entity."""
    ha = _FakeHA()
    d = HARobotDriver(ha=ha, entities={"mode_select": "select.dravix_mode"})
    await d.set_mode("sleep")
    assert ha.calls[-1] == (
        "select", "select_option",
        {"entity_id": "select.dravix_mode", "option": "sleep"},
    )


async def test_ha_driver_set_mode_without_entity_raises():
    d = HARobotDriver(ha=_FakeHA(), entities={})
    import pytest

    with pytest.raises(NotImplementedError):
        await d.set_mode("awake")


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
