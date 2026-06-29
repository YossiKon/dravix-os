"""Mode interface + the context object handed to every mode.

A *mode* is the unit of custom behavior ("Focus", "Pomodoro", "Companion", "Guard", ...).
Modes are plugins: they receive a ``ModeContext`` giving safe access to the robot, Home
Assistant, the AI router, the event bus, and per-mode config.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
