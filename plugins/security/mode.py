"""Security mode — the robot becomes a little guard camera.

While armed it:
  * saves a camera snapshot every ``snapshot_every_s`` seconds into the add-on's
    persistent storage (``<data>/security/YYYY-MM-DD/HHMMSS.jpg``) — browse/serve them
    via ``GET /api/security/photos`` and the dashboard's Security card;
  * patrols — every ``patrol_every_min`` minutes the head sweeps left → right → centre,
    so the camera covers the room (0 disables the patrol);
  * stays steerable — the dashboard's joystick + live camera view keep working, so you
    can look around remotely (reach the dashboard from anywhere via Home Assistant's
    own remote access).

Storage is day-folders, pruned to ``keep_days``. Everything stays on YOUR box — nothing
leaves the LAN, which also means it fully respects the master isLocal flag. Needs a
backend with a camera (``CAP_PHOTO``); patrol additionally wants a head (``CAP_HEAD``).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from dravix.config import security_dir
from dravix.dal.base import CAP_HEAD, CAP_PHOTO, CAP_SAY
from dravix.modes import Mode, ModeMeta


class SecurityMode(Mode):
    meta = ModeMeta(
        name="security",
        description="Guard mode: periodic snapshots to server storage + a head patrol",
        kind="foreground",
    )

    def __init__(self, ctx) -> None:  # noqa: ANN001 — ctx is ModeContext
        super().__init__(ctx)
        self._task: asyncio.Task | None = None
        self._prev_idle = True

    async def on_enter(self) -> None:
        robot = self.ctx.robot
        if not robot.supports(CAP_PHOTO):
            self.ctx.log.warning("security: this backend has no camera (CAP_PHOTO) — idle")
            return
        # the autonomous idle glances would fight the patrol — pause them while armed
        self._prev_idle = getattr(robot, "idle_motion", True)
        robot.idle_motion = False
        if bool(self.ctx.config.get("announce", False)) and robot.supports(CAP_SAY):
            from dravix.config import get_settings

            he = (get_settings().language or "en").startswith("he")
            try:
                await robot.say("מצב אבטחה הופעל." if he else "Security mode armed.")
            except Exception:  # noqa: BLE001 — announcing is best-effort
                pass
        self._task = asyncio.create_task(self._run(), name="dravix-security")

    async def on_exit(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.ctx.robot.idle_motion = self._prev_idle

    # ── the guard loop ────────────────────────────────────────────────────────────
    async def _run(self) -> None:
        cfg = self.ctx.config
        every_s = max(2.0, float(cfg.get("snapshot_every_s", 10)))
        patrol_s = max(0.0, float(cfg.get("patrol_every_min", 3))) * 60.0
        span = min(1.0, max(0.1, float(cfg.get("patrol_span", 0.7))))
        keep_days = max(1, int(cfg.get("keep_days", 7)))
        next_patrol = time.monotonic() + patrol_s if patrol_s else float("inf")
        last_prune = 0.0
        while True:
            started = time.monotonic()
            try:
                await self._snapshot()
            except Exception as exc:  # noqa: BLE001 — a failed frame must not stop the guard
                self.ctx.log.debug("security: snapshot failed: %s", exc)
            if time.monotonic() >= next_patrol:
                next_patrol = time.monotonic() + patrol_s
                try:
                    await self._patrol(span)
                except Exception as exc:  # noqa: BLE001
                    self.ctx.log.debug("security: patrol failed: %s", exc)
            if time.monotonic() - last_prune > 3600:
                last_prune = time.monotonic()
                await asyncio.to_thread(self._prune, keep_days)
            # keep the cadence even when a snapshot/patrol took a while
            await asyncio.sleep(max(1.0, every_s - (time.monotonic() - started)))

    async def _snapshot(self) -> None:
        data = await self.ctx.robot.take_photo()
        if not data:
            return
        now = datetime.now()
        day_dir = security_dir() / now.strftime("%Y-%m-%d")
        path = day_dir / f"{now.strftime('%H%M%S')}.jpg"
        def _write() -> None:
            day_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        await asyncio.to_thread(_write)

    async def _patrol(self, span: float) -> None:
        robot = self.ctx.robot
        if not robot.supports(CAP_HEAD):
            return
        # a slow sweep: left, hold, right, hold, back to centre — camera covers the room
        for yaw in (-span, span, 0.0):
            await robot.move_head(yaw, 0.0, speed=0.5)
            await asyncio.sleep(2.0)

    def _prune(self, keep_days: int) -> None:
        """Drop day-folders older than keep_days (best-effort, runs in a thread)."""
        root = security_dir()
        if not root.exists():
            return
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        for day in root.iterdir():
            if day.is_dir() and day.name < cutoff:
                for f in day.iterdir():
                    try:
                        f.unlink()
                    except OSError:
                        pass
                try:
                    day.rmdir()
                except OSError:
                    pass
