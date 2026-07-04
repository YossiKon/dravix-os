"""Ambient idle behavior.

Runs in the background alongside whatever foreground mode is active. Every few ticks it
makes a small HEAD glance so the robot feels alive rather than frozen. It does NOT touch
the face — the firmware owns the idle face (blink / breathe / its own glances) and a
face poke here would fight whatever foreground mode is showing.
"""
from __future__ import annotations

import random

from dravix.dal.base import CAP_HEAD
from dravix.modes import Mode, ModeMeta


class AmbientIdleMode(Mode):
    meta = ModeMeta(name="ambient_idle", description="Subtle idle glances", kind="ambient")

    async def on_enter(self) -> None:
        self._n = 0
        self._every = max(1, int(self.ctx.config.get("glance_every_ticks", 3)))
        # normalised glance amount (0..1 fraction of travel); small = subtle looks.
        self._span = min(1.0, abs(float(self.ctx.config.get("glance_yaw", 0.35))))

    async def tick(self) -> None:
        robot = self.ctx.robot
        # Master switch for ALL of dravix's autonomous idle life. Off ⇒ the robot stays put
        # (the on-device firmware, which glances on its own and correctly freezes in
        # sleep/focus/quiet, is then the only thing that moves it).
        if not getattr(robot, "idle_motion", True):
            return
        self._n += 1
        if self._n % self._every != 0:
            return
        if not robot.supports(CAP_HEAD):
            return
        # Do-not-disturb: don't twitch the head in sleep/calm modes (the driver drops
        # sleep/screensaver anyway, but night/focus/quiet need this explicit check).
        if await self.ctx.is_quiet():
            return
        yaw = random.uniform(-self._span, self._span)
        pitch = random.uniform(-self._span / 3, self._span / 3)
        await robot.move_head(round(yaw, 2), round(pitch, 2), speed=0.3)
