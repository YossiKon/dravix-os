"""Agent presence API: multi-agent registry, winner selection, prefs, dismiss."""
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


def test_single_agent_report_and_read_back(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            # starts empty — no winner
            snap = c.get("/api/agent/status").json()
            assert snap["winner"] is None and snap["agents"] == []
            assert snap["display"] == "both"
            assert "palette" in snap  # colour-blind-safe palette rides along

            r = c.post("/api/agent/status",
                       json={"state": "waiting_permission", "text": "rm build/?", "source": "claude"})
            assert r.status_code == 200
            win = r.json()["winner"]
            assert win["name"] == "claude" and win["state"] == "waiting_permission"
            assert win["text"] == "rm build/?"

            assert c.get("/api/status").json()["agent"]["winner"]["state"] == "waiting_permission"
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_two_agents_urgency_wins(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            c.post("/api/agent/status", json={"state": "working", "source": "proj-a"})
            snap = c.post("/api/agent/status",
                          json={"state": "waiting_permission", "source": "proj-b"}).json()
            # both listed; the one needing approval wins over the one merely working
            assert {a["name"] for a in snap["agents"]} == {"proj-a", "proj-b"}
            assert snap["winner"]["name"] == "proj-b"

            # pin proj-a as primary → it wins even though proj-b is more urgent
            c.put("/api/agent/prefs", json={"primary": "proj-a"})
            snap = c.get("/api/agent/status").json()
            assert snap["winner"]["name"] == "proj-a"
            assert snap["primary"] == "proj-a"
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_dismiss_and_display_pref(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            c.post("/api/agent/status", json={"state": "done", "source": "ci"})
            assert c.get("/api/agent/status").json()["winner"]["name"] == "ci"

            snap = c.delete("/api/agent/status/ci").json()
            assert snap["winner"] is None and snap["agents"] == []

            assert c.put("/api/agent/prefs", json={"display": "badge"}).json()["display"] == "badge"
            assert c.put("/api/agent/prefs", json={"display": "nonsense"}).status_code == 400
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
