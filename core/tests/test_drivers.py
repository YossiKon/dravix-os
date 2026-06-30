"""Tests for driver wiring (the HA fallback driver's capabilities from configured entities)."""
from __future__ import annotations

from dravix.dal.base import CAP_HEAD, CAP_LEDS, CAP_SAY
from dravix.dal.ha_driver import HARobotDriver


async def test_ha_driver_capabilities_from_entities():
    d = HARobotDriver(
        ha=None,
        entities={
            "media_player": "media_player.stackchan",
            "led_light": "light.stackchan",
            "head_yaw": "number.yaw",
            "head_pitch": "number.pitch",
        },
    )
    assert await d.capabilities() == {CAP_SAY, CAP_LEDS, CAP_HEAD}


async def test_ha_driver_no_entities_is_empty():
    d = HARobotDriver(ha=None, entities={})
    assert await d.capabilities() == set()
