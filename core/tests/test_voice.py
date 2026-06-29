"""Tests for TTS voice selection (override / per-persona) and its application to speech."""
from __future__ import annotations

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.persona import resolve_voice
from dravix.state import RobotState
from dravix.store import Store


def test_resolve_voice_precedence(tmp_path):
    s = Store(tmp_path / "s.json")
    assert resolve_voice(s) is None
    s.set_personas([{"name": "P", "system_prompt": "x", "voice": "piper-amy"}])
    s.set_active_persona("P")
    assert resolve_voice(s) == "piper-amy"  # persona voice
    s.set_voice("override-voice")
    assert resolve_voice(s) == "override-voice"  # global override wins
    s.set_voice(None)
    assert resolve_voice(s) == "piper-amy"  # falls back to persona


async def test_controller_applies_default_voice():
    drv = MockDriver()
    c = RobotController(drv, EventBus(), RobotState())
    await c.connect()
    c.default_voice = "myvoice"
    await c.say("hi")
    assert drv.last_voice == "myvoice"
    await c.say("yo", voice="explicit")
    assert drv.last_voice == "explicit"  # explicit voice overrides the default
    await c.close()
