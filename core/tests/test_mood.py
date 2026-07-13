"""Tests for the mood/personality engine and the emote library."""
from __future__ import annotations

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.emotes import emote_names, play_emote
from dravix.events import Event, EventBus
from dravix.mood import MoodEngine
from dravix.state import RobotState
from dravix.store import Store


async def _controller() -> RobotController:
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    return c


async def test_petting_makes_it_happy_and_shows_on_face():
    c = await _controller()
    m = MoodEngine(c._bus, c)  # no engine -> face not locked
    await m.handle(Event(type="touch.pet", data={}))
    await m.handle(Event(type="touch.pet", data={}))
    assert m.valence > 0.4
    assert m.affection > 0.5
    assert m.expression().value == "happy"
    # the pet EMOTE drives the face now (its reaction isn't stomped by a forced mood
    # push) — and at affection 0.7 the bonded robot melts into the love face
    assert c.state.expression == "love"
    await c.close()


async def test_alert_raises_arousal():
    c = await _controller()
    m = MoodEngine(c._bus, c)
    before = m.arousal
    await m.handle(Event(type="guard.alert", data={}))
    assert m.arousal > before
    await c.close()


async def test_mood_persists_across_restart(tmp_path):
    store = Store(tmp_path / "s.json")
    c = await _controller()
    m = MoodEngine(c._bus, c, store=store)
    await m.handle(Event(type="touch.pet", data={}))
    reloaded = MoodEngine(c._bus, c, store=store)
    assert abs(reloaded.valence - m.valence) < 1e-6
    assert abs(reloaded.affection - m.affection) < 1e-6
    await c.close()


async def test_emotes_play_on_mock():
    c = await _controller()
    assert {"happy", "love", "fistbump", "curious"} <= set(emote_names())
    await play_emote(c, "happy")  # must not raise
    await play_emote(c, "fistbump")
    await c.close()
