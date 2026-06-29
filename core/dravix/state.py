"""Live runtime state, exposed to the dashboard and modes."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RobotState:
    online: bool = False
    driver: str = "mock"
    transport: str = ""
    capabilities: list[str] = field(default_factory=list)
    expression: str = "neutral"
    head_yaw: float = 0.0
    head_pitch: float = 0.0
    last_said: str = ""
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass
class RuntimeState:
    robot: RobotState = field(default_factory=RobotState)
    active_mode: str | None = None
    ambient_modes: list[str] = field(default_factory=list)
    ai_provider: str = "ha_assist"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
