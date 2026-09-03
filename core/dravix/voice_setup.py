"""Voice setup check — is "Okay Nabu" actually wired to something that can answer?

The robot's wake word and listening face are on-device; everything after them — hearing the
words (speech-to-text), deciding what to say (a conversation agent) and saying it
(text-to-speech) — is a Home Assistant *Assist pipeline*, chosen per satellite in HA's own
settings. When any of those three is missing the robot listens and then simply goes quiet,
which is indistinguishable from "it heard nothing". This module reads what HA actually has
wired to the robot and says, in words, what is missing.

Read-only. It asks HA three questions over its WebSocket API (``assist_pipeline/pipeline/list``,
``assist_pipeline/device/list``, ``assist_pipeline/language/list``) — each opens and closes a
connection, so it runs on demand (a dashboard card, a Re-check button), never on a loop.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .integrations.homeassistant import HomeAssistant

# HA's built-in conversation agent — always present, needs no entity lookup.
HA_BUILTIN_AGENT = "conversation.home_assistant"
# The satellite's pipeline select shows this when it follows HA's preferred pipeline.
OPTION_PREFERRED = "preferred"

# (discovery role, its object-id suffix) — any of these pins the robot's entity-id prefix
_PREFIX_ROLES = (("mode_select", "mode"), ("face_select", "face"), ("state_sensor", "state"),
                 ("bubble_text", "bubble"), ("media_player", "media_player"))


def robot_prefix(discovered: dict[str, str]) -> str | None:
    """The robot's entity-id prefix ("dravix" in select.dravix_mode), from discovery."""
    for role, suffix in _PREFIX_ROLES:
        eid = discovered.get(role)
        if not eid or "." not in eid:
            continue
        object_id = eid.split(".", 1)[1]
        tail = "_" + suffix
        if object_id.endswith(tail) and len(object_id) > len(tail):
            return object_id[: -len(tail)]
    return None


def _check(key: str, ok: bool, level: str, he: str, en: str) -> dict[str, Any]:
    return {"key": key, "ok": ok, "level": level, "he": he, "en": en}


def _engine_check(kind: str, engine: str | None, states: dict[str, dict]) -> dict[str, Any]:
    """One of the pipeline's three engines. Four outcomes, because two of them look alike
    from the robot: MISSING (nothing chosen) · ABSENT (chosen, but its entity isn't in HA —
    the add-on is stopped or was removed) · OK · UNKNOWN (a legacy provider name with no
    entity to look up — a cloud provider, usually; can't verify from here)."""
    labels = {
        "stt": ("המרת דיבור לטקסט", "speech-to-text"),
        "conversation": ("סוכן שיחה", "conversation agent"),
        "tts": ("המרת טקסט לדיבור", "text-to-speech"),
    }
    fixes = {
        "stt": ("התקן את התוסף Whisper (מקומי) או השתמש ב-Home Assistant Cloud, ובחר אותו ב-pipeline",
                "Install the Whisper add-on (local) or use Home Assistant Cloud, then pick it in the pipeline"),
        "conversation": ("בחר סוכן שיחה ב-pipeline — Home Assistant (מובנה) מספיק לשליטה בבית; LLM לצ'אט",
                         "Pick a conversation agent in the pipeline — Home Assistant (built-in) is enough for control; an LLM for chat"),
        "tts": ("התקן את התוסף Piper (מקומי, אנגלית) או השתמש ב-Home Assistant Cloud, ובחר אותו ב-pipeline",
                "Install the Piper add-on (local, English) or use Home Assistant Cloud, then pick it in the pipeline"),
    }
    he_l, en_l = labels[kind]
    if not engine:
        return _check(kind, False, "missing",
                      f"אין {he_l} ב-pipeline — הרובוט מקשיב ואז שותק. {fixes[kind][0]}",
                      f"No {en_l} in the pipeline — the robot listens, then goes quiet. {fixes[kind][1]}")
    if engine == HA_BUILTIN_AGENT:
        return _check(kind, True, "ok", f"{he_l}: Home Assistant (מובנה)", f"{en_l}: Home Assistant (built-in)")
    if "." in engine:
        st = states.get(engine)
        if st is None or st.get("state") in ("unavailable", None):
            return _check(kind, False, "absent",
                          f"{he_l} מוגדר ({engine}) אבל לא רץ ב-Home Assistant — התוסף שלו כבוי או הוסר",
                          f"{en_l} is set ({engine}) but isn't running in Home Assistant — its add-on is stopped or gone")
        return _check(kind, True, "ok", f"{he_l}: {engine}", f"{en_l}: {engine}")
    return _check(kind, True, "unknown",
                  f"{he_l}: {engine} (ספק חיצוני — לא ניתן לאמת מכאן)",
                  f"{en_l}: {engine} (an external provider — can't be verified from here)")


