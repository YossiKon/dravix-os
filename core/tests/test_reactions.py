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


async def test_reaction_floor_is_per_rule_and_stops_self_feeding_loops():
    """Every rule gets a 1 s floor (robot writes no longer block on HA, so a rule fed by its
    own output would spin) — but two UNNAMED rules on one event never throttle each other."""
    c = await _controller()
    rules = [
        {"on": "ha.motion", "match": {"entity_id": "hall"}, "say": "hall"},
        {"on": "ha.motion", "match": {"entity_id": "door"}, "say": "door"},
        {"name": "loop", "on": "robot.say", "face": "happy"},
    ]
    eng = ReactionEngine(c, c._bus, store=_StoreStub(rules))
    fired: list[str] = []
    run = eng._run

    async def counting(rule, event):
        fired.append(rule.get("name") or rule.get("say"))
        await run(rule, event)

    eng._run = counting
    await eng.handle(Event(type="ha.motion", data={"entity_id": "hall"}))
    await eng.handle(Event(type="ha.motion", data={"entity_id": "door"}))
    for _ in range(5):                            # a burst of echoes fires the rule ONCE
        await eng.handle(Event(type="robot.say", data={}))
    assert fired == ["hall", "door", "loop"]      # the door rule wasn't swallowed by the hall rule
    await c.close()


def test_warning_console_still_feeds_the_diagnostics_ring():
    import logging

    from dravix.logging import get_logger, recent_logs, setup_logging

    setup_logging("WARNING")
    try:
        assert logging.getLogger().handlers[0].level == logging.WARNING
        get_logger("test").info("robot connected (ring check)")
        assert any(r["msg"] == "robot connected (ring check)" for r in recent_logs())
    finally:
        setup_logging("WARNING")
