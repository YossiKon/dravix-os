"""Pomodoro timer mode.

Drives the robot through work/break cycles. Uses the engine's periodic ``tick`` to advance,
so it needs no threads of its own. All robot actions are capability-guarded, so it runs fine
on the mock driver (and later, unchanged, on the real robot).
"""
from __future__ import annotations

import time

from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.modes import Mode, ModeMeta


class PomodoroMode(Mode):
    meta = ModeMeta(name="pomodoro", description="Work/break timer", kind="foreground")

    async def on_enter(self) -> None:
        self._phase = "work"
        self._work_s = float(self.ctx.config.get("work_minutes", 25)) * 60
        self._break_s = float(self.ctx.config.get("break_minutes", 5)) * 60
        self._deadline = time.monotonic() + self._work_s
        await self._announce_phase("Let's focus. 25 minutes, starting now.")

    async def on_exit(self) -> None:
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.NEUTRAL)

    async def tick(self) -> None:
        if time.monotonic() < self._deadline:
            return
        if self._phase == "work":
            self._phase = "break"
            self._deadline = time.monotonic() + self._break_s
            await self._announce_phase("Nice work! Take a short break.")
        else:
            self._phase = "work"
            self._deadline = time.monotonic() + self._work_s
            await self._announce_phase("Break's over. Back to it.")

    async def _announce_phase(self, line: str) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.HAPPY if self._phase == "break" else Expression.NEUTRAL)
        if robot.supports(CAP_LEDS):
            color = cfg.get("break_color" if self._phase == "break" else "work_color", "blue")
            await robot.set_leds(color, 0.5)
        if robot.supports(CAP_SAY):
            await robot.say(line)
        await self.ctx.bus.publish("pomodoro.phase", phase=self._phase)
        self.ctx.log.info("pomodoro -> %s", self._phase)

    def remaining_seconds(self) -> int:
        return max(0, int(self._deadline - time.monotonic()))
