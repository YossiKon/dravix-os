"""Tests for the persistent store and the engine's use of it (overrides + disabled)."""
from __future__ import annotations

import pytest

from dravix.config import PLUGINS_DIR
from dravix.dal.base import RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.modes import ModeContext, ModeEngine
from dravix.state import RobotState
from dravix.store import Store


def test_store_persists(tmp_path):
    path = tmp_path / "store.json"
    s = Store(path)
    assert s.ai_provider() is None
    s.set_ai_provider("claude")
    s.set_mode_config("focus", {"led_color": "green"})
    s.set_disabled("guard", True)
    assert path.exists()

    # Reload from disk — values survive.
    s2 = Store(path)
    assert s2.ai_provider() == "claude"
    assert s2.mode_config("focus") == {"led_color": "green"}
    assert s2.is_disabled("guard") is True
    s2.set_disabled("guard", False)
    assert Store(path).is_disabled("guard") is False


def test_store_survives_corrupt_file(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("{not json", encoding="utf-8")
    s = Store(path)  # must not raise
    assert s.ai_provider() is None


def test_export_reimports_cleanly_after_normal_use(tmp_path):
    """A full /api/export payload must pass /api/import's validate_patch — every key that gets
    written into the store during normal operation (personality drift, agent prefs) or from the
    dashboard (dashboard_url, spontaneous_speech) must be in _UPDATABLE_KEYS, or restore 400s.
    This regression-guards the backup/restore round-trip."""
    s = Store(tmp_path / "s.json")
    # keys written by background operation / the dashboard that used to be missing from the
    # importable set (personality persists after ~20 min uptime → broke restore for everyone)
    s.set_personality({"valence": 0.1, "arousal": 0.3, "days": 2})
    s.set_agent_prefs(display="badge")
    s.set_dashboard_url("http://homeassistant.local:10000/lovelace/0?viewport=320x240")
    s.set_spontaneous_speech(True)
    # a real backup is just to_dict(); re-importing it must report zero bad keys
    assert s.validate_patch(s.to_dict()) == []


async def _controller() -> RobotController:
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    return c


async def test_engine_applies_store_overrides_and_disabled(tmp_path):
    store = Store(tmp_path / "s.json")
    store.set_disabled("ambient_idle", True)
    store.set_mode_config("focus", {"greet": "", "led_color": "green"})
    c = await _controller()
    engine = ModeEngine(
        PLUGINS_DIR, ModeContext(robot=c, bus=c._bus), tick_interval=0.05, store=store
    )
    engine.discover()
    await engine.start()
    try:
        # disabled ambient mode is not auto-started
        assert "ambient_idle" not in engine.ambient_active
        # config override reaches the running instance
        await engine.activate("focus")
        assert engine._fg_instance.ctx.config.get("led_color") == "green"
        # disabling a mode blocks activation
        await engine.deactivate()
        store.set_disabled("focus", True)
        with pytest.raises(ValueError):
            await engine.activate("focus")
    finally:
        await engine.stop()
        await c.close()
