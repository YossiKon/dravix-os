"""Ambient idle behavior.

Runs in the background alongside whatever foreground mode is active. Every few ticks it makes
a small head glance and relaxes the face, so the robot feels alive rather than frozen. Being
*ambient*, it auto-starts at boot and coexists with foreground modes.
"""
from __future__ import annotations

import random

from dravix.dal.base import CAP_FACE, CAP_HEAD, Expression
from dravix.modes import Mode, ModeMeta


class AmbientIdleMode(Mode):
    meta = ModeMeta(name="ambient_idle", description="Subtle idle life", kind="ambient")

    async def on_enter(self) -> None:
        self._n = 0
        self._every = max(1, int(self.ctx.config.get("glance_every_ticks", 3)))
        # normalised glance amount (0..1 fraction of travel); small = subtle looks.
        self._span = float(self.ctx.config.get("glance_yaw", 0.35))

    async def tick(self) -> None:
        self._n += 1
        if self._n % self._every != 0:
            return
        robot = self.ctx.robot
        if robot.supports(CAP_HEAD) and getattr(robot, "idle_motion", True):
            yaw = random.uniform(-self._span, self._span)
            pitch = random.uniform(-self._span / 3, self._span / 3)
            await robot.move_head(round(yaw, 1), round(pitch, 1), speed=0.3)
        if robot.supports(CAP_FACE) and random.random() < 0.3:
            await robot.set_face(random.choice([Expression.NEUTRAL, Expression.SLEEPY]))
