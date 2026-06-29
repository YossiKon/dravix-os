"""Frigate watch mode.

When Frigate (via Home Assistant) reports a detection — person/motion/door, surfaced on the
bus by the HA event bridge — fetch that camera's snapshot (locally) and show it on the robot's
screen, with an alert face. Needs a ``camera`` configured and the robot to support a display;
otherwise it stays quiet.
"""
from __future__ import annotations

from dravix.dal.base import CAP_DISPLAY, CAP_FACE, Expression
from dravix.events import Event
from dravix.integrations.frigate import Frigate
from dravix.modes import Mode, ModeMeta


class FrigateWatchMode(Mode):
    meta = ModeMeta(name="frigate_watch", description="Show Frigate on detection", kind="foreground")

    async def on_enter(self) -> None:
        self._camera = self.ctx.config.get("camera", "")
        self._triggers = set(
            self.ctx.config.get("triggers", ["presence.detected", "ha.motion", "ha.door"])
        )
        self._frigate = Frigate(self.ctx.ha, self.ctx.config.get("frigate_url", ""))
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.NEUTRAL)

    async def on_event(self, event: Event) -> None:
        if event.type not in self._triggers or not self._camera:
            return
        if not self.ctx.robot.supports(CAP_DISPLAY):
            return
        try:
            img = await self._frigate.snapshot(self._camera)
            await self.ctx.robot.show_image(img)
            if self.ctx.robot.supports(CAP_FACE):
                await self.ctx.robot.set_face(Expression.DOUBT)
            await self.ctx.bus.publish("frigate.shown", camera=self._camera, source=event.type)
        except Exception as exc:  # noqa: BLE001
            self.ctx.log.warning("frigate_watch failed: %s", exc)
