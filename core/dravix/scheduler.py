"""Scheduler — daily jobs + one-shot timers (the alarms/reminders a desk robot needs).

- **Daily jobs** live in the store (editable at runtime via ``/api/schedule``). Each has an
  ``at`` time (``HH:MM``), optional ``days`` (0=Mon..6=Sun), and an ``action`` (say / face /
  emote / activate_mode) — e.g. "08:00 → wake emote + say good morning".
- **Timers** are one-shot: set N seconds, it fires ``timer.done`` and runs an action.

The clock is injectable so the daily logic is unit-testable.
"""
from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable

from .dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, RobotController, robot_is_quiet
from .emotes import play_emote
from .events import EventBus
from .logging import get_logger

if TYPE_CHECKING:
    from .modes import ModeEngine
    from .store import Store

log = get_logger("scheduler")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def daily_due(job: dict[str, Any], now_hhmm: str, weekday: int) -> bool:
    """Pure: does this daily job match the current minute (ignoring the fired-once guard)?"""
    if not job.get("enabled", True) or job.get("at") != now_hhmm:
        return False
    days = job.get("days")
    return not days or weekday in days


class Scheduler:
    def __init__(
        self,
        bus: EventBus,
        controller: RobotController,
        store: "Store | None" = None,
        engine: "ModeEngine | None" = None,
        check_interval: float = 20.0,
        clock: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._bus = bus
        self._robot = controller
        self._store = store
        self._engine = engine
        self._check_interval = check_interval
        self._clock = clock or datetime.datetime.now
        self._fired: dict[str, str] = {}  # job name -> last date fired (once per day)
        self._timers: dict[str, asyncio.Task] = {}
        self._timer_meta: dict[str, dict[str, Any]] = {}  # id -> {label, ends} for listing
        self._task: asyncio.Task | None = None

    def _schedule(self) -> list[dict[str, Any]]:
        return self._store.schedule() if self._store is not None else []

    # ── runtime ────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="dravix-scheduler")

    async def stop(self) -> None:
        for t in (self._task, *self._timers.values()):
            if t:
                t.cancel()
        for t in (self._task, *list(self._timers.values())):
            if t:
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._check_interval)
                await self.check_daily()
        except asyncio.CancelledError:
            raise

    async def check_daily(self) -> None:
        now = self._clock()
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        await self._maybe_celebrate_birthday(today, hhmm)
        for job in self._schedule():
            name = job.get("name") or job.get("at") or "?"
            if not daily_due(job, hhmm, now.weekday()):
                continue
            if self._fired.get(name) == today:
                continue
            self._fired[name] = today
            await self.run_action(job.get("action") or {}, {"name": name})
            await self._bus.publish("schedule.fired", job=name)

    async def _maybe_celebrate_birthday(self, today: str, hhmm: str) -> None:
        """🎂 Once a year: on the first tick after 09:00 of the stored birthday (MM-DD),
        the robot celebrates — love face, party lights, and a spoken greeting in the
        configured language. Best-effort: a missing capability just skips its part."""
        bday = getattr(self._store, "birthday", lambda: "")() if self._store is not None else ""
        if not bday or today[5:] != bday or hhmm < "09:00":
            return
        if self._fired.get("__birthday__") == today:
            return
        self._fired["__birthday__"] = today
        from .config import get_settings
        from .dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression

        robot = self._robot
        try:
            if robot.supports(CAP_FACE):
                await robot.set_face(Expression.LOVE)
            if robot.supports(CAP_LEDS):
                # party lights, not permanent lighting — return to normal after the moment
                await robot.flash_leds("purple", 0.9, revert_s=10.0)
            # the dashboard's live language toggle (store) wins over the add-on option
            lang = (
                getattr(self._store, "language", lambda: None)() if self._store is not None else None
            ) or get_settings().language
            line = (
                "יום הולדת שמח! חוגגים אותך היום 🎂"
                if (lang or "en").startswith("he")
                else "Happy birthday! Today we're celebrating you 🎂"
            )
            if robot.supports(CAP_SAY):
                await robot.say(line, proactive=True)
        except Exception:  # noqa: BLE001 — a party must never crash the scheduler
            pass
        await self._bus.publish("birthday.celebrated", date=today)

    # ── timers ─────────────────────────────────────────────────────────────────
    async def set_timer(
        self, seconds: float, label: str = "", action: dict[str, Any] | None = None
    ) -> str:
        timer_id = uuid.uuid4().hex[:8]

        async def _fire() -> None:
            try:
                await asyncio.sleep(seconds)
                await self._bus.publish("timer.done", label=label, id=timer_id)
                default = {"say": f"{label or 'Timer'} done."}
                # a timer is something the user explicitly set — it must ring even when the
                # "speaks on its own" mute is on (that mute is for ambient chatter, not alerts).
                await self.run_action(action or default, {"label": label}, proactive=False)
            except asyncio.CancelledError:
                raise
            finally:
                self._timers.pop(timer_id, None)
                self._timer_meta.pop(timer_id, None)

        self._timer_meta[timer_id] = {"label": label, "ends": time.time() + seconds}
        self._timers[timer_id] = asyncio.create_task(_fire(), name=f"dravix-timer-{timer_id}")
        return timer_id

    def cancel_timer(self, timer_id: str) -> bool:
        task = self._timers.pop(timer_id, None)
        self._timer_meta.pop(timer_id, None)
        if task is None:
            return False
        task.cancel()
        return True

    def list_timers(self) -> list[dict[str, Any]]:
        """The running one-shot timers, newest first, with seconds remaining."""
        now = time.time()
        out = [
            {
                "id": tid,
                "label": meta.get("label", ""),
                "seconds_left": max(0, round(float(meta.get("ends", now)) - now)),
            }
            for tid, meta in self._timer_meta.items()
        ]
        out.sort(key=lambda t: t["seconds_left"])
        return out

    # ── shared action runner ────────────────────────────────────────────────────
    async def run_action(
        self, action: dict[str, Any], ctx: dict[str, Any], *, proactive: bool = True
    ) -> None:
        """Run a scheduled action's flourishes. ``proactive`` (default True — a scheduled
        announcement is ambient) is False for user-set timer alerts so they ring through the
        "speaks on its own" mute."""
        robot = self._robot
        try:
            # DND: face/LED/motion/speech flourishes respect the robot's quiet modes (a
            # job may opt out with "respect_quiet": false). MODE changes are exempt —
            # that's how the day schedule puts it to sleep and wakes it in the first place.
            quiet = bool(action.get("respect_quiet", True)) and await robot_is_quiet(robot)
            if action.get("face") and not quiet and robot.supports(CAP_FACE):
                await robot.set_face(action["face"])
            if action.get("leds") and not quiet and robot.supports(CAP_LEDS):
                leds = action["leds"]
                # scheduled colour = a moment's accent, not permanent lighting — auto-reverts
                await robot.flash_leds(leds.get("color", "white"), float(leds.get("brightness", 1.0)))
            if action.get("head") and not quiet and robot.supports(CAP_HEAD):
                yaw, pitch = action["head"]
                await robot.move_head(float(yaw), float(pitch))
            if action.get("emote") and not quiet:
                await play_emote(robot, action["emote"], proactive=proactive)
            # the robot's ON-DEVICE mode (awake/morning/focus/quiet/night/sleep) — this
            # is what the dashboard's Day-Schedule rows use ("07:30 morning, 23:00 sleep")
            if action.get("mode"):
                setter = getattr(robot.driver, "set_mode", None)
                if setter is not None:
                    await setter(str(action["mode"]))
            if action.get("say") and not quiet and robot.supports(CAP_SAY):
                await robot.say(str(action["say"]).format_map(_SafeDict(ctx)), proactive=proactive)
            if action.get("activate_mode") and self._engine is not None:
                await self._engine.activate(action["activate_mode"])
        except Exception as exc:  # noqa: BLE001 — a bad job must not kill the loop
            log.warning("scheduled action failed: %s", exc)
