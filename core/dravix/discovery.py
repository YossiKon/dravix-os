"""Auto-discovery of the robot's Home Assistant entities.

dravix already knows every entity the dravix ESPHome firmware exposes — each has a stable
object-id SUFFIX ("head_pitch", "show_image_url", "privacy_mode", …). So instead of making
the user hand-map entities in the dashboard, this scans HA's states once and fills every
robot role automatically. Entity-id PREFIXES are never assumed (devices get renamed; some
flashes carry an "<area>_<device>" prefix): the distinctive suffixes vote for the robot's
prefix, and ambiguous roles ("state", "mode", "camera") only accept a majority prefix.

Explicit configuration still wins — add-on options / env / anything saved in the store
override whatever is discovered. Discovery only fills the gaps.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .logging import get_logger

if TYPE_CHECKING:
    from .integrations.homeassistant import HomeAssistant

log = get_logger("discovery")

# role -> (domain, candidate object-id suffixes, needs_prefix_anchor)
# needs_prefix_anchor=True: the suffix is too generic ("state", "mode") to trust house-wide,
# so it only matches under a prefix that the distinctive suffixes voted for.
_ROLES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "face_select": ("select", ("face",), True),
    "mode_select": ("select", ("mode",), True),
    "head_yaw": ("number", ("servo_x_angle",), False),
    "head_pitch": ("number", ("head_pitch",), False),
    "led_light": ("light", ("stackchan_light_bar", "light_bar"), False),
    "media_player": ("media_player", ("media_player",), True),
    "camera": ("camera", ("camera",), True),
    "state_sensor": ("sensor", ("state",), True),
    "heard_sensor": ("sensor", ("last_heard",), False),
    "reply_sensor": ("sensor", ("last_reply",), False),
    "image_url_text": ("text", ("show_image_url",), False),
    "privacy_switch": ("switch", ("privacy_mode",), False),
    "islocal_switch": ("switch", ("local_only",), False),
    "screensaver_number": ("number", ("screensaver_after_min",), False),
    "sleep_number": ("number", ("sleep_after_min",), False),
}

# Suffixes unique enough to identify the robot device (they vote for its prefix).
_ANCHOR_SUFFIXES = (
    "head_pitch", "show_image_url", "privacy_mode", "last_heard", "last_reply",
    "screensaver_after_min", "sleep_after_min", "stackchan_light_bar", "servo_x_angle",
)


def _split(entity_id: str) -> tuple[str, str]:
    domain, _, object_id = entity_id.partition(".")
    return domain, object_id


def _prefix_for(object_id: str, suffix: str) -> str | None:
    """The prefix part of ``object_id`` if it matches ``suffix`` ("" = no prefix)."""
    if object_id == suffix:
        return ""
    if object_id.endswith("_" + suffix):
        return object_id[: -(len(suffix) + 1)]
    return None


def discover_from_states(states: list[dict]) -> dict[str, str]:
    """Map robot roles -> entity ids from a full HA state dump (pure, testable)."""
    ids = [s.get("entity_id", "") for s in states if s.get("entity_id")]

    # 1 · the distinctive suffixes vote for the robot's entity prefix(es)
    votes: Counter[str] = Counter()
    for eid in ids:
        _, object_id = _split(eid)
        for suffix in _ANCHOR_SUFFIXES:
            p = _prefix_for(object_id, suffix)
            if p is not None:
                votes[p] += 1
    # every prefix with a meaningful share of the votes is "the robot" (a renamed device
    # can legitimately have entities under two prefixes — see the firmware's ha_prefix_alt)
    prefixes = {p for p, n in votes.items() if n >= 2} or set(dict(votes.most_common(1)))

    # 2 · fill each role
    found: dict[str, str] = {}
    for role, (domain, suffixes, needs_anchor) in _ROLES.items():
        candidates: list[tuple[bool, int, str]] = []  # (not-anchored, length, entity_id)
        for eid in ids:
            d, object_id = _split(eid)
            if d != domain:
                continue
            for suffix in suffixes:
                p = _prefix_for(object_id, suffix)
                if p is None:
                    continue
                anchored = p in prefixes
                if needs_anchor and not anchored:
                    continue
                candidates.append((not anchored, len(object_id), eid))
                break
        if candidates:
            candidates.sort()
            found[role] = candidates[0][2]

    # 3 · the TTS engine is an HA-level service, not a robot entity — pick the one there is
    tts = sorted(eid for eid in ids if eid.startswith("tts."))
    if tts:
        found["tts_engine"] = tts[0]

    return found


async def discover_robot_entities(ha: "HomeAssistant") -> dict[str, str]:
    """Scan HA and return {role: entity_id} for everything recognizably the robot's."""
    try:
        states = await ha.states()
    except Exception as exc:  # noqa: BLE001 — discovery must never break startup
        log.warning("entity discovery skipped (HA states unavailable: %s)", exc)
        return {}
    found = discover_from_states(states)
    if found:
        log.info("auto-discovered %d robot entities: %s", len(found), found)
    else:
        log.warning("no robot entities discovered — is the robot's firmware flashed?")
    return found
