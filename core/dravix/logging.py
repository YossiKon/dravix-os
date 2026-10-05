"""Minimal logging setup + an in-memory ring buffer so the dashboard can show recent logs
(and the user can copy them to send along when something breaks)."""
from __future__ import annotations

import collections
import logging
import time

_CONFIGURED = False
# Last N dravix log records, kept in memory for the /api/logs endpoint (cheap, bounded).
_RING: collections.deque = collections.deque(maxlen=500)
_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class _RingHandler(logging.Handler):
    """Copies each dravix log record into the ring buffer. Must never raise."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _RING.append(
                {
                    "ts": time.strftime("%H:%M:%S", time.localtime(record.created)),
                    "level": record.levelname,
                    "name": record.name.replace("dravix.", ""),
                    "msg": record.getMessage(),
                }
            )
        except Exception:  # noqa: BLE001 — logging must never crash the app
            pass


def recent_logs(level: str | None = None) -> list[dict]:
    """Recent dravix logs, newest last. ``level`` filters to that severity and above."""
    items = list(_RING)
    if level:
        floor = _ORDER.get(level.upper(), 0)
        items = [r for r in items if _ORDER.get(r.get("level", ""), 0) >= floor]
    return items


def _apply_levels(level: str) -> None:
    """``level`` governs the CONSOLE (the add-on log); the dravix loggers still let INFO
    through so the dashboard's Diagnostics ring keeps "robot connected", "auto-discovered"
    and friends even when the add-on log is set to WARNING."""
    lvl = logging.getLevelName(level.upper())
    if not isinstance(lvl, int):
        lvl = logging.INFO
    root = logging.getLogger()
    root.setLevel(lvl)
    for h in root.handlers:
        h.setLevel(lvl)
    logging.getLogger("dravix").setLevel(min(lvl, logging.INFO))


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        _apply_levels(level)
        return
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Mirror every dravix.* record into the ring buffer for the dashboard's Diagnostics tab.
    ring = _RingHandler()
    ring.setLevel(logging.INFO)
    logging.getLogger("dravix").addHandler(ring)
    _apply_levels(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"dravix.{name}")
