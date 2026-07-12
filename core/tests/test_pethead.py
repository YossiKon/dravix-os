"""The pet head-lift behavior: petting tilts the head up, then it returns after a hold."""
from __future__ import annotations

import asyncio

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.pethead import PetHeadBehavior
from dravix.state import RobotState


class _RecordingDriver(MockDriver):
    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[float, float]] = []

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        self.moves.append((yaw, pitch))


async def test_pet_raises_head_then_returns():
    bus = EventBus()
    driver = _RecordingDriver()
    controller = RobotController(driver, bus, RobotState())
    await controller.connect()
    beh = PetHeadBehavior(bus, controller, hold_s=0.02, raise_pitch=30)
    await beh.start()
    await asyncio.sleep(0.05)  # let the pump subscribe

    await bus.publish("touch.pet")
    await asyncio.sleep(0.15)  # raise, hold, then return
    await beh.stop()

    # DEGREES in config are normalized to the -1..1 head API (30° → 1/3 of travel) —
    # passing 30.0 raw used to clamp to 1.0 and slam the head to FULL pitch on a pet.
    assert driver.moves[0] == (0.0, 30.0 / 90.0)  # gently tilted up on the pet
    assert driver.moves[-1] == (0.0, 0.0)  # returned to centre after the hold


async def test_repeated_petting_keeps_head_up_without_respamming():
    bus = EventBus()
    driver = _RecordingDriver()
    controller = RobotController(driver, bus, RobotState())
    await controller.connect()
    beh = PetHeadBehavior(bus, controller, hold_s=0.08, raise_pitch=25)
    await beh.start()
    await asyncio.sleep(0.05)

    for _ in range(3):
        await bus.publish("touch.pet")
        await asyncio.sleep(0.02)  # re-pet before the hold elapses
    await asyncio.sleep(0.2)  # now let it settle back
    await beh.stop()

    # Only ONE raise (not one per pet), then a single return — kind to the servo bus.
    assert driver.moves.count((0.0, 25.0 / 90.0)) == 1
    assert driver.moves[-1] == (0.0, 0.0)
