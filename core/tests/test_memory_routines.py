"""Tests for the memory store + routine runner."""
from __future__ import annotations

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.memory import build_memory_context
from dravix.routines import run_routine
from dravix.state import RobotState
from dravix.store import Store


def test_store_memories(tmp_path):
    s = Store(tmp_path / "s.json")
    m = s.add_memory("My name is Dana")
    assert m["id"] and m["text"] == "My name is Dana"
    assert len(s.memories()) == 1
    assert "Dana" in build_memory_context(s)
    # persists
    assert Store(tmp_path / "s.json").memories()[0]["text"] == "My name is Dana"
    assert s.remove_memory(m["id"]) is True
    assert s.remove_memory("nope") is False
    assert build_memory_context(s) == ""


async def test_run_routine():
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    steps = [
        {"face": "happy", "say": "Good morning!"},
        {"emote": "wake"},
        {"head": [10, 0], "wait": 0},
    ]
    await run_routine(c, steps)
    assert c.state.last_said == "Good morning!"
    assert c.state.head_yaw == 10
    await c.close()
