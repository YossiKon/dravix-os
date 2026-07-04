"""Dance mode — a playful head-bob + LED color cycle, advanced by the engine tick.

(Tip: lower ``DRAVIX_*`` tick or the engine ``tick_interval`` for a faster dance — the default
5s tick makes for a *very* relaxed groove.)
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, Expression
from dravix.modes import Mode, ModeMeta

# normalised head positions (-1..1): a playful side-to-side bob.
_STEPS = [(-0.6, 0.2), (0.6, 0.2), (-0.3, -0.2), (0.3, -0.2), (0.0, 0.0)]


class DanceMode(Mode):
    meta = ModeMeta(name="dance", description="A little dance", kind="foreground")

    async def on_enter(self) -> None:
        self._i = 0
        self._colors = self.ctx.config.get("colors", ["red", "green", "blue"])
        # don't let the ambient idle glances fight the choreography
        self._prev_idle = getattr(self.ctx.robot, "idle_motion", True)
        self.ctx.robot.idle_motion = False
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.HAPPY)

    async def on_exit(self) -> None:
        robot = self.ctx.robot
        robot.idle_motion = self._prev_idle
        if robot.supports(CAP_HEAD):
            await robot.move_head(0, 0)
        if robot.supports(CAP_LEDS):
            await robot.set_leds("off", 0.0)  # stop the disco on the way out
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.NEUTRAL)

    async def tick(self) -> None:
        robot = self.ctx.robot
        # no dancing while the robot is asleep/screensaver — the head moves get dropped
        # by the driver anyway, and cycling party LEDs on a sleeping robot is wrong
        if await self.ctx.is_asleep():
            return
        yaw, pitch = _STEPS[self._i % len(_STEPS)]
        color = self._colors[self._i % len(self._colors)]
        self._i += 1
        if robot.supports(CAP_HEAD):
            await robot.move_head(yaw, pitch, speed=1.0)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(color, 1.0)
