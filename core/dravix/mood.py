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
import random
import time
from typing import TYPE_CHECKING, Any

from .dal.base import CAP_FACE, CAP_SAY, QUIET_STATES, Expression, RobotController
from .emotes import play_emote
from .events import Event, EventBus
from .logging import get_logger

if TYPE_CHECKING:
    from .modes import ModeEngine
    from .store import Store

log = get_logger("mood")

# event type -> (d_valence, d_arousal, d_affection, emote_on_fire | None)
_NUDGES: dict[str, tuple[float, float, float, str | None]] = {
    "robot.say": (0.02, 0.05, 0.03, None),
    "user.spoke": (0.08, 0.10, 0.05, None),
    "touch.pet": (0.25, 0.15, 0.20, "love"),
    "touch.tap": (0.05, 0.20, 0.02, "curious"),
    "robot.touched": (0.10, 0.15, 0.10, "happy"),
    "guard.alert": (-0.10, 0.40, 0.00, None),
    "ha.motion": (0.00, 0.15, 0.00, None),
    "presence.detected": (0.02, 0.10, 0.02, None),
    "frigate.shown": (-0.02, 0.20, 0.00, None),
}
_INTERACTIONS = {"user.spoke", "touch.pet", "touch.tap", "robot.touched"}

# Little things it says on its own when bored (the "alive" idle behavior) — in the
# USER'S language (dashboard toggle wins) and varied by time of day, so 8am and 23:00
# don't sound the same.
_IDLE_QUIPS: dict[str, dict[str, list[str]]] = {
    "en": {
        "morning": ["Morning! Ready when you are.", "Fresh day, fresh circuits.", "*stretches* okay, today we thrive."],
        "day": ["Hmm, quiet in here.", "I'm here whenever you need me.", "Just thinking.", "*hums quietly*", "Anyone around?"],
        "evening": ["Cozy evening, huh?", "*yawns a little*", "Evenings are nice and quiet.", "I'm here if you need anything."],
    },
    "he": {
        "morning": ["בוקר! מוכן כשאתה מוכן.", "יום חדש, מעגלים רעננים.", "*מתמתח* קדימה, יום חדש."],
        "day": ["הממ, שקט פה.", "אני כאן אם צריך אותי.", "סתם חושב לעצמי.", "*מזמזם בשקט*", "יש מישהו בסביבה?"],
        "evening": ["ערב נעים, אה?", "*מפהק קצת*", "ערבים זה זמן טוב לשקט.", "אני פה אם תצטרך משהו."],
    },
}
_QUIP_MIN_GAP_S = 600.0  # a bored robot may be cute, not chatty — one quip per 10 min tops