def diagnose(pipelines: list[dict], preferred_id: str | None, devices: list[dict],
             states: list[dict] | dict[str, dict], prefix: str | None) -> dict[str, Any]:
    """Pure: given what HA reports, say what the robot's voice path looks like."""
    by_id = states if isinstance(states, dict) else {s.get("entity_id", ""): s for s in states}
    checks: list[dict[str, Any]] = []
    out: dict[str, Any] = {"configured": False, "satellite": None, "pipeline": None, "checks": checks}

    # 1 · is the robot a voice satellite at all?
    devices = [d for d in (devices or []) if d.get("pipeline_entity")]
    if not devices:
        checks.append(_check("satellite", False, "missing",
                             "Home Assistant לא רואה את הרובוט כלוויין קולי — האם מכשיר ה-ESPHome אומץ ומחובר?",
                             "Home Assistant doesn't list the robot as a voice satellite — is the ESPHome device adopted and connected?"))
        out["problems"] = 1
        return out
    mine = None
    if prefix:
        for d in devices:
            object_id = str(d["pipeline_entity"]).split(".", 1)[-1]
            if object_id.startswith(prefix):
                mine = d
                break
    if mine is None and len(devices) == 1:
        mine = devices[0]
    if mine is None:
        checks.append(_check("satellite", False, "ambiguous",
                             f"יש {len(devices)} לוויינים קוליים ב-HA ולא הצלחתי לזהות איזה הוא הרובוט",
                             f"{len(devices)} voice satellites in HA — couldn't tell which one is the robot"))
        out["problems"] = 1
        return out

    # 2 · which pipeline is it set to follow?
    sel_id = str(mine["pipeline_entity"])
    selected = (by_id.get(sel_id) or {}).get("state")
    sat = {"pipeline_entity": sel_id, "selected": selected, "device_count": len(devices)}
    out["satellite"] = sat
    pipeline = None
    if selected and selected not in (OPTION_PREFERRED, "unknown", "unavailable"):
        pipeline = next((p for p in pipelines if p.get("name") == selected), None)
        if pipeline is None:
            checks.append(_check("pipeline", False, "missing",
                                 f"הרובוט מוגדר ל-pipeline בשם „{selected}” שכבר לא קיים — בחר אחר בעמוד המכשיר",
                                 f"The robot is set to a pipeline named \"{selected}\" that no longer exists — pick another on its device page"))
    if pipeline is None and not any(c["key"] == "pipeline" for c in checks):
        pipeline = next((p for p in pipelines if p.get("id") == preferred_id), None) or (pipelines[0] if len(pipelines) == 1 else None)
        if pipeline is None:
            checks.append(_check("pipeline", False, "missing",
                                 "אין pipeline של Assist ב-Home Assistant — צור אחד: הגדרות → עוזרים קוליים → הוסף עוזר",
                                 "No Assist pipeline exists in Home Assistant — create one: Settings → Voice assistants → Add assistant"))
    if pipeline is None:
        out["problems"] = sum(1 for c in checks if not c["ok"])
        return out

    out["pipeline"] = {k: pipeline.get(k) for k in (
        "id", "name", "language", "stt_engine", "tts_engine", "conversation_engine",
        "wake_word_entity", "prefer_local_intents")}

    # 3 · the three engines, in the order a turn uses them
    for kind, field in (("stt", "stt_engine"), ("conversation", "conversation_engine"), ("tts", "tts_engine")):
        checks.append(_engine_check(kind, pipeline.get(field), by_id))
    lang = pipeline.get("language") or "?"
    checks.append(_check("language", True, "info",
                         f"שפת ה-pipeline: {lang} — הרובוט יבין ויענה בשפה הזאת",
                         f"Pipeline language: {lang} — the robot understands and answers in this language"))
    if pipeline.get("wake_word_entity"):
        checks.append(_check("wake_word", True, "info",
                             "ב-pipeline מוגדרת גם מילת השכמה בצד HA; מילת ההשכמה של הרובוט רצה על המכשיר עצמו — זה עובד כך או כך",
                             "The pipeline also has an HA-side wake word; the robot's wake word runs on the device itself — it works either way"))
    out["problems"] = sum(1 for c in checks if not c["ok"])
    out["configured"] = out["problems"] == 0
    return out


async def check_voice_setup(ha: "HomeAssistant", discovered: dict[str, str]) -> dict[str, Any]:
    """Fetch what HA has and diagnose it. Never raises — a HA too old for these commands
    (or unreachable) comes back as a single failed check, not a 500."""
    try:
        pl = await ha._ws_command({"type": "assist_pipeline/pipeline/list"}) or {}
        devices = await ha._ws_command({"type": "assist_pipeline/device/list"}) or []
        try:
            langs = await ha._ws_command({"type": "assist_pipeline/language/list"}) or {}
        except Exception:  # noqa: BLE001 — nice-to-have; older HA lacks it
            langs = {}
        states = await ha.states()
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the dashboard
        return {
            "configured": False, "satellite": None, "pipeline": None, "problems": 1, "languages": [],
            "checks": [_check("ha", False, "error",
                              f"לא הצלחתי לשאול את Home Assistant על ה-Assist pipelines: {exc}",
                              f"Couldn't query Home Assistant's Assist pipelines: {exc}")],
        }
    result = diagnose(pl.get("pipelines") or [], pl.get("preferred_pipeline"), devices, states,
                      robot_prefix(discovered or {}))
    result["languages"] = (langs or {}).get("languages") or []
    return result
