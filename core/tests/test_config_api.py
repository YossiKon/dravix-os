"""End-to-end test of the config API via the real app (TestClient runs the lifespan)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_config_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAVIX_ROBOT_DRIVER", "mock")
    monkeypatch.setenv("DRAVIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRAVIX_HA_URL", "")
    monkeypatch.setenv("DRAVIX_HA_TOKEN", "")

    from dravix.config import get_settings

    get_settings.cache_clear()
    from dravix.app import create_app

    try:
        with TestClient(create_app()) as client:
            assert client.get("/api/config").status_code == 200

            # Switch the AI provider live to ollama (no API key needed).
            r = client.put("/api/config/ai_provider", json={"provider": "ollama"})
            assert r.status_code == 200
            assert r.json()["ai_provider"] == "ollama"
            assert r.json()["ai_available"] is True

            # Override a mode's config.
            r = client.put("/api/config/modes/focus", json={"config": {"led_color": "green"}})
            assert r.status_code == 200
            assert r.json()["config"] == {"led_color": "green"}

            # Disable a mode → activating it is rejected with 409.
            assert client.post("/api/config/modes/focus/disabled", json={"disabled": True}).status_code == 200
            assert client.post("/api/modes/focus/activate").status_code == 409

            # Unknown mode → 404.
            assert client.post("/api/config/modes/nope/disabled", json={"disabled": True}).status_code == 404

            # Fun games + time speak work; weather without a configured entity → 400.
            assert "dice" in client.get("/api/fun").json()["games"]
            assert client.post("/api/fun/dice").status_code == 200
            assert client.post("/api/say/time").status_code == 200
            assert client.post("/api/say/weather").status_code == 400

            # Memory: "remember ..." stores a fact (no AI needed).
            r = client.post("/api/ai/chat", json={"text": "remember that I like tea", "speak": False})
            assert r.status_code == 200 and r.json().get("remembered") == "I like tea"
            assert any(m["text"] == "I like tea" for m in client.get("/api/memory").json()["memories"])

            # Routines: define + run; unknown → 404.
            client.put("/api/routines", json={"routines": [{"name": "hi", "steps": [{"say": "hello", "emote": "yes"}]}]})
            assert client.post("/api/routines/hi/run").status_code == 200
            assert client.post("/api/routines/none/run").status_code == 404

            # Voice override applies live.
            assert client.put("/api/voice", json={"voice": "piper-amy"}).json()["voice"] == "piper-amy"
            assert client.get("/api/voice").json()["voice"] == "piper-amy"

            # Frigate cameras with no HA configured → empty list.
            assert client.get("/api/frigate/cameras").json()["cameras"] == []
            # Robot camera relay: mock yields no real frame → 503 (not a crash).
            assert client.get("/camera/robot/snapshot.jpg").status_code == 503

            # Store was persisted to the temp data dir.
            assert (tmp_path / "store.json").exists()
    finally:
        get_settings.cache_clear()
