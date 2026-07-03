"""Follow mode — the robot's head tracks a person in real time.

Off-device visual servoing: dravix asks Frigate where the person is in the robot's camera
frame and nudges the head to re-centre them with a small P-controller on the *normalised*
``move_head(-1..1)`` facade. All the vision work stays on the Frigate host — the ESP32 only
receives head commands — so this adds no load to the robot (no reboots).

Needs:
  * a Frigate server (the ``frigate_url`` config, or ``DRAVIX_FRIGATE_URL``) that ingests the
    robot's own camera as a tracked camera — see docs/frigate.md;
  * a backend with a real head (``CAP_HEAD`` → the ``ha`` driver). On any other backend it
    logs a warning and does nothing.

Every knob (gains, deadzone, inversion, rate) is a live per-mode config value
(``PUT /api/config/modes/follow``), so you can tune it from the dashboard without a redeploy.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from dravix.config import get_settings
from dravix.dal.base import CAP_HEAD
from dravix.integrations.frigate import Frigate
from dravix.modes import Mode, ModeMeta


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


class FollowMode(Mode):
    meta = ModeMeta(
        name="follow",
        description="The robot's head follows a person in real time (via Frigate)",
        kind="foreground",
    )

    def __init__(self, ctx) -> None:  # noqa: ANN001 — ctx is ModeContext
        super().__init__(ctx)
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._frigate: Frigate | None = None
        self._prev_idle = True

    async def on_enter(self) -> None:
        robot = self.ctx.robot
        if not robot.supports(CAP_HEAD):
            self.ctx.log.warning("follow: this backend has no movable head (CAP_HEAD) — idle")
            return
        cfg = self.ctx.config
        frigate_url = str(cfg.get("frigate_url") or get_settings().frigate_url or "").strip()
        if not frigate_url:
            self.ctx.log.warning(
                "follow: no Frigate URL — set 'frigate_url' in the mode config or DRAVIX_FRIGATE_URL"
            )
            return
        # Don't let the autonomous idle glances fight the tracker.
        self._prev_idle = robot.idle_motion
        robot.idle_motion = False
        self._client = httpx.AsyncClient(timeout=5.0)
        self._frigate = Frigate(self.ctx.ha, base_url=frigate_url, client=self._client)
        self._task = asyncio.create_task(self._loop())
        self.ctx.log.info(
            "follow: tracking '%s' on camera '%s' via %s",
            cfg.get("label", "person"), cfg.get("camera", "stackchan"), frigate_url,
        )

    async def on_exit(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._frigate = None
        # Restore whatever the idle-motion setting was before we took over.
        self.ctx.robot.idle_motion = self._prev_idle

    async def _loop(self) -> None:
        cfg = self.ctx.config
        robot = self.ctx.robot
        camera = str(cfg.get("camera") or "stackchan")
        label = str(cfg.get("label") or "person")
        box_format = str(cfg.get("box_format") or "xywh")
        frame = (int(cfg.get("frame_w", 320)), int(cfg.get("frame_h", 240)))
        gain_yaw = float(cfg.get("gain_yaw", 0.4))
        gain_pitch = float(cfg.get("gain_pitch", 0.4))
        deadzone = float(cfg.get("deadzone", 0.12))
        max_step = float(cfg.get("max_step", 0.2))
        s_yaw = -1.0 if cfg.get("invert_yaw") else 1.0
        # +pitch = look up; a person low in the frame (ey > 0) means look DOWN → default -1.
        s_pitch = 1.0 if cfg.get("invert_pitch") else -1.0
        speed = float(cfg.get("speed", 1.0))
        lost_timeout = float(cfg.get("lost_timeout", 3.0))
        recenter = bool(cfg.get("recenter_when_lost", True))
        hz = float(cfg.get("update_hz", 2.0)) or 2.0
        period = 1.0 / min(max(hz, 0.2), 5.0)  # the servo bus caps ~2 Hz; don't spin faster
        last_seen = 0.0
        recentred = False
        while True:
            try:
                centre = await self._frigate.latest_person(camera, label, box_format, frame)
                now = time.monotonic()
                if centre is not None:
                    last_seen = now
                    recentred = False
                    ex, ey = centre[0] * 2.0 - 1.0, centre[1] * 2.0 - 1.0  # 0 = centred in frame
                    if abs(ex) >= deadzone or abs(ey) >= deadzone:
                        cur_yaw = robot.state.head_yaw or 0.0
                        cur_pit = robot.state.head_pitch or 0.0
                        yaw = _clamp(cur_yaw + _clamp(s_yaw * gain_yaw * ex, -max_step, max_step))
                        pit = _clamp(cur_pit + _clamp(s_pitch * gain_pitch * ey, -max_step, max_step))
                        if abs(yaw - cur_yaw) > 0.01 or abs(pit - cur_pit) > 0.01:
                            await robot.move_head(yaw, pit, speed)
                elif recenter and not recentred and (now - last_seen) > lost_timeout:
                    cur_yaw = robot.state.head_yaw or 0.0
                    cur_pit = robot.state.head_pitch or 0.0
                    if abs(cur_yaw) > 0.02 or abs(cur_pit) > 0.02:
                        await robot.move_head(0.0, 0.0, speed)
                    recentred = True
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — a transient bus/HTTP error must not kill follow
                self.ctx.log.debug("follow loop: %s", e)
            await asyncio.sleep(period)
