"""Teleop endpoints: manual recording status + push-to-talk input validation."""
from __future__ import annotations

from fastapi.testclient import TestClient


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


def test_record_status_starts_idle(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            st = c.get("/api/record/status").json()
            assert st == {"recording": False, "name": None, "seconds": 0}
            # stopping when idle is a clean no-op, not an error
            assert c.post("/api/record/stop").json()["recording"] is False
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_talk_rejects_empty_audio(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            # body validation happens BEFORE any ffmpeg/HA dependency — offline-safe
            assert c.post("/api/robot/talk", content=b"").status_code == 400
            assert c.post("/api/robot/talk", content=b"tiny").status_code == 400
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_talk_clip_names_are_validated(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.get("/api/talk/../../etc/passwd").status_code in (400, 404)
            assert c.get("/api/talk/zzzz.mp3").status_code == 400
            assert c.get("/api/talk/0123456789ab.mp3").status_code == 404  # valid name, no file
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()
