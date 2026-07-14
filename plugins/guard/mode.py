"""Guard / sentry mode.

Reacts to motion/presence/door events from Home Assistant (delivered on the event bus by
the HA event bridge) with an alert face, red LEDs, and a spoken warning. Alerts are
throttled so a flapping sensor can't machine-gun; in sleep / calm modes the spoken line is
suppressed (face + LEDs still fire) unless you turn ``quiet_no_voice`` off.
"""
from __future__ import annotations

import time

from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.modes import Mode, ModeMeta


class GuardMode(Mode):
    meta = ModeMeta(name="guard", description="Desk sentry", kind="foreground")

    async def on_enter(self) -> None:
        self._triggers = set(self.ctx.config.get("triggers", ["ha.motion"]))
        self._throttle_s = float(self.ctx.config.get("throttle_s", 20))
        self._last = 0.0
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
        now = time.monotonic()
        if now - self._last < self._throttle_s:
            return
        self._last = now
        await self._alert(event)

    async def _alert(self, event: Event) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.ANGRY)
        if robot.supports(CAP_LEDS):
            await robot.set_leds(cfg.get("alert_color", "red"), 1.0)
        # a full-volume "I'm watching" at 3am is rarely wanted — face+LEDs alert, but
        # hold the spoken line in sleep/calm modes (unless the user opts out)
        speak = robot.supports(CAP_SAY)
        if speak and cfg.get("quiet_no_voice", True) and await self.ctx.is_quiet():
            speak = False
        if speak:
            await robot.say(cfg.get("alert_line", "Motion detected."), proactive=True)
        await self.ctx.bus.publish("guard.alert", source=event.type, detail=event.data)
        self.ctx.log.info("guard alert from %s", event.type)
