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


def test_clear_all(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            c.post("/api/agent/status", json={"state": "working", "source": "a"})
            c.post("/api/agent/status", json={"state": "working", "source": "b"})
            snap = c.post("/api/agent/status/clear").json()
            assert snap["agents"] == [] and snap["winner"] is None
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_mute_pref_roundtrip(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            c.post("/api/agent/status", json={"state": "working", "source": "chatty"})
            snap = c.put("/api/agent/prefs", json={"muted": ["chatty"]}).json()
            assert snap["muted"] == ["chatty"]
            assert c.get("/api/agent/status").json()["muted"] == ["chatty"]
            # unmute
            assert c.put("/api/agent/prefs", json={"muted": []}).json()["muted"] == []
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_permission_request_decide_flow(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            r = c.post("/api/agent/permission",
                       json={"source": "claude", "tool": "Bash", "summary": "rm -rf build/"})
            assert r.status_code == 200
            req = r.json()
            pid = req["id"]
            assert req["decision"] == "pending" and req["agent"] == "claude"

            # asking flips the agent to waiting_permission (the winner) + shows in the snapshot
            snap = c.get("/api/agent/status").json()
            assert snap["winner"]["state"] == "waiting_permission"
            assert snap["permission"]["id"] == pid

            # poll → still pending, then approve → the poll reports approved
            assert c.get(f"/api/agent/permission/{pid}").json()["decision"] == "pending"
            decided = c.post(f"/api/agent/permission/{pid}/decide", json={"decision": "approve"}).json()
            assert decided["decision"] == "approved"
            assert c.get(f"/api/agent/permission/{pid}").json()["decision"] == "approved"

            # once decided, the prompt clears and the agent goes back to working
            snap = c.get("/api/agent/status").json()
            assert snap["permission"] is None
            assert snap["winner"]["state"] == "working"

            assert c.get("/api/agent/permission/nope").status_code == 404
            assert c.post("/api/agent/permission/nope/decide", json={"decision": "approve"}).status_code == 404
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_reject_sets_idle(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            pid = c.post("/api/agent/permission", json={"source": "ci", "summary": "deploy?"}).json()["id"]
            assert c.post(f"/api/agent/permission/{pid}/decide", json={"decision": "reject"}).json()["decision"] == "rejected"
            assert c.get("/api/agent/status").json()["winner"]["state"] == "idle"
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_short_for_robot_two_lines():
    from dravix.agent_status import _short_for_robot

    assert _short_for_robot("ls") == "ls"                       # short → unchanged
    assert _short_for_robot("a\n\n  b   c") == "a b c"          # whitespace/newlines collapsed
    long = _short_for_robot("rm -rf build/ && npm ci && npm run build && deploy --prod --force")
    assert len(long) <= 44 and long.endswith("..")             # clipped to ~2 lines


def test_permission_summary_full_on_dashboard_short_on_robot(tmp_path, monkeypatch):
    # the stored/dashboard summary stays FULL even though the robot text is compacted
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            full = "rm -rf build/ && npm ci && npm run build && deploy --prod --force"
            r = c.post("/api/agent/permission", json={"source": "claude", "summary": full}).json()
            assert r["summary"] == full                         # dashboard sees the whole thing
            assert c.get(f"/api/agent/permission/{r['id']}").json()["summary"] == full
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_badge_fits_and_keeps_state():
    from dravix.agent_status import _badge

    assert _badge("claude", "working") == "claude: working"
    assert _badge("", "working") == ""            # no name → no badge
    assert _badge("x", "idle") == ""               # idle → no badge
    long = _badge("a-very-long-project-folder-name-indeed", "waiting_permission")
    assert long.endswith("waiting permission") and len(long) <= 30  # state preserved, name clipped