def _pick_quip(lang: str) -> str:
    import datetime

    hour = datetime.datetime.now().hour
    slot = "morning" if 5 <= hour < 12 else "day" if 12 <= hour < 18 else "evening"
    table = _IDLE_QUIPS["he" if (lang or "").startswith("he") else "en"]
    return random.choice(table.get(slot) or table["day"])


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
        self._persisted: tuple[float, float, float] | None = None
        self._last_quip = 0.0
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
        if self._store is None:
            return
        # Skip the disk write when nothing moved meaningfully — the ticker calls this every
        # 15s and a synchronous save per tick is needless flash wear on a small HA box.
        snap = (round(self.valence, 2), round(self.arousal, 2), round(self.affection, 2))
        if snap == self._persisted:
            return
        self._persisted = snap
        self._store.set_mood(
            {"valence": self.valence, "arousal": self.arousal, "affection": self.affection}
        )

    # ── derived ────────────────────────────────────────────────────────────────
    def label(self) -> str:
        # Thresholds MATCH expression() below — the dashboard's mood text and the face must
        # never contradict each other ("happy" text over a neutral face).
        if self._night and self.arousal < 0.4:
            return "sleepy"
        if self.valence > 0.35 and self.arousal > 0.55:
            return "excited"
        if self.valence > 0.35:
            return "happy"
        if self.valence < -0.35:
            return "sad"
        if self.arousal < 0.2:
            return "bored"
        return "content" if self.valence >= 0 else "down"

    def expression(self) -> Expression:
        # Symmetric thresholds: happy needs a clearly positive mood, sad needs a clearly
        # negative one — reachable by real interaction (a pet is +0.25), but neither is the
        # steady state (decay + the bounded boredom drift both settle inside ±0.35).
        if self._night and self.arousal < 0.4:
            return Expression.SLEEPY
        if self.valence > 0.35:
            return Expression.HAPPY
        if self.valence < -0.4 and self.arousal > 0.55:
            return Expression.ANGRY
        if self.valence < -0.35:
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
                event = await q.get()
                try:
                    await self.handle(event)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 — one bad event must not kill the pump
                    log.exception("mood event handling failed (%s)", event.type)
        except asyncio.CancelledError:
            raise
        finally:
            self._bus.unsubscribe(q)

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(self._tick)
            try:
                self.valence *= 1 - self._decay
                self.arousal += (0.3 - self.arousal) * self._decay
                if time.monotonic() - self._last_interaction > self._idle_bored_s:
                    # Boredom nudges the mood down but is FLOORED well above the sad
                    # threshold — being ignored makes it wistful, not permanently
                    # miserable (unbounded drift used to pin the face on SAD forever).
                    if self.valence > -0.25:
                        self.valence = max(self.valence - 0.03, -0.25)
                    self.arousal = _clamp(self.arousal - 0.02, 0, 1)
                    if not self._night and random.random() < 0.2:
                        await self.idle_behavior()  # do something cute on its own
                if self._night:
                    self.arousal = _clamp(self.arousal - 0.03, 0, 1)
                await self._express()
                self._persist()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick must not kill the mood forever
                log.exception("mood tick failed")

    def _locked(self) -> bool:
        # A foreground mode owns the face; don't override it with mood.
        return self._engine is not None and self._engine.active is not None

    async def _dnd(self) -> bool:
        """The robot's ON-DEVICE do-not-disturb states — the same hard rule vitals
        follows: mood must not push faces or play quips in sleep / calm modes /
        the screensaver (a face push also flashes LEDs and poses the head there)."""
        getter = getattr(self._robot.driver, "get_text", None)
        if getter is None:
            return False
        try:
            state = await getter("state_sensor")
        except Exception:  # noqa: BLE001
            return False
        return (state or "").strip().lower() in QUIET_STATES

    async def _express(self, force: bool = False) -> None:
        if self._locked() or await self._dnd():
            return
        expr = self.expression()
        # Compare against what's ACTUALLY on the face (controller state) — emotes, agent
        # status, reactions and the dashboard all write the face too, and comparing a
        # private cache let their face stick forever (mood could never reclaim it).
        current = getattr(self._robot.state, "expression", None)
        if not force and current == expr.value:
            return
        if self._robot.supports(CAP_FACE):
            try:
                await self._robot.set_face(expr)
            except Exception:  # noqa: BLE001 — a blip is retried on the next tick
                pass

    async def idle_behavior(self) -> None:
        """A small spontaneous behavior when bored (skipped if a mode owns the face, or if
        the robot's autonomous idle motion is switched off)."""
        if self._locked() or await self._dnd():
            return
        if not getattr(self._robot, "idle_motion", True):
            return  # idle motion off → stay still & quiet (e.g. the firmware owns idle life)
        if time.monotonic() - self._last_quip < _QUIP_MIN_GAP_S:
            return  # bored ≠ chatty — cap the self-talk
        self._last_quip = time.monotonic()
        try:
            await play_emote(self._robot, "curious")
            if self._robot.supports(CAP_SAY):
                lang = ""
                if self._store is not None:
                    try:
                        lang = self._store.language() or ""
                    except Exception:  # noqa: BLE001
                        pass
                if not lang:
                    from .config import get_settings

                    lang = get_settings().language or "en"
                await self._robot.say(_pick_quip(lang))
        except Exception:  # noqa: BLE001
            pass
        await self._bus.publish("mood.idle")

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
        if event.type == "touch.pet":
            # the BOND shows: a robot still warming up is curious about pets, a bonded
            # one melts — two robots raised differently feel different to pet.
            emote = "curious" if self.affection < 0.3 else ("happy" if self.affection < 0.7 else "love")
        if emote and not self._locked():
            try:
                await play_emote(self._robot, emote)
            except Exception:  # noqa: BLE001
                pass
            # the emote's face IS the reaction — don't stomp it with a forced mood face
            # (the ♥ pet-face used to vanish ~0.3s in); the next tick reclaims naturally.
        else:
            await self._express()
        self._persist()
        await self._bus.publish("mood.changed", **self.snapshot())
