"""Day/night awareness.

Checks the local hour on each tick and, on a day↔night transition, publishes
``daynight.changed`` — the signal the MoodEngine uses to drift toward a sleepy expression
at night. It does NOT paint the face or LEDs itself: the firmware already owns night
behaviour (its ``night`` mode + the "Sleep when dark" ambient-light path), so a second
painter here would fight it and leave LEDs lit all night. This mode is the tiny bridge
that tells the mood engine what time of day it is.
"""
from __future__ import annotations

import datetime

from dravix.modes import Mode, ModeMeta


class DayNightMode(Mode):
    meta = ModeMeta(name="daynight", description="Day/night awareness (mood signal)", kind="ambient")

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
        # signal only — the mood engine and the firmware do the actual expressing
        await self.ctx.bus.publish("daynight.changed", night=night)
