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


async def test_spontaneous_speech_gate():
    drv = MockDriver()
    c = RobotController(drv, EventBus(), RobotState())
    await c.connect()

    # spontaneous speech OFF → proactive chatter is muted, but user/AI speech still speaks
    c.speak_spontaneous = False
    await c.say("bored quip", proactive=True)
    assert c.state.last_said != "bored quip"      # never reached the driver
    await c.say("AI reply")                        # non-proactive always speaks
    assert c.state.last_said == "AI reply"

    # turning it ON lets proactive speech through
    c.speak_spontaneous = True
    await c.say("good morning!", proactive=True)
    assert c.state.last_said == "good morning!"
    await c.close()
