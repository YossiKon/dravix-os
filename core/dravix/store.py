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
}


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
        keys = (
            "ai_provider", "mode_overrides", "disabled_modes", "reactions", "schedule",
            "personas", "active_persona", "memories", "routines", "voice", "voices", "inbox",
        )
        for key in keys:
            if key in patch:
                self._data[key] = patch[key]
        self.save()

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

    def voice(self) -> str | None:
        return self._data.get("voice")

    def set_voice(self, voice: str | None) -> None:
        self._data["voice"] = voice
        self.save()

    def idle_motion(self) -> bool:
        return bool(self._data.get("idle_motion", True))

    def set_idle_motion(self, enabled: bool) -> None:
        self._data["idle_motion"] = bool(enabled)
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

    def mood(self) -> dict[str, Any]:
        return dict(self._data.get("mood", {}))

    def set_mood(self, mood: dict[str, Any]) -> None:
        self._data["mood"] = mood
        self.save()

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
