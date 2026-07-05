"""Privacy mode is enforced at the RobotController choke point: no camera, no mic.

Also covers the LED hex → rgb_color path added for the colour-blind-safe agent palette.
"""
from __future__ import annotations

import pytest

from dravix.dal.base import ALL_CAPABILITIES, RobotController
from dravix.dal.ha_driver import _hex_to_rgb
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.state import RobotState


class _PrivateMock(MockDriver):
    """Mock that also exposes a togglable Privacy switch like the HA driver."""

    def __init__(self) -> None:
        super().__init__()
        self.private = False

    async def is_private(self) -> bool:
        return self.private

    async def take_photo(self):  # noqa: ANN201 — returns a fake frame
        return b"\xff\xd8realframe"


async def _controller(driver):
    ctrl = RobotController(driver, EventBus(), RobotState())
    await ctrl.connect()
    return ctrl


@pytest.mark.asyncio
async def test_take_photo_blocked_in_privacy():
    drv = _PrivateMock()
    ctrl = await _controller(drv)

    assert await ctrl.take_photo() == b"\xff\xd8realframe"  # normal: a frame comes back

    drv.private = True
    ctrl._priv_at = 0.0  # bypass the ~1.5s cache for the test
    assert await ctrl.take_photo() is None                  # privacy: nothing, no matter who asks
    assert await ctrl.is_private() is True


@pytest.mark.asyncio
async def test_listen_blocked_in_privacy():
    drv = _PrivateMock()
    ctrl = await _controller(drv)
    drv.private = True
    ctrl._priv_at = 0.0
    assert await ctrl.listen() is None  # no microphone in privacy mode


@pytest.mark.asyncio
async def test_no_privacy_switch_is_never_private():
    # a plain mock (no is_private) must never falsely report private / block the camera
    ctrl = await _controller(MockDriver())
    assert await ctrl.is_private() is False


def test_hex_to_rgb():
    assert _hex_to_rgb("#56B4E9") == (86, 180, 233)
    assert _hex_to_rgb("009E73") == (0, 158, 115)
    assert _hex_to_rgb("blue") is None      # a bare name → caller uses color_name
    assert _hex_to_rgb("#12") is None
