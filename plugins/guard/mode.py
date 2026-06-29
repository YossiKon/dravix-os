"""Guard / sentry mode.

Reacts to motion/presence/door events from Home Assistant (bridged onto the event bus in a
later phase) with an alert face, red LEDs, and a spoken warning. Built and testable now by
publishing a trigger event onto the bus; it lights up for real once the HA event bridge is
wired.
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.modes import Mode, ModeMeta


class GuardMode(Mode):
    meta = ModeMeta(name="guard", description="Desk sentry", kind="foreground")

    async def on_enter(self) -> None:
        self._triggers = set(self.ctx.config.get("triggers", ["ha.motion"]))
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.DOUBT)
        if self.ctx.robot.supports(CAP_LEDS):
            await self.ctx.robot.set_leds("amber", 0.3)

    async def on_exit(self) -> None:
        if self.ctx.robot.supports(CAP_LEDS):
            await self.ctx.robot.set_leds("off", 0.0)
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.NEUTRAL)

    async def on_event(self, event: Event) -> None:
        if event.type not in self._triggers:
            return
        await self._alert(event)

    async def _alert(self, event: Event) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.ANGRY)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(cfg.get("alert_color", "red"), 1.0)
        if robot.supports(CAP_SAY):
            await robot.say(cfg.get("alert_line", "Motion detected."))
        await self.ctx.bus.publish("guard.alert", source=event.type, detail=event.data)
        self.ctx.log.info("guard alert from %s", event.type)
