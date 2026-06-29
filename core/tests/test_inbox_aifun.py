"""Tests for the notifications inbox (store) and the AI-games prompt set."""
from __future__ import annotations

from dravix.aifun import PROMPTS, kinds
from dravix.store import Store


def test_aifun_kinds():
    assert "joke" in kinds()
    assert all(k in PROMPTS for k in kinds())


def test_store_inbox(tmp_path):
    s = Store(tmp_path / "s.json")
    item = s.add_inbox("dinner is ready")
    assert item["id"] and item["text"] == "dinner is ready"
    assert len(s.inbox()) == 1
    assert Store(tmp_path / "s.json").inbox()[0]["text"] == "dinner is ready"  # persists
    s.clear_inbox()
    assert s.inbox() == []
