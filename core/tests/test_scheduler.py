"""Tests for the scheduler (daily jobs + one-shot timers)."""
from __future__ import annotations

import asyncio
import datetime

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.scheduler import Scheduler, daily_due
from dravix.state import RobotState


class _Store:
    def __init__(self, jobs):
        self._jobs = jobs

    def schedule(self):
        return self._jobs


async def _controller() -> RobotController:
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    return c


def test_daily_due():
    assert daily_due({"at": "08:00"}, "08:00", 2) is True
    assert daily_due({"at": "08:00"}, "08:01", 2) is False
    assert daily_due({"at": "08:00", "days": [0, 1]}, "08:00", 2) is False  # Wed not in Mon/Tue
    assert daily_due({"at": "08:00", "days": [2]}, "08:00", 2) is True
    assert daily_due({"at": "08:00", "enabled": False}, "08:00", 2) is False


async def test_daily_job_fires_once_per_day():
    c = await _controller()
    jobs = [{"name": "morning", "at": "08:00", "action": {"say": "Good morning!", "face": "happy"}}]
    fixed = datetime.datetime(2026, 6, 29, 8, 0, 0)
    sched = Scheduler(c._bus, c, store=_Store(jobs), clock=lambda: fixed)
    await sched.check_daily()
    assert c.state.last_said == "Good morning!"
    assert c.state.expression == "happy"
    c.state.last_said = ""
    await sched.check_daily()  # same minute, same day
    assert c.state.last_said == ""  # already fired today — no double-fire
    await c.close()


async def test_scheduler_action_leds_and_head():
    c = await _controller()
    sched = Scheduler(c._bus, c, store=_Store([]))
    await sched.run_action({"leds": {"color": "red", "brightness": 0.5}, "head": [12, 3], "say": "hi"}, {})
    assert c.state.head_yaw == 12  # head action applied
    assert c.state.last_said == "hi"
    await c.close()


async def test_timer_fires():
    c = await _controller()
    sched = Scheduler(c._bus, c)
    await sched.set_timer(0.05, "tea")
    await asyncio.sleep(0.15)
    assert "tea" in c.state.last_said.lower()
    await c.close()
