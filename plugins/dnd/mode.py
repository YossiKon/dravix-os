"""Do Not Disturb / meeting mode.

Being a foreground mode, it's mutually exclusive with chatty/guard modes, so simply being
active keeps the robot calm and quiet. It does not react to events while active.
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.modes import Mode, ModeMeta


class DndMode(Mode):
    meta = ModeMeta(name="dnd", description="Do not disturb", kind="foreground")

    async def on_enter(self) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.DOUBT)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(cfg.get("color", "red"), cfg.get("brightness", 0.2))
        greet = cfg.get("greet")
        if greet and robot.supports(CAP_SAY):
            await robot.say(greet, proactive=True)

    async def on_exit(self) -> None:
        robot = self.ctx.robot
        if robot.supports(CAP_LEDS):
            await robot.set_leds("off", 0.0)
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.NEUTRAL)
