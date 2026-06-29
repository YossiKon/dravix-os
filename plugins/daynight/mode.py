"""Day/night ambient mood.

Checks the local hour on each tick; at night the robot looks sleepy with warm dim LEDs, by
day it relaxes to neutral. Only acts on transitions, so it won't fight other modes every tick.
"""
from __future__ import annotations

import datetime

from dravix.dal.base import CAP_FACE, CAP_LEDS, Expression
from dravix.modes import Mode, ModeMeta


class DayNightMode(Mode):
    meta = ModeMeta(name="daynight", description="Day/night mood", kind="ambient")

    async def on_enter(self) -> None:
        self._night_start = int(self.ctx.config.get("night_start", 22))
        self._night_end = int(self.ctx.config.get("night_end", 7))
        self._last: bool | None = None
        await self._apply()

    async def tick(self) -> None:
        await self._apply()

    def _is_night(self, hour: int) -> bool:
        start, end = self._night_start, self._night_end
        if start > end:  # window wraps past midnight (e.g. 22 -> 7)
            return hour >= start or hour < end
        return start <= hour < end

    async def _apply(self) -> None:
        night = self._is_night(datetime.datetime.now().hour)
        if night == self._last:
            return
        self._last = night
        robot = self.ctx.robot
        if night:
            if robot.supports(CAP_FACE):
                await robot.set_face(Expression.SLEEPY)
            if robot.supports(CAP_LEDS):
                await robot.set_leds("amber", 0.1)
        else:
            if robot.supports(CAP_FACE):
                await robot.set_face(Expression.NEUTRAL)
            if robot.supports(CAP_LEDS):
                await robot.set_leds("white", 0.3)
        await self.ctx.bus.publish("daynight.changed", night=night)
