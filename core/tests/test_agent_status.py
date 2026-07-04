"""Agent presence API: report a state, reflect it on the robot, read it back."""
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


def test_report_and_read_back(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            # starts idle
            assert c.get("/api/agent/status").json()["state"] == "idle"

            r = c.post("/api/agent/status", json={"state": "waiting_permission", "text": "rm build/?"})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True
            assert body["state"] == "waiting_permission" and body["text"] == "rm build/?"
            assert body["updated_at"]  # a timestamp was stamped

            # readable both from the dedicated endpoint and the main status snapshot
            assert c.get("/api/agent/status").json()["state"] == "waiting_permission"
            assert c.get("/api/status").json()["agent"]["state"] == "waiting_permission"
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_unknown_state_rejected(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.post("/api/agent/status", json={"state": "banana"}).status_code == 400
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()
