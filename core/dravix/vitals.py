"""Vitals / needs engine — the Tamagotchi "life" layer + wellness nudges.

Four needs (energy, food, fun, calm), each 0-100 where 100 = fully satisfied. They decay over
time and are topped up by actions (feed / rest / play / calm) from the dashboard, by petting/
talking, and — when a need bottoms out — by the robot itself (auto-eat, auto-sleep-till-rested).
Every change shows as real feedback: an emote (face + LEDs + head) + live bars on the robot's
own screen (page_vitals) and the web dashboard.

Plus WELLNESS NUDGES for whoever's working next to the robot: research-backed break reminders
(20-20-20 eye rule, Cornell 20-8-2 sit/stand/move, hydrate, posture, stretch). A tip pops on the
robot's screen and it wiggles so you notice.

THE HARD RULE: in a CALM firmware mode (focus / quiet / night / busy / sleep) the engine is
completely silent — no autonomy, no feedback, no nudges. Needs still decay quietly in the
background, but the robot does nothing on its own until it's back to `awake`. Focus = do-not-disturb.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable

import httpx

from .config import get_settings
from .dal.base import QUIET_STATES
from .emotes import play_emote
from .events import Event, EventBus
from .logging import get_logger

if TYPE_CHECKING:
    from .dal.base import RobotController
    from .integrations.homeassistant import HomeAssistant
    from .modes import ModeEngine
    from .store import Store

log = get_logger("vitals")

# Modes where the engine must stay SILENT (do-not-disturb) — the canonical set shared with
# mood + every plugin (via ModeContext.is_quiet). Any other/unknown state counts as active,
# so a new firmware mode never mutes the robot by accident. None/"" = mock → allow.
_QUIET_MODES = QUIET_STATES

# WELLNESS NUDGES have their own rule: focus = the user is DEFINITELY at the desk
# (work/gaming DND automations set it), which is exactly when the eye/move/water
# reminders matter — so nudges DO fire in focus (quietly: the firmware suppresses the
# wiggle/LED flash in calm modes, leaving just the on-screen bubble). They stay silent
# where the user probably ISN'T looking at the robot at all:
_NUDGE_QUIET_MODES = {"sleep", "night", "screensaver", "quiet", "busy"}

# Decay in points PER HOUR while awake (tunable). energy instead REFILLS while asleep.
_DECAY_PER_H = {"energy": 22.0, "food": 16.0, "fun": 28.0, "calm": 30.0}
_SLEEP_ENERGY_GAIN_PER_H = 240.0   # a full recharge in ~25 min of sleep
_CRITICAL = 6.0                    # a need at/under this triggers autonomy

# action -> (need it fills to 100, emote). "rest" is special (a nap; handled inline).
_ACTIONS = {"feed": ("food", "eat"), "play": ("fun", "play"), "calm": ("calm", "calm")}

# Bus interactions that also feed the needs a little (reused from the same events mood uses).
_NEED_NUDGES: dict[str, dict[str, float]] = {
    "touch.pet": {"fun": 12, "calm": 18},
    "touch.tap": {"fun": 6},
    "user.spoke": {"fun": 8, "calm": 4},
    "robot.touched": {"fun": 8, "calm": 6},
    "guard.alert": {"calm": -25},
    "ha.motion": {"calm": -4},
}

# Wellness nudges — key -> every_minutes. Intervals are the well-known desk-work guidance:
# 20-20-20 (eyes), Cornell 20-8-2 (stand/move ~every 30m), posture, hydration, stretch.
_NUDGE_INTERVALS_MIN: dict[str, float] = {
    "eyes": 20.0, "move": 30.0, "posture": 45.0, "water": 60.0, "stretch": 90.0,
}
# Tip texts per language (short, so they fit the on-screen bubble). Picked by the store's
# `language` override, else DRAVIX_LANG. The store's `wellness_tips` list replaces them all.
# ADDING A LANGUAGE = add one entry here (same keys); unknown codes fall back to "en".
_NUDGE_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "eyes":    "Eye break — look 20 seconds into the distance",
        "move":    "Stand up and move for 2 minutes",
        "posture": "Posture check — sit up straight",
        "water":   "Time to drink some water",
        "stretch": "Time for a stretch and a deep breath",
    },
    "he": {
        "eyes":    "מנוחה לעיניים — הבט 20 שניות למרחק",
        "move":    "קום וזוז 2 דקות",
        "posture": "בדוק יציבה — שב זקוף",
        "water":   "כדאי לשתות קצת מים",
        "stretch": "זמן למתיחה ונשימה עמוקה",
    },
}
_NUDGE_MIN_SPACING_S = 240.0  # never fire two tips within 4 minutes of each other


def _entity_missing(exc: Exception) -> bool:
    """True when a service call failed because the entity no longer exists (robot re-flashed /
    renamed) — the caller should drop its cached entity ids and re-resolve."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (400, 404)
    msg = str(exc).lower()
    return "not found" in msg or "not_found" in msg


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


