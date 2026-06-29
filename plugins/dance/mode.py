"""Dance mode — a playful head-bob + LED color cycle, advanced by the engine tick.

(Tip: lower ``DRAVIX_*`` tick or the engine ``tick_interval`` for a faster dance — the default
5s tick makes for a *very* relaxed groove.)
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, Expression
from dravix.modes import Mode, ModeMeta

_STEPS = [(-30, 6), (30, 6), (-15, -6), (15, -6), (0, 0)]


class DanceMode(Mode):
    meta = ModeMeta(name="dance", description="A little dance", kind="foreground")

    async def on_enter(self) -> None:
        self._i = 0
        self._colors = self.ctx.config.get("colors", ["red", "green", "blue"])
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.HAPPY)

    async def on_exit(self) -> None:
        robot = self.ctx.robot
        if robot.supports(CAP_HEAD):
            await robot.move_head(0, 0)
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.NEUTRAL)

    async def tick(self) -> None:
        robot = self.ctx.robot
        yaw, pitch = _STEPS[self._i % len(_STEPS)]
        color = self._colors[self._i % len(self._colors)]
        self._i += 1
        if robot.supports(CAP_HEAD):
            await robot.move_head(yaw, pitch, speed=1.0)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(color, 1.0)
