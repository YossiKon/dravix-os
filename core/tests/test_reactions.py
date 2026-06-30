"""Tests for the configurable event→action reaction engine."""
from __future__ import annotations

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import Event, EventBus
from dravix.reactions import ReactionEngine
from dravix.state import RobotState


class _StoreStub:
    def __init__(self, rules):
        self._rules = rules

    def reactions(self):
        return self._rules


async def _controller() -> RobotController:
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    return c


async def test_reaction_matches_and_runs():
    c = await _controller()
    rules = [{
        "name": "r1",
        "on": "ha.motion",
        "match": {"entity_id": "x"},
        "face": "angry",
        "say": "hi {entity_id}",
        "throttle_s": 0,
    }]
    eng = ReactionEngine(c, c._bus, store=_StoreStub(rules))
    await eng.handle(Event(type="ha.motion", data={"entity_id": "x"}))
    assert c.state.expression == "angry"
    assert c.state.last_said == "hi x"
    await c.close()


async def test_reaction_no_match_and_wrong_type():
    c = await _controller()
    rules = [{"name": "r", "on": "ha.motion", "match": {"entity_id": "y"}, "say": "nope"}]
    eng = ReactionEngine(c, c._bus, store=_StoreStub(rules))
    await eng.handle(Event(type="ha.motion", data={"entity_id": "x"}))  # match fails
    await eng.handle(Event(type="other", data={}))  # type mismatch
    assert c.state.last_said == ""
    await c.close()


async def test_reaction_emote_action():
    c = await _controller()
    rules = [{"name": "e", "on": "x", "emote": "yes"}]
    eng = ReactionEngine(c, c._bus, store=_StoreStub(rules))
    await eng.handle(Event(type="x", data={}))
    assert c.state.expression == "happy"  # the 'yes' emote ends on a happy face
    await c.close()


async def test_reaction_throttle():
    c = await _controller()
    rules = [{"name": "r", "on": "tick", "say": "{n}", "throttle_s": 60}]
    eng = ReactionEngine(c, c._bus, store=_StoreStub(rules))
    await eng.handle(Event(type="tick", data={"n": "1"}))
    assert c.state.last_said == "1"
    await eng.handle(Event(type="tick", data={"n": "2"}))
    assert c.state.last_said == "1"  # second within window is throttled
    await c.close()
