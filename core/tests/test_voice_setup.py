"""The voice-setup diagnosis is pure: feed it what HA would report, read the verdict."""
from __future__ import annotations

from dravix.voice_setup import HA_BUILTIN_AGENT, diagnose, robot_prefix

PIPE_OK = {
    "id": "p1", "name": "Robot", "language": "en", "stt_engine": "stt.faster_whisper",
    "tts_engine": "tts.piper", "conversation_engine": HA_BUILTIN_AGENT,
    "wake_word_entity": None, "prefer_local_intents": True,
}
DEVICES = [{"device_id": "d1", "pipeline_entity": "select.dravix_assistant"}]
STATES = [
    {"entity_id": "select.dravix_assistant", "state": "preferred"},
    {"entity_id": "stt.faster_whisper", "state": "idle"},
    {"entity_id": "tts.piper", "state": "idle"},
]


def _problems(r):
    return [c["key"] for c in r["checks"] if not c["ok"]]


def test_prefix_from_discovery():
    assert robot_prefix({"mode_select": "select.dravix_mode"}) == "dravix"
    assert robot_prefix({"face_select": "select.study_room_dravix_face"}) == "study_room_dravix"
    assert robot_prefix({}) is None


def test_healthy_pipeline_via_preferred():
    r = diagnose([PIPE_OK], "p1", DEVICES, STATES, "dravix")
    assert r["configured"] is True and r["problems"] == 0
    assert r["pipeline"]["name"] == "Robot"
    assert r["satellite"]["selected"] == "preferred"


def test_missing_stt_is_named():
    r = diagnose([{**PIPE_OK, "stt_engine": None}], "p1", DEVICES, STATES, "dravix")
    assert _problems(r) == ["stt"]
    assert "speech-to-text" in next(c for c in r["checks"] if c["key"] == "stt")["en"]


def test_engine_configured_but_not_running_is_absent_not_missing():
    states = [s for s in STATES if s["entity_id"] != "tts.piper"]   # Piper add-on stopped
    r = diagnose([PIPE_OK], "p1", DEVICES, states, "dravix")
    c = next(c for c in r["checks"] if c["key"] == "tts")
    assert c["ok"] is False and c["level"] == "absent"


def test_legacy_cloud_provider_is_not_flagged_as_a_problem():
    r = diagnose([{**PIPE_OK, "stt_engine": "cloud"}], "p1", DEVICES, STATES, "dravix")
    c = next(c for c in r["checks"] if c["key"] == "stt")
    assert c["ok"] is True and c["level"] == "unknown"
    assert r["configured"] is True


def test_named_selection_beats_preferred_and_a_vanished_name_is_reported():
    other = {**PIPE_OK, "id": "p2", "name": "Kitchen", "tts_engine": None}
    states = [{"entity_id": "select.dravix_assistant", "state": "Kitchen"}] + STATES[1:]
    r = diagnose([PIPE_OK, other], "p1", DEVICES, states, "dravix")
    assert r["pipeline"]["name"] == "Kitchen" and _problems(r) == ["tts"]
    states[0]["state"] = "Gone"
    r = diagnose([PIPE_OK, other], "p1", DEVICES, states, "dravix")
    assert _problems(r) == ["pipeline"]


def test_no_satellite_and_ambiguous_satellites():
    r = diagnose([PIPE_OK], "p1", [], STATES, "dravix")
    assert _problems(r) == ["satellite"] and r["pipeline"] is None
    two = DEVICES + [{"device_id": "d2", "pipeline_entity": "select.kitchen_assistant"}]
    r = diagnose([PIPE_OK], "p1", two, STATES, None)          # no prefix, two devices
    assert _problems(r) == ["satellite"]
    r = diagnose([PIPE_OK], "p1", two, STATES, "dravix")      # prefix picks the robot
    assert r["configured"] is True
