"""Tests for the fun/games module and the mood engine's proactive idle behavior."""
from __future__ import annotations

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.emotes import emote_names
from dravix.events import EventBus
from dravix.fun import GAMES, game_names
from dravix.mood import _IDLE_QUIPS, MoodEngine
from dravix.state import RobotState


def test_games_produce_valid_results():
    assert set(game_names()) == {"dice", "coin", "8ball", "joke", "fortune"}
    valid = set(emote_names())
    for fn in GAMES.values():
        r = fn()
        assert r["text"]
        if r.get("emote"):
            assert r["emote"] in valid
    for _ in range(25):
        assert 1 <= GAMES["dice"]()["value"] <= 6


async def test_mood_idle_behavior_speaks():
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    m = MoodEngine(c._bus, c)  # no engine -> not locked
    await m.idle_behavior()
    # quips are now per-language and per-time-of-day — the line must come from the table
    all_quips = [q for lang in _IDLE_QUIPS.values() for slot in lang.values() for q in slot]
    assert c.state.last_said in all_quips
    await c.close()


async def test_mood_idle_behavior_is_not_chatty():
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    m = MoodEngine(c._bus, c)
    await m.idle_behavior()
    first = c.state.last_said
    c.state.last_said = ""
    await m.idle_behavior()  # inside the min-gap → must stay silent
    assert first and c.state.last_said == ""
    await c.close()
