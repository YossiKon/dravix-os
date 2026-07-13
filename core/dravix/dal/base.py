"""Device Abstraction Layer (DAL).

Everything above the DAL talks to a single ``RobotController`` interface. Concrete
``RobotDriver`` implementations (MCP / Home Assistant / mock) provide the actual transport.
This is what lets us swap *how* the robot is reached without touching modes, AI, or the UI.
"""
from __future__ import annotations

import abc
import asyncio
from enum import Enum
from typing import Any

from ..events import EventBus
from ..logging import get_logger
from ..state import RobotState

log = get_logger("dal")


class Expression(str, Enum):
    """Canonical emotions (mirrors m5stack-avatar's expression set + its decorators)."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SLEEPY = "sleepy"
    DOUBT = "doubt"
    LOVE = "love"
    DIZZY = "dizzy"

    @classmethod
    def coerce(cls, value: "Expression | str") -> "Expression":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.NEUTRAL


# Capability names a driver may advertise.
CAP_FACE = "set_face"
CAP_HEAD = "move_head"
CAP_SAY = "say"
CAP_LEDS = "set_leds"
CAP_PHOTO = "take_photo"
CAP_LISTEN = "listen"
CAP_DISPLAY = "show_image"  # push a JPEG to the robot's screen (e.g. a Frigate snapshot)
ALL_CAPABILITIES = (CAP_FACE, CAP_HEAD, CAP_SAY, CAP_LEDS, CAP_PHOTO, CAP_LISTEN, CAP_DISPLAY)

# ── canonical robot-state names (published by the firmware's "State" sensor) ──────────
# The ONE source of truth for do-not-disturb gating, shared by vitals, mood and every
# mode (via ModeContext.is_quiet). Any OTHER/unknown state counts as active, so a new
# firmware state can never accidentally mute the robot.
#   QUIET_STATES  — no autonomous faces / speech / LEDs / head moves belong here.
#   ASLEEP_STATES — the robot is effectively OFF; even deliberate foreground alerts hold.
QUIET_STATES = frozenset({"sleep", "night", "screensaver", "quiet", "focus", "busy"})
ASLEEP_STATES = frozenset({"sleep", "screensaver"})


async def robot_is_quiet(controller: "RobotController") -> bool:
    """The ONE do-not-disturb check, shared by mood / vitals / agents / reactions /
    scheduler: True when the robot's own state sensor reports a QUIET state. An
    unknown or unreadable state counts as ACTIVE (mock/tests stay unchanged, and a
    new firmware state can never accidentally mute the robot)."""
    getter = getattr(controller.driver, "get_text", None)
    if getter is None:
        return False
    try:
        state = await getter("state_sensor")
    except Exception:  # noqa: BLE001 — can't tell → treat as active
        return False
    return (state or "").strip().lower() in QUIET_STATES


class RobotDriver(abc.ABC):
    """Backend that knows how to physically talk to the robot."""

    name: str = "base"
    transport: str = ""

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    async def capabilities(self) -> set[str]:
        """Return the set of CAP_* verbs this backend actually supports."""

    @abc.abstractmethod
    async def set_face(self, expression: Expression) -> None: ...

    @abc.abstractmethod
    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None: ...

    @abc.abstractmethod
    async def say(self, text: str, voice: str | None = None) -> None: ...

    @abc.abstractmethod
    async def set_leds(self, color: str, brightness: float = 1.0) -> None: ...

    @abc.abstractmethod
    async def take_photo(self) -> bytes | None: ...

    @abc.abstractmethod
    async def listen(self, timeout: float = 7.0) -> str | None: ...

    @abc.abstractmethod
    async def show_image(self, image: bytes) -> None:
        """Display a JPEG image (raw bytes) on the robot's screen."""

    @abc.abstractmethod
    async def get_status(self) -> dict[str, Any]: ...

    async def raw_call(self, action: str, **kwargs: Any) -> Any:
        """Escape hatch for backend-specific actions not covered by the interface."""
        raise NotImplementedError(f"{self.name} driver has no raw_call for {action!r}")


class CapabilityError(RuntimeError):
    """Raised when a verb is requested that the active backend does not support."""


