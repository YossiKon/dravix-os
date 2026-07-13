"""Privacy enforcement — REALLY detach the robot's camera while privacy mode is on.

dravix's own endpoints (stream / photo / photobooth / security snapshots) already refuse
while private — but the robot's camera is ALSO a Home Assistant entity, fetchable by HA
(and by anything going through HA: automations, NVRs, other add-ons) regardless of dravix.
So when privacy flips ON we DISABLE the camera entity in HA's registry — it is removed
from HA on the spot, nothing can snapshot or stream it. Flipping privacy OFF re-enables
it and reloads its integration so it comes straight back.

The detached entity id is remembered in the store: a robot that stays private across a
restart is invisible to discovery (disabled entities aren't in /api/states), and we still
need to know WHAT to re-attach later.

The microphone needs no equivalent — audio only ever leaves the robot through a voice
session, and the firmware refuses/kills sessions while its privacy switch is on.
"""
from __future__ import annotations

from typing import Any

from .logging import get_logger

log = get_logger("privacy")


async def apply_camera_privacy(s: Any, private: bool) -> str | None:
    """Detach (privacy ON) / re-attach the camera entity at the HA level.

    ``s`` is app.state. Returns an error string, or None when done/nothing-to-do.
    Never raises — privacy must not break the toggle itself."""
    ha = getattr(s, "ha", None)
    if ha is None:
        return None  # mock / no HA — nothing reaches a camera anyway
    store = getattr(s, "store", None)
    cam = (getattr(s, "discovered_entities", None) or {}).get("camera") or ""
    if not cam and store is not None:
        # detached before a restart → invisible to discovery; the store remembers it
        cam = store.privacy_camera()
    if not cam:
        return "no camera entity known"
    try:
        # no-op when already in the desired state — a config-entry reload flaps every
        # robot entity, so it must only happen on a REAL re-attach
        entry = await ha._ws_command(  # noqa: SLF001 — same-package admin helper
            {"type": "config/entity_registry/get", "entity_id": cam}
        )
        if bool(entry.get("disabled_by")) == private:
            pass  # already there
        else:
            await ha.set_entity_enabled(cam, enabled=not private)
            log.info("camera %s %s", cam, "DETACHED from HA (privacy on)" if private else "re-attached")
    except Exception as exc:  # noqa: BLE001
        log.warning("camera privacy (%s) failed for %s: %s", private, cam, exc)
        return str(exc)
    if store is not None:
        try:
            store.set_privacy_camera(cam if private else "")
        except Exception:  # noqa: BLE001 — bookkeeping only
            pass
    return None
