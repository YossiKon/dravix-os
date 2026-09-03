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


# ── Home Assistant Cloud: the pure halves of the one-click connect ───────────────
def test_cloud_available_needs_login_subscription_and_both_engines():
    from dravix.voice_setup import CLOUD_STT, CLOUD_TTS, cloud_available

    both = [{"entity_id": CLOUD_STT, "state": "idle"}, {"entity_id": CLOUD_TTS, "state": "idle"}]
    assert cloud_available({"logged_in": True, "active_subscription": True}, both)["available"] is True
    assert cloud_available({"logged_in": True, "active_subscription": False}, both)["available"] is False
    assert cloud_available(None, both)["available"] is False          # cloud integration not loaded
    assert cloud_available({"logged_in": True, "active_subscription": True}, both[:1])["available"] is False


def test_pick_cloud_voice_prefers_region_and_plain_voice():
    from dravix.voice_setup import pick_cloud_voice

    info = {"languages": [
        ["en-GB", "SoniaNeural", "Sonia"], ["en-US", "JennyNeural|cheerful", "Jenny (cheerful)"],
        ["en-US", "JennyNeural", "Jenny"], ["he-IL", "HilaNeural", "Hila"], ["he-IL", "AvriNeural", "Avri"],
    ]}
    assert pick_cloud_voice(info, "he") == ("he-IL", "HilaNeural")
    assert pick_cloud_voice(info, "en") == ("en-US", "JennyNeural")   # region first, no style variant
    assert pick_cloud_voice(info, "fr") is None
    assert pick_cloud_voice(None, "he") is None


def test_pick_stt_language_from_engine_list():
    from dravix.voice_setup import CLOUD_STT, pick_stt_language

    providers = [{"engine_id": CLOUD_STT, "supported_languages": ["en-GB", "en-US", "he-IL"]},
                 {"engine_id": "stt.faster_whisper", "supported_languages": ["en"]}]
    assert pick_stt_language(providers, CLOUD_STT, "he") == "he-IL"
    assert pick_stt_language(providers, CLOUD_STT, "en") == "en-US"
    assert pick_stt_language([{"engine_id": CLOUD_STT, "supported_languages": ["en-AU"]}], CLOUD_STT, "en") == "en-AU"
    assert pick_stt_language(None, CLOUD_STT, "he") == "he-IL"        # command missing → canonical on faith


def test_cloud_pipeline_fields_are_complete():
    from dravix.voice_setup import CLOUD_STT, CLOUD_TTS, HA_BUILTIN_AGENT, cloud_pipeline_fields

    f = cloud_pipeline_fields("he", "he-IL", "he-IL", "HilaNeural")
    for k in ("name", "language", "conversation_engine", "conversation_language", "stt_engine",
              "stt_language", "tts_engine", "tts_language", "tts_voice", "wake_word_entity", "wake_word_id"):
        assert k in f, k                                          # HA requires every one of these
    assert f["stt_engine"] == CLOUD_STT and f["tts_engine"] == CLOUD_TTS
    assert f["conversation_engine"] == HA_BUILTIN_AGENT and f["wake_word_entity"] is None
    assert f["prefer_local_intents"] is True


def test_no_satellite_and_ambiguous_satellites():
    r = diagnose([PIPE_OK], "p1", [], STATES, "dravix")
    assert _problems(r) == ["satellite"] and r["pipeline"] is None
    two = DEVICES + [{"device_id": "d2", "pipeline_entity": "select.kitchen_assistant"}]
    r = diagnose([PIPE_OK], "p1", two, STATES, None)          # no prefix, two devices
    assert _problems(r) == ["satellite"]
    r = diagnose([PIPE_OK], "p1", two, STATES, "dravix")      # prefix picks the robot
    assert r["configured"] is True


# ── a renamed device really does carry TWO prefixes (seen in the wild) ───────────
def test_two_prefixes_are_both_found_and_either_matches_the_satellite():
    from dravix.voice_setup import robot_prefixes, satellite_select

    # this is a real robot: our own text/state entities were re-registered under the area
    # prefix after a rename, while the BSP's selects kept the old slug
    disc = {"mode_select": "select.dravix_mode", "face_select": "select.dravix_face",
            "bubble_text": "text.mmd_room_dravix_bubble",
            "state_sensor": "sensor.mmd_room_dravix_state"}
    assert robot_prefixes(disc) == ["mmd_room_dravix", "dravix"]     # longest first
    devices = [{"device_id": "d1", "pipeline_entity": "select.mmd_room_dravix_assistant"},
               {"device_id": "d2", "pipeline_entity": "select.kitchen_assistant"}]
    sel, why = satellite_select(devices, robot_prefixes(disc))
    assert sel == "select.mmd_room_dravix_assistant" and why == ""
    # the shorter prefix alone used to miss it entirely
    assert satellite_select(devices, "dravix")[0] is None
