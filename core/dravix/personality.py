"""Personality drift — the robot slowly *becomes its own* over weeks.

The mood engine ([[mood]]) holds a fast-moving affective state (valence / arousal /
affection). This is the SLOW counterpart: a hidden temperament vector on three axes that
drifts a tiny, capped amount **once per day** toward how the robot was treated that day — so
two units raised differently grow distinct personalities. It's persisted, fully local, and
surfaced on the dashboard as a temperament readout.

Axes (value -1..+1, left↔right):
  * ``energy``     — calm ↔ excitable   (follows arousal)
  * ``boldness``   — shy ↔ bold         (follows valence + arousal)
  * ``attachment`` — independent ↔ clingy (follows affection)
"""
from __future__ import annotations

import datetime

# axis key -> (left label he/en, right label he/en)
_AXES: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "energy": (("רגוע", "calm"), ("נלהב", "excitable")),
    "boldness": (("ביישן", "shy"), ("נועז", "bold")),
    "attachment": (("עצמאי", "independent"), ("מתרפק", "clingy")),
}
_MAX_STEP_PER_DAY = 0.08   # ~25 days of consistent treatment to swing an axis fully


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _targets(valence: float, arousal: float, affection: float) -> dict[str, float]:
    """Where today's mood would pull each axis (-1..+1)."""
    return {
        "energy": _clamp((arousal - 0.35) * 2.2),
        "boldness": _clamp(valence * 0.7 + (arousal - 0.4) * 1.2),
        "attachment": _clamp((affection - 0.35) * 2.2),
    }


class Personality:
    def __init__(self, store) -> None:  # noqa: ANN001 — the persistence store
        self._store = store
        d = {}
        try:
            d = dict(store.personality()) if hasattr(store, "personality") else {}
        except Exception:  # noqa: BLE001
            d = {}
        axes = dict(d.get("axes") or {})
        self.axes: dict[str, float] = {k: float(axes.get(k, 0.0)) for k in _AXES}
        acc = dict(d.get("acc") or {})
        self._acc: dict[str, list[float]] = {
            k: [float((acc.get(k) or [0.0, 0.0])[0]), float((acc.get(k) or [0.0, 0.0])[1])] for k in _AXES
        }
        self._last_date: str = str(d.get("last_date") or "")
        self.days: int = int(d.get("days") or 0)

    def _persist(self) -> None:
        if hasattr(self._store, "set_personality"):
            try:
                self._store.set_personality({
                    "axes": self.axes, "acc": self._acc,
                    "last_date": self._last_date, "days": self.days,
                })
            except Exception:  # noqa: BLE001 — persistence is best-effort
                pass

    def observe(
        self, valence: float, arousal: float, affection: float, *, today: str | None = None,
    ) -> None:
        """Fold one mood sample into today's running average; when the day rolls over, apply a
        single capped drift step toward yesterday's average and start a fresh day."""
        day = today or datetime.date.today().isoformat()
        tg = _targets(valence, arousal, affection)
        if self._last_date and day != self._last_date and self._acc[next(iter(_AXES))][1] > 0:
            for k in _AXES:
                s, n = self._acc[k]
                avg = s / n if n else 0.0
                step = _clamp(avg - self.axes[k], -_MAX_STEP_PER_DAY, _MAX_STEP_PER_DAY)
                self.axes[k] = _clamp(self.axes[k] + step)
                self._acc[k] = [0.0, 0.0]
            self.days += 1
        # accumulate today's sample
        for k in _AXES:
            self._acc[k][0] += tg[k]
            self._acc[k][1] += 1.0
        self._last_date = day
        self._persist()

    def snapshot(self) -> dict:
        axes = []
        for k, (left, right) in _AXES.items():
            v = round(self.axes[k], 3)
            axes.append({
                "key": k, "value": v,
                "left_he": left[0], "left_en": left[1],
                "right_he": right[0], "right_en": right[1],
            })
        return {"axes": axes, "days": self.days, "settled": self.days >= 14}
