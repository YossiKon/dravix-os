"""Mock robot driver — logs calls, performs no I/O. For offline dev and tests."""
from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .base import ALL_CAPABILITIES, Expression, RobotDriver

log = get_logger("dal.mock")


class MockDriver(RobotDriver):
    name = "mock"
    transport = "none"

    def __init__(self) -> None:
        self._connected = False
        self.last_voice: str | None = None

    async def connect(self) -> None:
        self._connected = True
        log.info("mock driver connected (no real robot)")

    async def close(self) -> None:
        self._connected = False

    async def capabilities(self) -> set[str]:
        return set(ALL_CAPABILITIES)

    async def set_face(self, expression: Expression) -> None:
        log.info("[mock] set_face(%s)", expression.value)

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        log.info("[mock] move_head(yaw=%.1f, pitch=%.1f, speed=%.2f)", yaw, pitch, speed)

    async def say(self, text: str, voice: str | None = None) -> None:
        self.last_voice = voice
        log.info("[mock] say(%r, voice=%s)", text, voice)

    async def set_leds(self, color: str, brightness: float = 1.0) -> None:
        log.info("[mock] set_leds(%s, %.2f)", color, brightness)

    async def take_photo(self) -> bytes | None:
        log.info("[mock] take_photo() -> None")
        return None

    async def listen(self, timeout: float = 7.0) -> str | None:
        log.info("[mock] listen(timeout=%.1f) -> ''", timeout)
        return ""

    async def show_image(self, image: bytes) -> None:
        log.info("[mock] show_image(%d bytes)", len(image))

    async def get_status(self) -> dict[str, Any]:
        return {"driver": self.name, "connected": self._connected}
