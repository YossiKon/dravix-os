"""Manual video recorder — the teleop panel's REC button.

Records the robot's camera into an MP4 clip ON DEMAND (independent of security mode's
continuous recording): one ffmpeg process pulls our own privacy-gated MJPEG stream and
runs until the user presses stop (or the safety cap). Clips land in the security gallery
(``vid_HHMMSS.mp4`` in the day folder), so the existing dashboard manager — view /
download / delete — handles them with zero new UI.

Because ffmpeg reads ``/camera/robot/stream.mjpeg``, every existing rule follows for
free: privacy mode closes the stream and the clip just ends.
"""
from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
from datetime import datetime

from .config import get_settings, security_dir
from .logging import get_logger

log = get_logger("recorder")

_MAX_SECONDS = 15 * 60  # safety cap — a forgotten REC can't fill the disk


class ClipRecorder:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._out = None
        self._started = 0.0
        self._lock = asyncio.Lock()

    @property
    def recording(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def status(self) -> dict:
        rec = self.recording
        return {
            "recording": rec,
            "name": self._out.name if (self._out is not None and rec) else None,
            "seconds": round(time.monotonic() - self._started) if rec else 0,
        }

    async def start(self, fps: int = 6) -> dict:
        async with self._lock:
            if self.recording:
                return {"ok": True, "already": True, **self.status()}
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("ffmpeg is not available in this image")
            fps = min(15, max(1, int(fps)))
            settings = get_settings()
            url = f"http://127.0.0.1:{settings.port}/camera/robot/stream.mjpeg?fps={fps}"
            if settings.api_token:
                url += f"&token={settings.api_token}"
            now = datetime.now()
            day_dir = security_dir() / now.strftime("%Y-%m-%d")
            await asyncio.to_thread(day_dir.mkdir, parents=True, exist_ok=True)
            self._out = day_dir / f"vid_{now.strftime('%H%M%S')}.mp4"
            self._proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "mpjpeg", "-i", url,
                "-t", str(_MAX_SECONDS), "-r", str(fps),
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(self._out),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._started = time.monotonic()
            log.info("manual recording started -> %s", self._out.name)
            return {"ok": True, **self.status()}

    async def stop(self) -> dict:
        async with self._lock:
            if not self.recording:
                return {"ok": True, "recording": False, "name": None, "bytes": 0}
            proc, out = self._proc, self._out
            # 'q' on stdin is ffmpeg's GRACEFUL stop — it finalizes the mp4 (moov atom);
            # terminate() mid-write can corrupt the file, so it's only the fallback.
            try:
                assert proc.stdin is not None
                proc.stdin.write(b"q")
                await proc.stdin.drain()
                await asyncio.wait_for(proc.wait(), timeout=10)
            except Exception:  # noqa: BLE001
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), timeout=5)
            self._proc = None
            size = out.stat().st_size if out.is_file() else 0
            if size < 1024:
                # the stream never opened (privacy on / camera missing) — drop the stub
                with contextlib.suppress(OSError):
                    if out.is_file():
                        out.unlink()
                return {
                    "ok": False, "recording": False, "name": None, "bytes": 0,
                    "error": "clip came out empty — is privacy on / the camera offline?",
                }
            log.info("manual recording stopped -> %s (%d bytes)", out.name, size)
            return {
                "ok": True, "recording": False,
                "name": out.name, "day": out.parent.name, "bytes": size,
            }

    async def close(self) -> None:
        if self.recording:
            await self.stop()