class VitalsEngine:
    def __init__(
        self,
        bus: EventBus,
        controller: "RobotController",
        store: "Store | None" = None,
        engine: "ModeEngine | None" = None,
        ha: "HomeAssistant | None" = None,
        tick_interval: float = 20.0,
        nudge_interval: float = 30.0,
        discovered: "Callable[[], dict] | None" = None,
    ) -> None:
        self._bus = bus
        self._robot = controller
        self._store = store
        self._engine = engine
        self._ha = ha
        self._discovered = discovered  # lazy accessor to the auto-discovered entity map
        self._tick = tick_interval
        self._nudge_tick = nudge_interval
        self.energy = 80.0
        self.food = 80.0
        self.fun = 70.0
        self.calm = 80.0
        self._auto_slept = False
        self._last = time.monotonic()
        self._start_mono = time.monotonic()
        self._nudge_last: dict[str, float] = {}
        self._nudge_last_any = 0.0
        self._num_entities: dict[str, str] = {}   # need -> number.* entity id (device bars)
        self._tip_entity: str | None = None        # text.* entity for the on-screen tip
        self._pushed: dict[str, int] = {}
        self._tasks: list[asyncio.Task] = []
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        if self._store is None:
            return
        v = self._store.vitals()
        self.energy = float(v.get("energy", self.energy))
        self.food = float(v.get("food", self.food))
        self.fun = float(v.get("fun", self.fun))
        self.calm = float(v.get("calm", self.calm))
        self._auto_slept = bool(v.get("auto_slept", False))
        # catch up on decay for the wall-clock time we were off (best-effort, capped at 12h)
        saved = float(v.get("ts", 0.0))
        if saved:
            gap_h = min(12.0, max(0.0, (time.time() - saved) / 3600.0))
            for k in ("energy", "food", "fun", "calm"):
                setattr(self, k, _clamp(getattr(self, k) - _DECAY_PER_H[k] * gap_h))

    def _persist(self) -> None:
        if self._store is not None:
            self._store.set_vitals({
                "energy": round(self.energy, 1), "food": round(self.food, 1),
                "fun": round(self.fun, 1), "calm": round(self.calm, 1),
                "auto_slept": self._auto_slept, "ts": round(time.time(), 1),
            })

    def snapshot(self) -> dict[str, Any]:
        needs = {"energy": round(self.energy), "food": round(self.food),
                 "fun": round(self.fun), "calm": round(self.calm)}
        lowest = min(needs, key=lambda k: needs[k])
        nudges = self._store.nudges_enabled() if self._store is not None else True
        return {**needs, "lowest": lowest, "nudges": nudges}

    # ── runtime ──────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._pump(), name="dravix-vitals-pump"),
            asyncio.create_task(self._needs_ticker(), name="dravix-vitals-tick"),
            asyncio.create_task(self._nudge_ticker(), name="dravix-vitals-nudge"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

    def _active(self, mode: str | None) -> bool:
        """True when the robot may act on its own. Unknown mode (mock/no state sensor) → allow."""
        if mode is None or mode == "":
            return True
        return mode.strip().lower() not in _QUIET_MODES

    async def _user_present(self) -> bool:
        """Is someone actually at the desk? Uses the robot's "Presence nearby" sensor
        (proximity): present = ON now, or was ON within the last 15 minutes. No sensor
        discovered / read error → assume present (never silently starve the tips)."""
        entity = ((self._discovered() if self._discovered else {}) or {}).get("presence_sensor")
        if not entity or self._ha is None:
            return True
        try:
            st = await self._ha.get_state(entity)
        except Exception:  # noqa: BLE001
            return True
        if str(st.get("state")) == "on":
            return True
        changed = str(st.get("last_changed") or "")
        try:
            from datetime import datetime, timezone

            seen = datetime.fromisoformat(changed.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - seen).total_seconds() < 15 * 60
        except ValueError:
            return True

    async def _mode(self) -> str | None:
        getter = getattr(self._robot.driver, "get_text", None)
        if getter is None:
            return None
        try:
            return await getter("state_sensor")
        except Exception:  # noqa: BLE001
            return None

    async def _set_mode(self, mode: str) -> None:
        setter = getattr(self._robot.driver, "set_mode", None)
        if setter is None:
            return
        try:
            await setter(mode)
        except Exception:  # noqa: BLE001
            pass

    async def _emote(self, name: str, gated: bool = False) -> None:
        # gated = autonomous → skip if a foreground mode owns the face.
        if gated and self._engine is not None and self._engine.active is not None:
            return
        try:
            await play_emote(self._robot, name)
        except Exception:  # noqa: BLE001
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

    async def handle(self, event: Event) -> None:
        adj = _NEED_NUDGES.get(event.type)
        if not adj:
            return
        for need, d in adj.items():
            setattr(self, need, _clamp(getattr(self, need) + d))
        self._persist()

    async def _needs_ticker(self) -> None:
        while True:
            await asyncio.sleep(self._tick)
            try:
                now = time.monotonic()
                dt_h = (now - self._last) / 3600.0
                self._last = now
                mode = await self._mode()
                asleep = (mode or "").strip().lower() == "sleep"
                # decay always happens (silent) — energy refills while asleep
                if asleep:
                    self.energy = _clamp(self.energy + _SLEEP_ENERGY_GAIN_PER_H * dt_h)
                    for k in ("food", "fun", "calm"):
                        setattr(self, k, _clamp(getattr(self, k) - _DECAY_PER_H[k] * 0.3 * dt_h))
                else:
                    for k in ("energy", "food", "fun", "calm"):
                        setattr(self, k, _clamp(getattr(self, k) - _DECAY_PER_H[k] * dt_h))
                    if self._auto_slept:
                        # Woken mid-nap (mode select / a tap) — re-arm auto-napping. The flag
                        # used to stay latched (it's persisted!), so energy pinned at 0 and
                        # the robot never napped again until a manual "rest".
                        self._auto_slept = False
                await self._push_bars()
                # auto-wake from an AUTO nap once rested (a manual sleep is left alone)
                if asleep and self._auto_slept and self.energy >= 95.0:
                    self._auto_slept = False
                    await self._set_mode("awake")
                    await self._emote("wake", gated=True)
                # autonomy + feedback ONLY when active (awake/morning) — the HARD rule
                elif self._active(mode):
                    await self._autonomy()
                self._persist()
                await self._bus.publish("vitals.changed", **self.snapshot())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick must not kill the needs loop
                log.exception("vitals tick failed")

    async def _autonomy(self) -> None:
        """When a need bottoms out, the robot fixes it itself (only reached in an active mode)."""
        if self.energy <= _CRITICAL and not self._auto_slept:
            self._auto_slept = True           # nap until rested, then auto-wake
            await self._emote("yawn", gated=True)
            await self._set_mode("sleep")
            return
        if self.food <= _CRITICAL:
            self.food = 100.0
            await self._emote("eat", gated=True)
            return
        if self.fun <= _CRITICAL:
            self.fun = _clamp(self.fun + 45.0)
            await self._emote("play", gated=True)
            return
        if self.calm <= _CRITICAL:
            self.calm = _clamp(self.calm + 45.0)
            await self._emote("calm", gated=True)
            return

    async def satisfy(self, action: str) -> dict[str, Any]:
        """A user-initiated action from the dashboard — always runs + shows feedback."""
        if action == "rest":
            self._auto_slept = True           # a nap: refill energy + auto-wake when rested
            await self._emote("yawn")
            await self._set_mode("sleep")
        elif action in _ACTIONS:
            need, emote = _ACTIONS[action]
            setattr(self, need, 100.0)
            await self._emote(emote)
        else:
            raise ValueError(f"unknown action {action!r}")
        await self._push_bars()
        self._persist()
        await self._bus.publish("vitals.changed", **self.snapshot())
        return self.snapshot()

    # ── device screen (bars + tip) ─────────────────────────────────────────────
    async def _resolve_entities(self) -> None:
        if len(self._num_entities) >= 4 and self._tip_entity:
            return
        if self._ha is None:
            return
        try:
            states = await self._ha.states()
        except Exception:  # noqa: BLE001
            return
        # Match the vitals bars PRECISELY: a number whose object_id ends in _vital_<need>
        # (or is bare vital_<need>), then derive the device prefix from the first match so
        # the tip slot is resolved on the SAME device (<prefix>_tip / bare "tip") — not just
        # any text.*_tip in the house.
        found: dict[str, str] = {}
        prefix: str | None = None
        for s in states:
            eid = s.get("entity_id", "")
            if not eid.startswith("number."):
                continue
            object_id = eid.split(".", 1)[1]
            for need in ("energy", "food", "fun", "calm"):
                suffix = f"vital_{need}"
                if object_id == suffix or object_id.endswith("_" + suffix):
                    found.setdefault(need, eid)
                    if prefix is None:
                        prefix = object_id[: -len(suffix)].rstrip("_")
        if not found:
            return
        self._num_entities = found
        tip_object = f"{prefix}_tip" if prefix else "tip"
        for s in states:
            eid = s.get("entity_id", "")
            if eid.startswith("text.") and eid.split(".", 1)[1] == tip_object:
                self._tip_entity = eid
                break

    def _reset_entity_cache(self) -> None:
        """Forget the resolved entities (they vanished) — the next tick re-resolves."""
        self._num_entities = {}
        self._tip_entity = None
        self._pushed = {}

    async def _push_bars(self) -> None:
        if self._ha is None:
            return
        await self._resolve_entities()
        vals = {"energy": self.energy, "food": self.food, "fun": self.fun, "calm": self.calm}
        for need, ent in self._num_entities.items():
            v = int(round(vals[need]))
            if self._pushed.get(need) == v:
                continue
            try:
                await self._ha.call_service("number", "set_value", {"entity_id": ent, "value": v})
                self._pushed[need] = v
            except Exception as exc:  # noqa: BLE001
                if _entity_missing(exc):
                    self._reset_entity_cache()
                    return

    def _nudges(self) -> dict[str, tuple[float, str]]:
        """The active tip set — {key: (every_minutes, text)}.

        The store's ``wellness_tips`` (a non-empty list of strings) replaces the built-ins
        as-is, cycling through the default intervals. Otherwise the built-in tips are used
        in the configured language (store ``language`` override, else DRAVIX_LANG)."""
        intervals = list(_NUDGE_INTERVALS_MIN.values())
        custom = self._store.wellness_tips() if self._store is not None else []
        if custom:
            return {
                f"tip{i}": (intervals[i % len(intervals)], text)
                for i, text in enumerate(custom)
            }
        lang = (self._store.language() if self._store is not None else None) or \
            get_settings().language
        texts = _NUDGE_TEXTS.get((lang or "en").strip().lower(), _NUDGE_TEXTS["en"])
        return {k: (_NUDGE_INTERVALS_MIN[k], texts[k]) for k in _NUDGE_INTERVALS_MIN}

    async def _nudge_ticker(self) -> None:
        while True:
            await asyncio.sleep(self._nudge_tick)
            try:
                if self._store is not None and not self._store.nudges_enabled():
                    continue
                mode = await self._mode()
                if mode is not None and mode.strip().lower() in _NUDGE_QUIET_MODES:
                    continue          # user isn't at the robot — no reminders
                if not await self._user_present():
                    continue          # nobody at the desk (proximity) — save the tip
                now = time.monotonic()
                if now - self._nudge_last_any < _NUDGE_MIN_SPACING_S:
                    continue
                due: tuple[str, str] | None = None
                for key, (every_min, text) in self._nudges().items():
                    last = self._nudge_last.get(key, self._start_mono)
                    if now - last >= every_min * 60.0:
                        due = (key, text)
                        break
                if due is None:
                    continue
                key, text = due
                self._nudge_last[key] = now
                self._nudge_last_any = now
                # in focus the tip must be BUBBLE-ONLY: the dravix-side wiggle emote
                # drives the LEDs/head directly and would bypass the firmware's calm-mode
                # gates — so it only plays when the mode is fully active
                await self._fire_nudge(text, wiggle=self._active(mode))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick must not kill the tips forever
                log.exception("wellness nudge tick failed")

    async def _fire_nudge(self, text: str, wiggle: bool = True) -> None:
        if self._ha is not None:
            await self._resolve_entities()
            if self._tip_entity:
                from .bidi import for_robot

                try:
                    await self._ha.call_service(
                        "text", "set_value", {"entity_id": self._tip_entity, "value": for_robot(text)}
                    )
                except Exception as exc:  # noqa: BLE001
                    if _entity_missing(exc):
                        self._reset_entity_cache()
        if wiggle:
            await self._emote("nudge", gated=True)   # a little wiggle so you notice
        await self._bus.publish("vitals.nudge", text=text)
