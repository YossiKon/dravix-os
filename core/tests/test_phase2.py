"""Tests for Phase 2/3 additions: real plugins, ambient/tick engine, persona, MCP server."""
from __future__ import annotations

from dravix.config import PLUGINS_DIR
from dravix.dal.base import Expression, RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.modes import ModeContext, ModeEngine
from dravix.persona import parse_expression
from dravix.state import RobotState


async def _controller() -> RobotController:
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    return c


def test_parse_expression():
    assert parse_expression("(happy) hello there") == (Expression.HAPPY, "hello there")
    assert parse_expression("[Sad]: oh no") == (Expression.SAD, "oh no")
    assert parse_expression("no tag here") == (Expression.NEUTRAL, "no tag here")
    assert parse_expression("") == (Expression.NEUTRAL, "")


async def test_all_flagship_plugins_load():
    c = await _controller()
    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=c, bus=c._bus))
    engine.discover()
    names = {m["name"] for m in engine.list_modes()}
    assert {"focus", "pomodoro", "companion", "ambient_idle", "guard"} <= names
    await c.close()


async def test_ambient_autostart_and_foreground_switch():
    c = await _controller()
    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=c, bus=c._bus), tick_interval=0.05)
    engine.discover()
    await engine.start()
    try:
        # ambient_idle should auto-start.
        assert "ambient_idle" in engine.ambient_active
        # foreground modes are mutually exclusive.
        await engine.activate("pomodoro")
        assert engine.active == "pomodoro"
        await engine.activate("companion")
        assert engine.active == "companion"
        await engine.deactivate()
        assert engine.active is None
        # ambient still running alongside.
        assert "ambient_idle" in engine.ambient_active
    finally:
        await engine.stop()
        await c.close()


async def test_guard_reacts_to_trigger_event():
    c = await _controller()
    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=c, bus=c._bus))
    engine.discover()
    await engine.activate("guard")
    # Inspect the running guard instance directly (no event-pump timing).
    guard = engine._fg_instance
    from dravix.events import Event

    await guard.on_event(Event(type="ha.motion", data={"area": "office"}))
    assert c.state.expression == "angry"
    await engine.deactivate()
    await c.close()


async def test_mcp_server_builds():
    c = await _controller()
    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=c, bus=c._bus))
    engine.discover()
    from dravix.mcpserver import build_server

    server = build_server(c, engine, ai=None)
    assert server is not None
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {"robot_say", "robot_set_face", "activate_mode", "get_status"} <= names
    await c.close()
