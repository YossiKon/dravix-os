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
import uuid
from typing import TYPE_CHECKING, Any, Callable

from .dal.base import CAP_FACE, CAP_SAY, RobotController
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
        for job in self._schedule():
            name = job.get("name") or job.get("at") or "?"
            if not daily_due(job, hhmm, now.weekday()):
                continue
            if self._fired.get(name) == today:
                continue
            self._fired[name] = today
            await self.run_action(job.get("action") or {}, {"name": name})
            await self._bus.publish("schedule.fired", job=name)

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
                await self.run_action(action or default, {"label": label})
            except asyncio.CancelledError:
                raise
            finally:
                self._timers.pop(timer_id, None)

        self._timers[timer_id] = asyncio.create_task(_fire(), name=f"dravix-timer-{timer_id}")
        return timer_id

    def cancel_timer(self, timer_id: str) -> bool:
        task = self._timers.pop(timer_id, None)
        if task is None:
            return False
        task.cancel()
        return True

    # ── shared action runner ────────────────────────────────────────────────────
    async def run_action(self, action: dict[str, Any], ctx: dict[str, Any]) -> None:
        robot = self._robot
        try:
            if action.get("face") and robot.supports(CAP_FACE):
                await robot.set_face(action["face"])
            if action.get("emote"):
                await play_emote(robot, action["emote"])
            if action.get("say") and robot.supports(CAP_SAY):
                await robot.say(str(action["say"]).format_map(_SafeDict(ctx)))
            if action.get("activate_mode") and self._engine is not None:
                await self._engine.activate(action["activate_mode"])
        except Exception as exc:  # noqa: BLE001 — a bad job must not kill the loop
            log.warning("scheduled action failed: %s", exc)
