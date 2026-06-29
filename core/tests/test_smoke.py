"""Smoke tests that run fully offline (mock driver, no robot/HA needed)."""
from __future__ import annotations

import pytest

from dravix.config import PLUGINS_DIR
from dravix.dal.base import CAP_FACE, Expression, RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.modes import ModeContext, ModeEngine
from dravix.state import RobotState


async def _make_controller() -> RobotController:
    bus = EventBus()
    controller = RobotController(MockDriver(), bus, RobotState())
    await controller.connect()
    return controller


async def test_mock_controller_verbs():
    controller = await _make_controller()
    assert controller.state.online is True
    assert controller.supports(CAP_FACE)
    await controller.set_face(Expression.HAPPY)
    assert controller.state.expression == "happy"
    await controller.move_head(10, -5)
    assert controller.state.head_yaw == 10
    await controller.say("hello")
    assert controller.state.last_said == "hello"
    await controller.close()
    assert controller.state.online is False


def test_expression_coerce():
    assert Expression.coerce("HAPPY") is Expression.HAPPY
    assert Expression.coerce("nonsense") is Expression.NEUTRAL


async def test_engine_discovers_example_plugin():
    controller = await _make_controller()
    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=controller, bus=controller._bus))
    engine.discover()
    names = {m["name"] for m in engine.list_modes()}
    assert "focus" in names, f"expected 'focus' plugin, found {names}"
    await engine.activate("focus")
    assert engine.active == "focus"
    await engine.deactivate()
    assert engine.active is None
    await controller.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
