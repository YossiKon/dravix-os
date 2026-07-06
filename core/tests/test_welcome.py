"""Welcome-by-name: the greeting-line builder + Frigate face recognition (sub_label)."""
from __future__ import annotations

import importlib.util
import time

import pytest

from dravix.config import PLUGINS_DIR
from dravix.integrations.frigate import Frigate


def _load(plugin: str):
    path = PLUGINS_DIR / plugin / "mode.py"
    spec = importlib.util.spec_from_file_location(f"_test_plugin_{plugin}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pretty_and_greeting_line():
    w = _load("welcome")
    assert w._pretty("person.yossi") == "Yossi"
    assert w._pretty("dana_k") == "Dana k"
    assert w._pretty("") == ""

    assert w._greeting_line("Welcome back, {name}!", "Yossi", False) == "Welcome back, Yossi!"
    assert w._greeting_line("ברוך שובך, {name}!", "יוסי", True) == "ברוך שובך, יוסי!"
    assert w._greeting_line("Hi", "Dana", False) == "Hi Dana"
    assert w._greeting_line("", "Dana", False) == "Welcome back, Dana!"
    # an unknown person + a {name} template → the clean default, never a dangling comma
    assert w._greeting_line("Welcome back, {name}!", "", False) == "Welcome back!"
    assert w._greeting_line("", "", True) == "ברוך שובך!"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._d


class _Client:
    def __init__(self, data):
        self._d = data

    async def get(self, url, params=None):
        return _Resp(self._d)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_latest_face_reads_sub_label():
    now = time.time()
    fresh = [{"start_time": now, "sub_label": ["yossi", 0.92]}]  # sub_label can be [name, score]
    assert await Frigate(None, "http://frigate:5000", _Client(fresh)).latest_face("cam") == "yossi"

    stale = [{"start_time": now - 999, "sub_label": "yossi"}]    # too old → ignored
    assert await Frigate(None, "http://frigate:5000", _Client(stale)).latest_face("cam") is None

    none = [{"start_time": now, "sub_label": None}]              # detected but not recognised
    assert await Frigate(None, "http://frigate:5000", _Client(none)).latest_face("cam") is None

    # no Frigate base URL → never calls out, returns None
    assert await Frigate(None, "", _Client(fresh)).latest_face("cam") is None
