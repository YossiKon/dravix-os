"""Frigate watch mode.

When Frigate (via Home Assistant) reports a detection — person/motion/door, surfaced on the
bus by the HA event bridge — show that camera's snapshot on the robot's screen with an alert
face. On the real (``ha``) backend the robot DOWNLOADS the snapshot itself via the firmware's
"Show image URL" slot (needs a direct ``frigate_url`` + a bare Frigate camera name); backends
that support ``show_image`` (mock/MCP) get the fetched bytes instead. Throttled, and silent
while the robot is asleep / in a calm mode.
"""
from __future__ import annotations

import time

from dravix.config import get_settings
from dravix.dal.base import CAP_DISPLAY, CAP_FACE, Expression
from dravix.integrations.frigate import Frigate
from dravix.events import Event
from dravix.modes import Mode, ModeMeta


class FrigateWatchMode(Mode):
    meta = ModeMeta(name="frigate_watch", description="Show Frigate on detection", kind="foreground")

    async def on_enter(self) -> None:
        self._camera = self.ctx.config.get("camera", "")
        self._triggers = set(
            self.ctx.config.get("triggers", ["presence.detected", "ha.motion", "ha.door"])
        )
        self._url = str(self.ctx.config.get("frigate_url") or get_settings().frigate_url or "").rstrip("/")
        self._frigate = Frigate(self.ctx.ha, self._url)
        self._throttle_s = float(self.ctx.config.get("throttle_s", 15))
        self._last = 0.0
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(Expression.NEUTRAL)

    async def on_event(self, event: Event) -> None:
        if event.type not in self._triggers or not self._camera:
            return
        now = time.monotonic()
        if now - self._last < self._throttle_s:
            return  # don't hijack the screen on every motion frame
        if await self.ctx.is_quiet():
            return  # asleep / calm mode → don't light up the screen
        self._last = now
        robot = self.ctx.robot
        try:
            shower = getattr(robot.driver, "show_image_url", None)
            if shower is not None and self._url and not self._camera.startswith("camera."):
                # the robot downloads it itself (light, local) — the path that works on `ha`
                await shower(f"{self._url}/api/{self._camera}/latest.jpg?height=240")
            elif robot.supports(CAP_DISPLAY):
                await robot.show_image(await self._frigate.snapshot(self._camera))
            else:
                return  # no way to display on this backend
            if robot.supports(CAP_FACE):
                await robot.set_face(Expression.DOUBT)
            await self.ctx.bus.publish("frigate.shown", camera=self._camera, source=event.type)
        except Exception as exc:  # noqa: BLE001
            self.ctx.log.warning("frigate_watch failed: %s", exc)
