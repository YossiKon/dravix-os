"""Version + update visibility.

One place answers "is anything out of date?" for the dashboard:

- **add-on**: this service's ``__version__`` vs the newest GitHub release tag
  (checked at most every 6 h, never when the master isLocal flag is on — no
  internet calls in local-only mode; Home Assistant additionally shows its own
  native update entity for the add-on).
- **firmware**: the ``fw_version`` the running robot publishes (the "Firmware
  version" sensor) vs the ``fw_version`` bundled in this release's copy of
  ``deploy/esphome/stackchan-dravix.yaml``. A mismatch means "press Install in
  ESPHome" (or bump the git-stub's ``ref``).

Rollback story (documented in the release workflow + the git-stub): every release
is tagged ``v<version>`` — firmware rolls back by pointing the stub's ``ref`` at an
older tag; the add-on rolls back by reverting the version in dravix_os/config.yaml
(every versioned image stays on GHCR).
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from . import __version__
from .config import REPO_ROOT
from .logging import get_logger

log = get_logger("updates")

_RELEASES_URL = "https://api.github.com/repos/YossiKon/dravix-os/releases/latest"
_CHECK_EVERY_S = 6 * 3600
_FW_YAML = REPO_ROOT / "deploy" / "esphome" / "stackchan-dravix.yaml"

_cache: dict[str, Any] = {"at": 0.0, "latest": None}


def bundled_fw_version() -> str | None:
    """The fw_version substitution in this release's firmware YAML (None if unreadable)."""
    try:
        text = _FW_YAML.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^\s*fw_version:\s*"?([\w.\-]+)"?', text, re.MULTILINE)
    return m.group(1) if m else None


def _newer(a: str, b: str) -> bool:
    """True when version string ``a`` is newer than ``b`` (numeric, best-effort)."""
    def parts(v: str) -> list[int]:
        return [int(x) for x in re.findall(r"\d+", v)] or [0]
    return parts(a) > parts(b)


async def latest_release(*, allow_network: bool) -> str | None:
    """Newest release tag ("0.0.42"), cached; None when offline/local-only/unknown."""
    if not allow_network:
        return _cache["latest"]  # whatever we last knew (possibly None) — no calls
    if time.monotonic() - _cache["at"] < _CHECK_EVERY_S and _cache["latest"]:
        return _cache["latest"]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(_RELEASES_URL, headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            tag = str(r.json().get("tag_name") or "").lstrip("v")
    except Exception as exc:  # noqa: BLE001 — update checks must never break anything
        log.debug("release check failed: %s", exc)
        return _cache["latest"]
    _cache["at"] = time.monotonic()
    _cache["latest"] = tag or None
    return _cache["latest"]


async def robot_fw_version(ha) -> str | None:
    """The fw_version the ROBOT is running (its "Firmware version" sensor), or None."""
    if ha is None:
        return None
    try:
        states = await ha.states()
    except Exception:  # noqa: BLE001
        return None
    for s in states:
        eid = s.get("entity_id", "")
        if eid.startswith("sensor.") and eid.split(".", 1)[1].endswith("firmware_version"):
            v = s.get("state")
            if v not in (None, "", "unknown", "unavailable"):
                return str(v)
    return None


async def update_report(ha, *, allow_network: bool) -> dict[str, Any]:
    """Everything the dashboard's "updates" card needs, in one call."""
    latest = await latest_release(allow_network=allow_network)
    fw_bundled = bundled_fw_version()
    fw_robot = await robot_fw_version(ha)
    return {
        "addon_version": __version__,
        "addon_latest": latest,
        "addon_update": bool(latest and __version__ != "dev" and _newer(latest, __version__)),
        "fw_bundled": fw_bundled,
        "fw_robot": fw_robot,  # None = robot offline or running pre-versioning firmware
        "fw_update": bool(fw_bundled and fw_robot and fw_robot != fw_bundled),
        "checked_online": allow_network,
    }
