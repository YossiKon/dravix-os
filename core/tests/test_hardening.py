"""Tests for the hardening fixes: API token auth, import validation, SSRF guards,
reaction-pump resilience, vitals quiet-set/tips, and the mode-options 400."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.reactions import ReactionEngine
from dravix.state import RobotState


def _app(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DRAVIX_ROBOT_DRIVER", "mock")
    monkeypatch.setenv("DRAVIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRAVIX_HA_URL", "")
    monkeypatch.setenv("DRAVIX_HA_TOKEN", "")
    monkeypatch.setenv("DRAVIX_XIAOZHI_MCP_URL", "")
    monkeypatch.setenv("DRAVIX_API_TOKEN", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from dravix.config import get_settings

    get_settings.cache_clear()
    from dravix.app import create_app

    return create_app()


def _cleanup():
    from dravix.config import get_settings

    get_settings.cache_clear()


# ── API token middleware ───────────────────────────────────────────────────────
def test_api_token_required_when_set(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path, DRAVIX_API_TOKEN="sekrit")
    try:
        with TestClient(app) as client:
            # /api/health stays open for probes.
            assert client.get("/api/health").status_code == 200
            # Everything else under /api/ and /camera/ needs the token.
            assert client.get("/api/status").status_code == 401
            assert client.get("/camera/robot/snapshot.jpg").status_code == 401
            # All three supply mechanisms work.
            assert client.get(
                "/api/status", headers={"Authorization": "Bearer sekrit"}
            ).status_code == 200
            assert client.get("/api/status", headers={"X-API-Token": "sekrit"}).status_code == 200
            assert client.get("/api/status", params={"token": "sekrit"}).status_code == 200
            # A wrong token is rejected.
            assert client.get("/api/status", headers={"X-API-Token": "nope"}).status_code == 401
    finally:
        _cleanup()


def test_no_token_setting_leaves_api_open(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as client:
            assert client.get("/api/status").status_code == 200
    finally:
        _cleanup()


# ── /api/import validation + SSRF guards + mode options ───────────────────────
def test_import_validation_and_ssrf_guards(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as client:
            # Unknown key → 400 naming it.
            r = client.post("/api/import", json={"store": {"nope": 1}})
            assert r.status_code == 400 and "nope" in r.json()["detail"]
            # Wrong types → 400 (list key given a string, bool key given a string).
            assert client.post("/api/import", json={"store": {"voices": "x"}}).status_code == 400
            assert client.post(
                "/api/import", json={"store": {"nudges_enabled": "yes"}}
            ).status_code == 400
            assert client.post(
                "/api/import", json={"store": {"robot_entities": ["not", "a", "dict"]}}
            ).status_code == 400
            # A valid patch (incl. the new language/wellness_tips keys) applies.
            r = client.post("/api/import", json={"store": {
                "voices": ["v1"], "language": "he", "wellness_tips": ["drink water"],
            }})
            assert r.status_code == 200
            # A full export → import round-trip stays valid.
            exported = client.get("/api/export").json()
            assert client.post("/api/import", json={"store": exported}).status_code == 200

            # show_image: only http(s) URLs are accepted.
            assert client.post(
                "/api/robot/show_image", json={"url": "file:///etc/passwd"}
            ).status_code == 400
            assert client.post(
                "/api/robot/show_image", json={"url": "gopher://x/1"}
            ).status_code == 400
            # frigate/show: camera must be a bare Frigate name or a camera.* entity.
            assert client.post(
                "/api/frigate/show", json={"camera": "../admin"}
            ).status_code == 400
            assert client.post(
                "/api/frigate/show", json={"camera": "front door?x=1"}
            ).status_code == 400

            # mode: a driver that reports its real select options → 400 listing them.
            class _FakeModeDrv:
                async def mode_options(self):
                    return ["awake", "sleep"]

                async def set_mode(self, mode):
                    raise RuntimeError("invalid option")

            app.state.robot._driver = _FakeModeDrv()
            r = client.post("/api/robot/mode", json={"mode": "focus"})
            assert r.status_code == 400
            assert "awake" in r.json()["detail"] and "sleep" in r.json()["detail"]
            # A mode the select claims to accept but HA rejects → also 400 with options.
            r = client.post("/api/robot/mode", json={"mode": "sleep"})
            assert r.status_code == 400 and "awake" in r.json()["detail"]
    finally:
        _cleanup()


# ── reaction pump resilience ───────────────────────────────────────────────────
class _MutableStore:
    def __init__(self, rules):
        self.rules = rules

    def reactions(self):
        return self.rules


async def test_reaction_pump_survives_bad_rule():
    bus = EventBus()
    controller = RobotController(MockDriver(), bus, RobotState())
    await controller.connect()
    store = _MutableStore([None])  # a malformed rule: not even a dict
    eng = ReactionEngine(controller, bus, store=store)
    await eng.start()
    try:
        await bus.publish("tick")  # the bad rule raises inside handle()
        await asyncio.sleep(0.05)
        store.rules = [{"name": "ok", "on": "tick", "say": "still alive"}]
        await bus.publish("tick")  # the pump must still be running
        await asyncio.sleep(0.05)
        assert controller.state.last_said == "still alive"
    finally:
        await eng.stop()
        await controller.close()


# ── vitals: quiet-set inversion + tips language/override ──────────────────────
async def _vitals(store=None):
    from dravix.vitals import VitalsEngine

    bus = EventBus()
    controller = RobotController(MockDriver(), bus, RobotState())
    await controller.connect()
    return VitalsEngine(bus, controller, store=store)


async def test_vitals_unknown_mode_counts_as_active():
    v = await _vitals()
    for quiet in ("sleep", "night", "screensaver", "quiet", "focus", "busy"):
        assert v._active(quiet) is False
    # Unknown/new firmware states must NOT silence the robot.
    assert v._active("awake") is True
    assert v._active("party") is True
    assert v._active(None) is True


def test_wellness_nudges_allowed_in_focus():
    # focus = the user is definitely at the desk (work/gaming DND) — exactly when the
    # eye/move/water reminders matter. The autonomy set still silences focus antics.
    from dravix.vitals import _NUDGE_QUIET_MODES, _QUIET_MODES

    assert "focus" not in _NUDGE_QUIET_MODES
    assert "focus" in _QUIET_MODES
    for m in ("sleep", "night", "screensaver", "quiet", "busy"):
        assert m in _NUDGE_QUIET_MODES


async def test_vitals_tips_language_and_override(tmp_path, monkeypatch):
    from dravix.config import get_settings
    from dravix.store import Store

    monkeypatch.setenv("DRAVIX_LANG", "en")
    get_settings.cache_clear()
    try:
        store = Store(tmp_path / "store.json")
        v = await _vitals(store)
        texts = [t for _, t in v._nudges().values()]
        assert "Time to drink some water" in texts  # env default: English
        store.set_language("he")
        texts = [t for _, t in v._nudges().values()]
        assert "כדאי לשתות קצת מים" in texts  # store override: Hebrew
        store.update({"wellness_tips": ["custom tip"]})
        nudges = v._nudges()
        assert [t for _, t in nudges.values()] == ["custom tip"]  # custom list wins as-is
        assert all(interval > 0 for interval, _ in nudges.values())
    finally:
        get_settings.cache_clear()
