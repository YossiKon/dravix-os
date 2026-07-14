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

            # Agenda needs HA → 503 here.
            assert client.post("/api/say/agenda").status_code == 503
            # Notify queues, inbox lists, play clears.
            assert client.post("/api/notify", json={"text": "dinner ready", "speak": False}).json()["queued"] is True
            assert len(client.get("/api/inbox").json()["messages"]) == 1
            assert client.post("/api/inbox/play").json()["spoken"] == 1
            assert client.get("/api/inbox").json()["messages"] == []
            # AI games list works; running one fails cleanly here (provider set to ollama but
            # not running → 502, or 503 if no provider) — never a crash.
            assert "joke" in client.get("/api/ai/fun").json()["kinds"]
            assert client.post("/api/ai/fun/joke").status_code in (502, 503)

            # Generic event ingest (e.g. the robot's head-touch sensor → the bus).
            assert client.post("/api/event", json={"type": "touch.pet"}).status_code == 200

            # Mood self-report; export/import of the whole config.
            assert client.post("/api/say/mood").status_code == 200
            exported = client.get("/api/export").json()
            assert "personas" in exported and "schedule" in exported
            assert client.post("/api/import", json={"store": {"voices": ["imported-voice"]}}).status_code == 200
            assert client.get("/api/voice").json()["voices"] == ["imported-voice"]

            # Climate config round-trips through the store; state/set need HA → 503 here.
            assert client.get("/api/config/climate").json()["entity"] == ""
            assert client.put("/api/config/climate", json={"entity": "climate.ac"}).json()["entity"] == "climate.ac"
            assert client.get("/api/config/climate").json()["entity"] == "climate.ac"
            assert client.get("/api/climate/state", params={"entity_id": "climate.ac"}).status_code == 503
            assert client.post("/api/climate/set", json={"entity_id": "climate.ac", "temperature": 22}).status_code == 503

            # Dashboard URL round-trips through the store; scheme is validated; empty clears it.
            # No HA configured here, so it's stored but not pushed to a robot.
            assert client.get("/api/config/dashboard_url").json()["url"] == ""
            r = client.put(
                "/api/config/dashboard_url",
                json={"url": "http://homeassistant.local:10000/lovelace/0?viewport=320x240"},
            )
            assert r.status_code == 200 and r.json()["pushed"] is False
            assert client.get("/api/config/dashboard_url").json()["url"].endswith("viewport=320x240")
            assert client.put("/api/config/dashboard_url", json={"url": "ftp://nope"}).status_code == 400
            assert client.put("/api/config/dashboard_url", json={"url": ""}).json()["url"] == ""

            # "Speaks on its own" toggle round-trips and shows up in /api/config's store.
            assert client.get("/api/config").json()["store"].get("spontaneous_speech") in (None, False)
            r = client.put("/api/robot/spontaneous-speech", json={"enabled": True})
            assert r.status_code == 200 and r.json()["spontaneous_speech"] is True
            assert client.get("/api/config").json()["store"]["spontaneous_speech"] is True

            # Robot mode: the mock driver has no mode control → 409; a bad mode → 400.
            assert client.post("/api/robot/mode", json={"mode": "sleep"}).status_code == 409
            assert client.post("/api/robot/mode", json={"mode": "nope"}).status_code == 400

            # Frigate cameras with no HA configured → empty list.
            assert client.get("/api/frigate/cameras").json()["cameras"] == []
            # Robot camera relay: mock yields no real frame → 503 (not a crash).
            assert client.get("/camera/robot/snapshot.jpg").status_code == 503

            # Store was persisted to the temp data dir.
            assert (tmp_path / "store.json").exists()
    finally:
        get_settings.cache_clear()
