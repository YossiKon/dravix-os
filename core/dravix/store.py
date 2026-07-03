"""Persistent runtime settings store (JSON-backed).

Holds the things a user changes at runtime — which AI provider to use, per-mode config
overrides, and which modes are disabled — so they survive restarts. Written atomically.
Env (`DRAVIX_*`) remains the source of *defaults*; the store only holds *overrides*.
"""
from __future__ import annotations

import json
import os
import pathlib
import uuid
from typing import Any

from .logging import get_logger

log = get_logger("store")

_DEFAULTS: dict[str, Any] = {
    "ai_provider": None,  # None = use the env default
    "mode_overrides": {},  # {mode_name: {config...}}
    "disabled_modes": [],  # [mode_name, ...]
    "reactions": [],  # [{name, on, match?, throttle_s?, face?, leds?, say?, frigate_show?, ...}]
    "mood": {},  # {valence, arousal, affection} — personality carried across restarts
    "schedule": [],  # [{name, at:"HH:MM", days?:[0-6], enabled?, action:{say?,face?,emote?,...}}]
    "personas": [],  # [{name, system_prompt, voice?, default_expression?}]
    "active_persona": None,  # name of the active persona (None = built-in default)
    "memories": [],  # [{id, text}] — facts the robot remembers (fed to the AI)
    "routines": [],  # [{name, steps:[{face?,leds?,head?,emote?,say?,wait?,activate_mode?}]}]
    "voice": None,  # active TTS voice override applied to all speech (None = persona/default)
    "voices": [],  # user catalog of voice ids to pick from (depends on your TTS engine)
    "inbox": [],  # [{id, text}] — queued notifications for the robot to read out
    "screens": [],  # up to 3 display cards: [{title, entities:[entity_id, ...]}] pushed to the robot
    "climate_entity": "",  # the dashboard's chosen AC / thermostat (climate.*) for the Climate page
    # Robot wiring picked from the dashboard (overrides the add-on/env defaults):
    "robot_driver": None,  # None = env default (mock|ha|mcp)
    "robot_entities": {},  # {face_select, head_yaw, head_pitch, media_player, tts_engine,
    #                         led_light, camera, screensaver_number, sleep_number, mode_select}
    "head_calibration": {},  # {yaw:{center,min,max,invert}, pitch:{center,min,max,invert}}
    "vitals": {},  # {energy, food, fun, calm} 0-100 + bookkeeping — the "life" needs, kept across restarts
    "nudges_enabled": True,  # wellness tips (rest/hydrate/eye-break) for the person working nearby
    "language": None,  # tips/UI language (en|he); None = the env default (DRAVIX_LANG)
    "wellness_tips": [],  # custom wellness tip texts; non-empty list replaces the built-ins
}

# Keys ``update()`` (and /api/import) may write. Everything else in a patch is rejected.
# Includes "mood"/"idle_motion" so an /api/export round-trips cleanly through /api/import.
_UPDATABLE_KEYS = (
    "ai_provider", "mode_overrides", "disabled_modes", "reactions", "schedule",
    "personas", "active_persona", "memories", "routines", "voice", "voices", "inbox",
    "screens", "robot_driver", "robot_entities", "head_calibration",
    "climate_entity", "vitals", "nudges_enabled", "language", "wellness_tips",
    "mood", "idle_motion", "robot_name", "local_only",
)


