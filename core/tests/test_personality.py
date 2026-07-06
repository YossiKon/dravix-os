"""Personality drift: once-per-day, capped steps toward how the robot was treated."""
from __future__ import annotations

from dravix.personality import Personality, _MAX_STEP_PER_DAY, _targets


class _Store:
    def __init__(self):
        self.saved = {}

    def personality(self):
        return dict(self.saved)

    def set_personality(self, data):
        self.saved = dict(data)


def test_targets_direction():
    # high arousal → excitable(+), high affection → clingy(+), low everything → negative
    hi = _targets(valence=0.8, arousal=0.9, affection=0.9)
    assert hi["energy"] > 0.5 and hi["boldness"] > 0.3 and hi["attachment"] > 0.5
    lo = _targets(valence=-0.5, arousal=0.1, affection=0.1)
    assert lo["energy"] < 0 and lo["attachment"] < 0


def test_drift_is_slow_and_daily():
    p = Personality(_Store())
    # many samples on day 1 only ACCUMULATE — no drift yet (axes still 0)
    for _ in range(50):
        p.observe(0.9, 0.9, 0.9, today="2026-07-01")
    assert p.axes["energy"] == 0.0 and p.days == 0

    # rolling into day 2 applies ONE capped step toward the (excitable/clingy) average
    p.observe(0.9, 0.9, 0.9, today="2026-07-02")
    assert p.days == 1
    assert 0 < p.axes["energy"] <= _MAX_STEP_PER_DAY + 1e-9    # capped, positive
    assert 0 < p.axes["attachment"] <= _MAX_STEP_PER_DAY + 1e-9

    # a full swing takes many days, never overshoots ±1
    for i in range(400):
        day = f"2026-07-{(i % 27) + 1:02d}" if i < 27 else f"2026-08-{(i % 27) + 1:02d}"
        p.observe(1.0, 1.0, 1.0, today=day)
    assert p.axes["energy"] <= 1.0 and p.axes["attachment"] <= 1.0


def test_persists_across_restart():
    store = _Store()
    p = Personality(store)
    p.observe(0.9, 0.9, 0.9, today="2026-07-01")
    p.observe(0.9, 0.9, 0.9, today="2026-07-02")
    energy = p.axes["energy"]
    # a fresh instance from the same store resumes where it left off
    p2 = Personality(store)
    assert p2.axes["energy"] == energy and p2.days == p.days


def test_snapshot_shape():
    snap = Personality(_Store()).snapshot()
    assert {a["key"] for a in snap["axes"]} == {"energy", "boldness", "attachment"}
    assert snap["days"] == 0 and snap["settled"] is False
    assert all(-1.0 <= a["value"] <= 1.0 for a in snap["axes"])
