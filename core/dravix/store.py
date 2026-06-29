"""Persistent runtime settings store (JSON-backed).

Holds the things a user changes at runtime — which AI provider to use, per-mode config
overrides, and which modes are disabled — so they survive restarts. Written atomically.
Env (`DRAVIX_*`) remains the source of *defaults*; the store only holds *overrides*.
"""
from __future__ import annotations

import json
import os
import pathlib
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
        for key in ("ai_provider", "mode_overrides", "disabled_modes", "reactions", "schedule"):
            if key in patch:
                self._data[key] = patch[key]
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