class Store:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path
        self._data: dict[str, Any] = json.loads(json.dumps(_DEFAULTS))  # deep copy
        self.load()

    # ── persistence ───────────────────────────────────────────────────────────
    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = {**self._data, **loaded}
        except Exception as exc:  # noqa: BLE001 — a corrupt file must not crash startup
            log.error("failed to read store %s: %s — using defaults", self._path, exc)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)  # atomic on the same filesystem

    # ── generic access ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._data))  # defensive copy

    def update(self, patch: dict[str, Any]) -> None:
        for key in _UPDATABLE_KEYS:
            if key in patch:
                self._data[key] = patch[key]
        self.save()

    def validate_patch(self, patch: dict[str, Any]) -> list[str]:
        """Return the bad keys in an ``update()`` patch (unknown key, or a value whose type
        doesn't match the key's current/default shape — lists stay lists, dicts dicts,
        scalars scalar). An empty result means the patch is safe to apply."""
        bad: list[str] = []
        for key, value in patch.items():
            if key not in _UPDATABLE_KEYS:
                bad.append(f"{key} (unknown key)")
                continue
            ref = self._data.get(key)
            if ref is None:
                ref = _DEFAULTS.get(key)
            if isinstance(ref, bool):
                ok = isinstance(value, bool)
            elif isinstance(ref, list):
                ok = isinstance(value, list)
            elif isinstance(ref, dict):
                ok = isinstance(value, dict)
            else:  # a scalar slot (str / number / nullable)
                ok = not isinstance(value, (list, dict))
            if not ok:
                expected = type(ref).__name__ if ref is not None else "scalar"
                bad.append(f"{key} (expected {expected})")
        return bad

    def personas(self) -> list[dict[str, Any]]:
        return list(self._data.get("personas", []))

    def set_personas(self, personas: list[dict[str, Any]]) -> None:
        self._data["personas"] = personas
        self.save()

    def active_persona(self) -> str | None:
        return self._data.get("active_persona")

    def set_active_persona(self, name: str | None) -> None:
        self._data["active_persona"] = name
        self.save()

    def memories(self) -> list[dict[str, Any]]:
        return list(self._data.get("memories", []))

    def add_memory(self, text: str) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex[:8], "text": text}
        self._data.setdefault("memories", []).append(item)
        self.save()
        return item

    def remove_memory(self, mem_id: str) -> bool:
        before = self._data.get("memories", [])
        after = [m for m in before if m.get("id") != mem_id]
        if len(after) == len(before):
            return False
        self._data["memories"] = after
        self.save()
        return True

    def routines(self) -> list[dict[str, Any]]:
        return list(self._data.get("routines", []))

    def set_routines(self, routines: list[dict[str, Any]]) -> None:
        self._data["routines"] = routines
        self.save()

    def local_only(self, default: bool = True) -> bool:
        """The MASTER isLocal flag: only local things may run (cloud AI blocked, the cloud
        MCP bridge disconnected, external image URLs rejected). ``None`` in the store =
        follow the add-on/env default; the dashboard writes True/False here."""
        v = self._data.get("local_only")
        return default if v is None else bool(v)

    def local_only_override(self) -> bool | None:
        return self._data.get("local_only")

    def set_local_only(self, enabled: bool | None) -> None:
        self._data["local_only"] = enabled
        self.save()

    def robot_name(self) -> str:
        """The robot's user-chosen name ("" = use the default branding)."""
        return str(self._data.get("robot_name") or "")

    def set_robot_name(self, name: str | None) -> None:
        self._data["robot_name"] = (name or "").strip()
        self.save()

    def voice(self) -> str | None:
        return self._data.get("voice")

    def set_voice(self, voice: str | None) -> None:
        self._data["voice"] = voice
        self.save()

    def idle_motion(self, default: bool = True) -> bool:
        return bool(self._data.get("idle_motion", default))

    def set_idle_motion(self, enabled: bool) -> None:
        self._data["idle_motion"] = bool(enabled)
        self.save()

    # ── robot wiring (driver + HA entities + head calibration) ──────────────────
    def robot_driver(self) -> str | None:
        return self._data.get("robot_driver")

    def set_robot_driver(self, driver: str | None) -> None:
        self._data["robot_driver"] = driver or None
        self.save()

    def robot_entities(self) -> dict[str, str]:
        return dict(self._data.get("robot_entities", {}))

    def set_robot_entities(self, entities: dict[str, str]) -> None:
        # Keep only non-empty ids so an empty picker falls back to the env default.
        self._data["robot_entities"] = {k: v for k, v in (entities or {}).items() if v}
        self.save()

    def head_calibration(self) -> dict[str, Any]:
        return dict(self._data.get("head_calibration", {}))

    def set_head_calibration(self, calibration: dict[str, Any]) -> None:
        self._data["head_calibration"] = calibration or {}
        self.save()

    def voices(self) -> list[str]:
        return list(self._data.get("voices", []))

    def set_voices(self, voices: list[str]) -> None:
        self._data["voices"] = voices
        self.save()

    def inbox(self) -> list[dict[str, Any]]:
        return list(self._data.get("inbox", []))

    def add_inbox(self, text: str) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex[:8], "text": text}
        self._data.setdefault("inbox", []).append(item)
        self.save()
        return item

    def clear_inbox(self) -> None:
        self._data["inbox"] = []
        self.save()

    def schedule(self) -> list[dict[str, Any]]:
        return list(self._data.get("schedule", []))

    def set_schedule(self, jobs: list[dict[str, Any]]) -> None:
        self._data["schedule"] = jobs
        self.save()

    def reactions(self) -> list[dict[str, Any]]:
        return list(self._data.get("reactions", []))

    def set_reactions(self, rules: list[dict[str, Any]]) -> None:
        self._data["reactions"] = rules
        self.save()

    def screens(self) -> list[dict[str, Any]]:
        return list(self._data.get("screens", []))

    def set_screens(self, screens: list[dict[str, Any]]) -> None:
        self._data["screens"] = screens
        self.save()

    def climate_entity(self) -> str:
        return str(self._data.get("climate_entity", "") or "")

    def set_climate_entity(self, entity: str) -> None:
        self._data["climate_entity"] = str(entity or "")
        self.save()

    def mood(self) -> dict[str, Any]:
        return dict(self._data.get("mood", {}))

    def set_mood(self, mood: dict[str, Any]) -> None:
        self._data["mood"] = mood
        self.save()

    def vitals(self) -> dict[str, Any]:
        return dict(self._data.get("vitals", {}))

    def set_vitals(self, vitals: dict[str, Any]) -> None:
        self._data["vitals"] = vitals
        self.save()

    def nudges_enabled(self) -> bool:
        return bool(self._data.get("nudges_enabled", True))

    def set_nudges_enabled(self, enabled: bool) -> None:
        self._data["nudges_enabled"] = bool(enabled)
        self.save()

    def language(self) -> str | None:
        return self._data.get("language")

    def set_language(self, language: str | None) -> None:
        self._data["language"] = language or None
        self.save()

    def wellness_tips(self) -> list[str]:
        """Custom wellness tip texts; a non-empty list replaces the built-in tips as-is."""
        tips = self._data.get("wellness_tips") or []
        return [t for t in tips if isinstance(t, str) and t.strip()]

    # ── typed helpers ──────────────────────────────────────────────────────────
    def ai_provider(self) -> str | None:
        return self._data.get("ai_provider")

    def set_ai_provider(self, provider: str | None) -> None:
        self._data["ai_provider"] = provider
        self.save()

    def mode_config(self, name: str) -> dict[str, Any]:
        return dict(self._data.get("mode_overrides", {}).get(name, {}))

    def set_mode_config(self, name: str, config: dict[str, Any]) -> None:
        self._data.setdefault("mode_overrides", {})[name] = config
        self.save()

    def is_disabled(self, name: str) -> bool:
        return name in self._data.get("disabled_modes", [])

    def set_disabled(self, name: str, disabled: bool) -> None:
        current = set(self._data.get("disabled_modes", []))
        current.add(name) if disabled else current.discard(name)
        self._data["disabled_modes"] = sorted(current)
        self.save()
