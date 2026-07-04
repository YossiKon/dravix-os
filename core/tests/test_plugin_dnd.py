"""Do-not-disturb behaviour: the shared ModeContext helper + the plugins that use it.

The plugins are loaded from ``plugins/<name>/mode.py`` by file path (the same way the mode
engine does), so these exercise the real plugin code, not a copy.
"""
from __future__ import annotations

import importlib.util

from dravix.config import PLUGINS_DIR
from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, Expression
from dravix.events import EventBus
from dravix.modes.base import ModeContext


class _Driver:
    """A robot driver stub exposing just get_text('state_sensor')."""

    def __init__(self, state: str | None) -> None:
        self._state = state

    async def get_text(self, role: str) -> str | None:
        assert role == "state_sensor"
        return self._state


class _Robot:
    def __init__(self, state: str | None = "awake", caps=(CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY)):
        self.driver = _Driver(state)
        self._caps = set(caps)
        self.idle_motion = True
        self.moves: list = []
        self.faces: list = []
        self.leds: list = []
        self.said: list = []

    def supports(self, cap: str) -> bool:
        return cap in self._caps

    async def move_head(self, yaw, pitch, speed: float = 1.0) -> None:
        self.moves.append((yaw, pitch))

    async def set_face(self, expr) -> None:
        self.faces.append(expr)

    async def set_leds(self, color, brightness) -> None:
        self.leds.append((color, brightness))

    async def say(self, text, voice=None) -> None:
        self.said.append(text)


def _ctx(robot: _Robot, **config) -> ModeContext:
    return ModeContext(robot=robot, bus=EventBus(), config=config)


def _load(plugin: str):
    """Import plugins/<plugin>/mode.py by path and return its module."""
    path = PLUGINS_DIR / plugin / "mode.py"
    spec = importlib.util.spec_from_file_location(f"_test_plugin_{plugin}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the shared helper ─────────────────────────────────────────────────────────
async def test_is_quiet_and_is_asleep():
    assert await _ctx(_Robot("focus")).is_quiet() is True
    assert await _ctx(_Robot("night")).is_quiet() is True
    assert await _ctx(_Robot("awake")).is_quiet() is False
    assert await _ctx(_Robot("party")).is_quiet() is False   # unknown state = active
    assert await _ctx(_Robot(None)).is_quiet() is False       # unreadable = active
    assert await _ctx(_Robot("sleep")).is_asleep() is True
    assert await _ctx(_Robot("screensaver")).is_asleep() is True
    assert await _ctx(_Robot("focus")).is_asleep() is False   # calm but not "off"


# ── ambient_idle: no head twitch in a calm mode ───────────────────────────────
async def test_ambient_idle_skips_quiet_modes():
    Mode = _load("ambient_idle").AmbientIdleMode

    quiet = _Robot("focus")
    m = Mode(_ctx(quiet, glance_every_ticks=1))
    await m.on_enter()
    await m.tick()
    assert quiet.moves == []          # focus → do not disturb
    assert quiet.faces == []          # ambient_idle never touches the face anymore

    awake = _Robot("awake")
    m = Mode(_ctx(awake, glance_every_ticks=1))
    await m.on_enter()
    await m.tick()
    assert len(awake.moves) == 1      # awake → it glances


# ── dance: no disco while the robot is asleep ─────────────────────────────────
async def test_dance_silent_when_asleep():
    Mode = _load("dance").DanceMode

    asleep = _Robot("sleep")
    m = Mode(_ctx(asleep))
    await m.on_enter()
    asleep.moves.clear(); asleep.leds.clear()
    await m.tick()
    assert asleep.moves == [] and asleep.leds == []

    awake = _Robot("awake")
    m = Mode(_ctx(awake))
    await m.on_enter()
    awake.moves.clear(); awake.leds.clear()
    await m.tick()
    assert awake.moves and awake.leds


# ── guard: throttled, and voice-suppressed (only) in DND ──────────────────────
async def test_guard_throttle_and_quiet_no_voice():
    from dravix.events import Event

    Mode = _load("guard").GuardMode

    awake = _Robot("awake")
    m = Mode(_ctx(awake, throttle_s=100, alert_line="Alert!"))
    await m.on_enter()
    await m.on_event(Event(type="ha.motion"))
    await m.on_event(Event(type="ha.motion"))   # within throttle → ignored
    assert awake.said == ["Alert!"]             # exactly one alert, not machine-gunned

    quiet = _Robot("night")
    m = Mode(_ctx(quiet, throttle_s=0, quiet_no_voice=True))
    await m.on_enter()
    quiet.said.clear(); quiet.leds.clear()
    await m.on_event(Event(type="ha.motion"))
    assert quiet.said == []          # no spoken alert at night…
    assert quiet.leds                # …but the visual alert still fires
