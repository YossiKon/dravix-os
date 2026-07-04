"""Agent presence — let an AI coding agent on your PC use the robot as a status lamp.

An agent (Claude Code, Cursor, a CI runner, your own script …) POSTs its state to
``/api/agent/status`` and the robot reflects it with a **face + LED colour** and, for the
states that need you, a short **spoken line** — so you can glance over and instantly know
whether it's working, waiting for your approval, asking a question, finished, or hit an
error.

Everything is best-effort and capability-guarded: on a backend without a face / LEDs /
speech the missing channel is simply skipped, never an error. Nothing here talks to the
network — the agent reaches the add-on over your LAN — so it fully respects isLocal.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class _Look:
    """How the robot shows one agent state."""

    face: str            # an Expression value (neutral|happy|sad|doubt|…)
    led: str             # colour the driver understands (hex or name)
    brightness: float    # 0..1
    say_en: str          # default spoken line (English) when the caller sends none
    say_he: str          # default spoken line (Hebrew)
    speak: bool          # speak by default for this state?


# state → look. The attention states (permission / question / error) speak by default;
# the ambient ones (working / idle) stay silent so the robot isn't chatty while you work.
# Unknown states fall back to WORKING rather than going dark.
_LOOKS: dict[str, _Look] = {
    "working":            _Look("doubt",   "#1E88E5", 0.6, "",                      "",                     False),
    "waiting_permission": _Look("doubt",   "#FB8C00", 1.0, "I need your approval.",  "צריך את האישור שלך.",  True),
    "question":           _Look("neutral", "#8E24AA", 1.0, "I have a question.",     "יש לי שאלה.",          True),
    "done":               _Look("happy",   "#43A047", 0.8, "All done.",              "סיימתי.",              True),
    "error":              _Look("sad",     "#E53935", 1.0, "Something went wrong.",  "משהו השתבש.",          True),
    "idle":               _Look("neutral", "#101010", 0.0, "",                      "",                     False),
}

STATES: tuple[str, ...] = tuple(_LOOKS.keys())


class AgentPresence:
    """Holds the current agent status and mirrors it onto the robot."""

    def __init__(self, robot, bus) -> None:  # noqa: ANN001 — RobotController + EventBus
        self._robot = robot
        self._bus = bus
        self._state = "idle"
        self._text = ""
        self._updated = ""
        self._source = ""

    def snapshot(self) -> dict:
        return {
            "state": self._state,
            "text": self._text,
            "updated_at": self._updated,
            "source": self._source,
        }

    async def set(
        self,
        state: str,
        text: str = "",
        *,
        say: bool | None = None,
        source: str = "",
        now: datetime.datetime | None = None,
    ) -> dict:
        """Record a new agent state and reflect it on the robot (best-effort)."""
        from .dal.base import CAP_FACE, CAP_LEDS, CAP_SAY

        look = _LOOKS.get(state, _LOOKS["working"])
        self._state = state
        self._text = (text or "").strip()
        self._source = (source or "").strip()
        stamp = now or datetime.datetime.now()
        self._updated = stamp.isoformat(timespec="seconds")

        robot = self._robot
        if robot.supports(CAP_FACE):
            try:
                await robot.set_face(look.face)
            except Exception:  # noqa: BLE001 — a status lamp must never raise into the caller
                pass
        if robot.supports(CAP_LEDS):
            try:
                await robot.set_leds(look.led, look.brightness)
            except Exception:  # noqa: BLE001
                pass

        speak = look.speak if say is None else bool(say)
        if speak and robot.supports(CAP_SAY):
            from .config import get_settings

            he = (get_settings().language or "en").startswith("he")
            line = self._text or (look.say_he if he else look.say_en)
            if line:
                try:
                    await robot.say(line)
                except Exception:  # noqa: BLE001
                    pass

        try:
            await self._bus.publish("agent.status", **self.snapshot())
        except Exception:  # noqa: BLE001 — publishing is a nicety for the live dashboard
            pass
        return self.snapshot()
