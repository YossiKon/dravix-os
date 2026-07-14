"""Known people (face recognition): store sanitization + /api/people + per-person greeting."""
from __future__ import annotations

import importlib.util
import pathlib

from fastapi.testclient import TestClient

from dravix.config import PLUGINS_DIR
from dravix.store import Store


def test_store_people_sanitizes(tmp_path: pathlib.Path):
    st = Store(tmp_path / "store.json")
    st.set_people([
        {"name": "  Yossi ", "line": "Hey {name}!", "line_he": "היי {name}!", "primary": True},
        {"name": "yossi", "primary": True},          # duplicate (case-insensitive) → dropped
        {"name": "Dana", "primary": True},           # second primary → demoted (first wins)
        {"name": ""},                                # no name → dropped
        "not-a-dict",                                # junk → dropped
    ])
    people = st.people()
    assert [p["name"] for p in people] == ["Yossi", "Dana"]
    assert people[0]["primary"] is True
    assert people[1]["primary"] is False
    # case-insensitive lookup finds the record
    assert st.person("YOSSI")["line"] == "Hey {name}!"
    assert st.person("nobody") is None
    # survives a reload from disk
    assert Store(tmp_path / "store.json").person("yossi")["line_he"] == "היי {name}!"


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("DRAVIX_ROBOT_DRIVER", "mock")
    monkeypatch.setenv("DRAVIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRAVIX_HA_URL", "")
    monkeypatch.setenv("DRAVIX_HA_TOKEN", "")
    monkeypatch.setenv("DRAVIX_XIAOZHI_MCP_URL", "")
    monkeypatch.setenv("DRAVIX_API_TOKEN", "")
    from dravix.config import get_settings

    get_settings.cache_clear()
    from dravix.app import create_app

    return create_app()


def test_people_endpoints_roundtrip(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.get("/api/people").json() == {"people": []}
            r = c.put("/api/people", json={"people": [
                {"name": "Yossi", "line": "Welcome home, {name}!", "primary": True},
                {"name": "Dana"},
            ]})
            names = [p["name"] for p in r.json()["people"]]
            assert names == ["Yossi", "Dana"]
            # the echo is the SANITIZED list — every record has the full shape
            assert all(set(p) == {"name", "line", "line_he", "primary"} for p in r.json()["people"])
            assert c.get("/api/people").json()["people"][0]["primary"] is True
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def _load_welcome():
    path = PLUGINS_DIR / "welcome" / "mode.py"
    spec = importlib.util.spec_from_file_location("_test_plugin_welcome_people", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_welcome_uses_the_persons_own_line(tmp_path):
    """The Settings → People record wins over the mode's generic greeting line."""
    w = _load_welcome()
    st = Store(tmp_path / "store.json")
    st.set_people([{"name": "Yossi", "line": "The king is back, {name}!", "primary": True}])

    class _Ctx:
        store = st
        config = {"line": "Generic hello", "primary": ""}

    mode = w.WelcomeMode.__new__(w.WelcomeMode)  # skip __init__ — only _person is exercised
    mode.ctx = _Ctx()
    person = mode._person("yossi")
    assert person["line"] == "The king is back, {name}!"
    assert person["primary"] is True
    assert mode._person("stranger") == {}
    # and the line builder honours it end-to-end
    assert w._greeting_line(person["line"], "Yossi", False) == "The king is back, Yossi!"