class RobotController:
    """Facade used by the rest of the app.

    Wraps a driver to add capability guards, shared state, and event emission so callers
    never touch a driver directly.
    """

    def __init__(self, driver: RobotDriver, bus: EventBus, state: RobotState) -> None:
        self._driver = driver
        self._bus = bus
        self.state = state
        self._caps: set[str] = set()
        self.default_voice: str | None = None  # applied to say() when no explicit voice given
        # When False, ambient/idle behaviors skip moving the head (manual control still works).
        self.idle_motion: bool = True
        # Short cache for the Privacy switch (see is_private) so the camera stream doesn't
        # re-read HA every frame.
        self._priv_val: bool = False
        self._priv_at: float = 0.0
        # Pending auto-revert of a flash_leds() call (cancelled by any newer LED write),
        # plus a generation counter so an already-detached revert can never darken a
        # colour that was deliberately set after its flash.
        self._led_revert: asyncio.Task | None = None
        self._led_gen: int = 0

    async def connect(self) -> None:
        await self._driver.connect()
        self._caps = await self._driver.capabilities()
        self.state.online = True
        self.state.driver = self._driver.name
        self.state.transport = self._driver.transport
        self.state.capabilities = sorted(self._caps)
        self.state.touch()
        await self._bus.publish("robot.connected", driver=self._driver.name, caps=sorted(self._caps))
        log.info("robot connected via %s (caps: %s)", self._driver.name, sorted(self._caps))

    async def close(self) -> None:
        await self._driver.close()
        self.state.online = False
        self.state.touch()
        await self._bus.publish("robot.disconnected")

    @property
    def driver(self) -> RobotDriver:
        return self._driver

    async def reconnect_with(self, driver: RobotDriver) -> None:
        """Swap in a freshly-built driver (e.g. after the dashboard changes the wiring) and
        reconnect. Raises on connect failure — the caller records it in state.last_error."""
        try:
            await self._driver.close()
        except Exception:  # noqa: BLE001 — old driver may already be dead
            pass
        self._driver = driver
        self._caps = set()
        self.state.online = False
        self.state.last_error = ""
        await self.connect()

    def supports(self, cap: str) -> bool:
        return cap in self._caps

    def _require(self, cap: str) -> None:
        if cap not in self._caps:
            raise CapabilityError(f"active backend ({self._driver.name}) does not support {cap!r}")

    async def set_face(self, expression: Expression | str) -> None:
        self._require(CAP_FACE)
        expr = Expression.coerce(expression)
        await self._driver.set_face(expr)
        self.state.expression = expr.value
        self.state.touch()
        await self._bus.publish("robot.face", expression=expr.value)

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        self._require(CAP_HEAD)
        await self._driver.move_head(yaw, pitch, speed)
        self.state.head_yaw, self.state.head_pitch = yaw, pitch
        self.state.touch()
        await self._bus.publish("robot.head", yaw=yaw, pitch=pitch)

    async def say(self, text: str, voice: str | None = None) -> None:
        self._require(CAP_SAY)
        await self._driver.say(text, voice or self.default_voice)
        self.state.last_said = text
        self.state.touch()
        await self._bus.publish("robot.say", text=text)

    async def set_leds(self, color: str, brightness: float = 1.0) -> None:
        await self._set_leds(color, brightness)

    async def _set_leds(self, color: str, brightness: float) -> int:
        """The one real LED write. Returns the write's generation — a newer LED intent
        always wins, and any revert task from an older generation must no-op."""
        self._require(CAP_LEDS)
        self._led_gen += 1
        gen = self._led_gen
        if self._led_revert is not None and not self._led_revert.done():
            self._led_revert.cancel()
            self._led_revert = None
        await self._driver.set_leds(color, brightness)
        await self._bus.publish("robot.leds", color=color, brightness=brightness)
        return gen

    async def flash_leds(self, color: str, brightness: float = 1.0, revert_s: float = 4.0) -> None:
        """A decorative LED pulse, not a state: light up, then auto-OFF after ``revert_s``.

        This is what reactions / scheduled actions / notifications / agent pulses use —
        the LED bar always returns to itself a few seconds later, so nothing can leave it
        burning. Deliberate LED choices (the dashboard picker) use set_leds and persist."""
        gen = await self._set_leds(color, brightness)

        async def _revert() -> None:
            try:
                await asyncio.sleep(revert_s)
                if gen != self._led_gen:
                    return  # a newer LED write took over — leave its colour alone
                self._led_revert = None  # our own turn-off must not cancel itself
                await self.set_leds("off", 0.0)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

        self._led_revert = asyncio.create_task(_revert(), name="dravix-led-revert")

    def invalidate_privacy(self) -> None:
        """Drop the privacy cache so the next is_private() re-reads immediately — call this
        the instant privacy is toggled (e.g. the dashboard PUT) to close the ~1.5s window
        where the camera would otherwise still serve frames after Privacy goes ON."""
        self._priv_at = 0.0

    async def is_private(self) -> bool:
        """True while the robot's Privacy switch is ON. Cached ~1.5s so the camera stream
        can check it every frame without hammering Home Assistant."""
        reader = getattr(self._driver, "is_private", None)
        if reader is None:
            return False
        import time as _time

        now = _time.monotonic()
        if now - self._priv_at < 1.5:
            return self._priv_val
        try:
            self._priv_val = bool(await reader())
        except Exception:  # noqa: BLE001 — an unreadable switch must not brick the camera
            self._priv_val = False
        self._priv_at = now
        return self._priv_val

    async def take_photo(self) -> bytes | None:
        self._require(CAP_PHOTO)
        # Privacy is enforced HERE, at the one choke point every capture funnels through
        # (security snapshots, the photo ritual, the MJPEG stream) — so Privacy mode means
        # the camera yields NOTHING, no matter who asks.
        if await self.is_private():
            return None
        return await self._driver.take_photo()

    async def listen(self, timeout: float = 7.0) -> str | None:
        self._require(CAP_LISTEN)
        if await self.is_private():  # Privacy mode = no microphone, period
            return None
        return await self._driver.listen(timeout)

    async def show_image(self, image: bytes) -> None:
        self._require(CAP_DISPLAY)
        await self._driver.show_image(image)
        await self._bus.publish("robot.image", bytes=len(image))

    async def get_status(self) -> dict[str, Any]:
        return await self._driver.get_status()

    async def raw_call(self, action: str, **kwargs: Any) -> Any:
        return await self._driver.raw_call(action, **kwargs)
