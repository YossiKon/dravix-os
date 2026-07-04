"""Mode interface + the context object handed to every mode.

A *mode* is the unit of custom behavior ("Focus", "Pomodoro", "Companion", "Guard", ...).
Modes are plugins: they receive a ``ModeContext`` giving safe access to the robot, Home
Assistant, the AI router, the event bus, and per-mode config.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..dal.base import ASLEEP_STATES, QUIET_STATES
from ..events import Event, EventBus
from ..logging import get_logger

if TYPE_CHECKING:  # avoid import cycles at runtime
    from ..ai.base import AIProvider
    from ..dal.base import RobotController
    from ..integrations.homeassistant import HomeAssistant


@dataclass
class ModeContext:
    robot: "RobotController"
    bus: EventBus
    ai: "AIProvider | None" = None
    ha: "HomeAssistant | None" = None
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def log(self):  # noqa: ANN201
        return get_logger("mode")

    async def robot_state(self) -> str | None:
        """The robot's live on-device state (awake/sleep/focus/…), or None if unreadable."""
        getter = getattr(self.robot.driver, "get_text", None)
        if getter is None:
            return None
        try:
            return await getter("state_sensor")
        except Exception:  # noqa: BLE001 — a state read must never break a mode
            return None

    async def is_quiet(self) -> bool:
        """Do-not-disturb: the robot is asleep or in a calm mode — no autonomous faces,
        speech, LEDs or moves. Unknown/unreadable state → False (never over-suppress)."""
        return (await self.robot_state() or "").strip().lower() in QUIET_STATES

    async def is_asleep(self) -> bool:
        """The robot is effectively OFF (sleep / screensaver) — even foreground alerts hold."""
        return (await self.robot_state() or "").strip().lower() in ASLEEP_STATES


@dataclass
class ModeMeta:
    name: str
    description: str = ""
    kind: str = "foreground"  # foreground | ambient
    enabled: bool = True


class Mode(abc.ABC):
    """Base class for all modes. Subclass and implement the lifecycle hooks you need."""

    meta: ModeMeta

    def __init__(self, ctx: ModeContext) -> None:
        self.ctx = ctx

    async def on_enter(self) -> None:
        """Called when the mode becomes active."""

    async def on_exit(self) -> None:
        """Called when the mode is deactivated."""

    async def on_event(self, event: Event) -> None:
        """Called for every event on the bus while the mode is active."""

    async def tick(self) -> None:
        """Optional periodic hook (called by the engine on an interval)."""
