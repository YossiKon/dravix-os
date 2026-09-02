"""Mode engine package."""
from __future__ import annotations

from .base import Mode, ModeContext, ModeMeta
from .engine import ModeEngine

# Seed for "this has never happened yet" when the clock is ``time.monotonic()``.
# monotonic() is the machine's UPTIME, so 0.0 does NOT mean "long ago" — on a host that
# booted a minute ago it means "one minute ago", and every throttle of the form
# ``now - last < gap`` then swallows its FIRST event. That is a real bug (Home Assistant
# restarts are exactly when a fresh uptime happens) and it fails deterministically on CI,
# whose runners are always freshly booted. Seed every such field with this instead.
LONG_AGO = -1e12

__all__ = ["Mode", "ModeContext", "ModeMeta", "ModeEngine", "LONG_AGO"]
