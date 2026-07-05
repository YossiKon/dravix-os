"""Physical notification gesture endpoint (LED colour + nod + optional speech)."""
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


def test_notify_kinds_and_colors(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            r = c.post("/api/robot/notify", json={"kind": "doorbell", "text": "someone's at the door"})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True
            assert body["color"] == "#009E73"          # doorbell = green
            assert body["spoken"] is True               # mock supports speech, not asleep

            # an unknown kind falls back to info/teal; say=False stays silent
            r2 = c.post("/api/robot/notify", json={"kind": "whatever", "text": "hi", "say": False}).json()
            assert r2["color"] == "#2EE6C8" and r2["spoken"] is False
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()
