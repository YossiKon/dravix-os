"""Example mode: Focus.

Demonstrates the plugin contract end-to-end. A real mode would react to HA presence,
calendar, Pomodoro timers, etc. This one keeps the robot calm and quietly acknowledges
when you talk to it. Capability guards mean it degrades gracefully on backends that don't
support a given verb (e.g. the mock driver supports all; the HA driver may not).
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.modes import Mode, ModeMeta


class FocusMode(Mode):
    meta = ModeMeta(name="focus", description="Calm work companion", kind="foreground")

    async def on_enter(self) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.NEUTRAL)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(cfg.get("led_color", "blue"), cfg.get("led_brightness", 0.25))
        greet = cfg.get("greet")
        if greet and robot.supports(CAP_SAY):
            await robot.say(greet)
        self.ctx.log.info("focus mode entered")

    async def on_exit(self) -> None:
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.NEUTRAL)

    async def on_event(self, event: Event) -> None:
        # Gentle acknowledgement: a brief happy glance when the user speaks to the robot.
        if event.type == "user.spoke" and self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.HAPPY)
