"""Mood / personality engine — the "alive" desk-robot layer (EMO/Vector style).

Keeps a small persistent affective state — **valence** (how positive, -1..1), **arousal**
(how energetic, 0..1) and **affection** (bond, 0..1). It drifts back toward baseline over time,
is nudged by what happens (being talked to, petted, motion, night), and *shows on the face*
when no foreground mode owns the screen. Explicit interactions (a pet, a tap) trigger an emote.

Personality carries across restarts via the store. Touch events (``touch.pet`` etc.) come from
the robot once its touch channel is wired; until then drive them with ``POST /api/robot/interact``.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from .dal.base import CAP_FACE, Expression, RobotController
from .emotes import play_emote
from .events import Event, EventBus
from .logging import get_logger

if TYPE_CHECKING:
    from .modes import ModeEngine
    from .store import Store

log = get_logger("mood")

# event type -> (d_valence, d_arousal, d_affection, emote_on_fire | None)
_NUDGES: dict[str, tuple[float, float, float, str | None]] = {
    "robot.say": (0.05, 0.05, 0.03, None),
    "user.spoke": (0.08, 0.10, 0.05, None),
    "touch.pet": (0.25, 0.15, 0.20, "love"),
    "touch.tap": (0.05, 0.20, 0.02, "curious"),
    "robot.touched": (0.10, 0.15, 0.10, "happy"),
    "guard.alert": (-0.10, 0.40, 0.00, None),
    "ha.motion": (0.00, 0.15, 0.00, None),
    "presence.detected": (0.05, 0.10, 0.02, None),
    "frigate.shown": (-0.02, 0.20, 0.00, None),
}
_INTERACTIONS = {"user.spoke", "touch.pet", "touch.tap", "robot.touched"}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class MoodEngine:
    def __init__(
        self,
        bus: EventBus,
        controller: RobotController,
        store: "Store | None" = None,
        engine: "ModeEngine | None" = None,
        tick_interval: float = 15.0,
        decay: float = 0.05,
        idle_bored_s: float = 600.0,
    ) -> None:
        self._bus = bus
        self._robot = controller
        self._store = store
        self._engine = engine
        self._tick = tick_interval
        self._decay = decay
        self._idle_bored_s = idle_bored_s
        self.valence = 0.0
        self.arousal = 0.3
        self.affection = 0.3
        self._night = False
        self._last_interaction = time.monotonic()
        self._last_expr: Expression | None = None
        self._tasks: list[asyncio.Task] = []
        self._load()

    # ── persistence ────────────────────────────────────────────────────────────
    def _load(self) -> None:
        if self._store is None:
            return
        m = self._store.mood()
        self.valence = float(m.get("valence", self.valence))
        self.arousal = float(m.get("arousal", self.arousal))
        self.affection = float(m.get("affection", self.affection))

    def _persist(self) -> None:
        if self._store is not None:
            self._store.set_mood(
                {"valence": self.valence, "arousal": self.arousal, "affection": self.affection}
            )

    # ── derived ────────────────────────────────────────────────────────────────
    def label(self) -> str:
        if self._night and self.arousal < 0.4:
            return "sleepy"
        if self.valence > 0.3 and self.arousal > 0.55:
            return "excited"
        if self.valence > 0.25:
            return "happy"
        if self.valence < -0.3:
            return "sad"
        if self.arousal < 0.2:
            return "bored"
        return "content" if self.valence >= 0 else "down"

    def expression(self) -> Expression:
        if self._night and self.arousal < 0.4:
            return Expression.SLEEPY
        if self.valence > 0.25:
            return Expression.HAPPY
        if self.valence < -0.3 and self.arousal > 0.55:
            return Expression.ANGRY
        if self.valence < -0.2:
            return Expression.SAD
        if self.arousal < 0.2:
            return Expression.SLEEPY
        return Expression.NEUTRAL

    def snapshot(self) -> dict[str, Any]:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "affection": round(self.affection, 3),
            "mood": self.label(),
            "expression": self.expression().value,
        }

    # ── runtime ────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._pump(), name="dravix-mood-pump"),
            asyncio.create_task(self._ticker(), name="dravix-mood-tick"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _pump(self) -> None:
        q = self._bus.subscribe()
        try:
            while True:
                await self.handle(await q.get())
        except asyncio.CancelledError:
            raise
        finally:
            self._bus.unsubscribe(q)

    async def _ticker(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick)
                self.valence *= 1 - self._decay
                self.arousal += (0.3 - self.arousal) * self._decay
                if time.monotonic() - self._last_interaction > self._idle_bored_s:
                    self.valence = _clamp(self.valence - 0.03, -1, 1)
                    self.arousal = _clamp(self.arousal - 0.02, 0, 1)
                if self._night:
                    self.arousal = _clamp(self.arousal - 0.03, 0, 1)
                await self._express()
                self._persist()
        except asyncio.CancelledError:
            raise

    def _locked(self) -> bool:
        # A foreground mode owns the face; don't override it with mood.
        return self._engine is not None and self._engine.active is not None

    async def _express(self, force: bool = False) -> None:
        if self._locked():
            return
        expr = self.expression()
        if not force and expr is self._last_expr:
            return
        self._last_expr = expr
        if self._robot.supports(CAP_FACE):
            try:
                await self._robot.set_face(expr)
            except Exception:  # noqa: BLE001
                pass

    async def handle(self, event: Event) -> None:
        if event.type == "daynight.changed":
            self._night = bool(event.data.get("night"))
            await self._express()
            return
        nudge = _NUDGES.get(event.type)
        if nudge is None:
            return
        dv, da, daf, emote = nudge
        self.valence = _clamp(self.valence + dv, -1.0, 1.0)
        self.arousal = _clamp(self.arousal + da, 0.0, 1.0)
        self.affection = _clamp(self.affection + daf, 0.0, 1.0)
        if event.type in _INTERACTIONS:
            self._last_interaction = time.monotonic()
        if emote and not self._locked():
            try:
                await play_emote(self._robot, emote)
            except Exception:  # noqa: BLE001
                pass
        await self._express(force=bool(emote))
        self._persist()
        await self._bus.publish("mood.changed", **self.snapshot())
