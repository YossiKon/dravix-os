"""Voice setup — is "Okay Nabu" actually wired to something that can answer, and one click
to wire it through Home Assistant Cloud.

The robot's wake word and listening face are on-device; everything after them — hearing the
words (speech-to-text), deciding what to say (a conversation agent) and saying it
(text-to-speech) — is a Home Assistant *Assist pipeline*, chosen per satellite in HA's own
settings. When any of those three is missing the robot listens and then simply goes quiet,
which is indistinguishable from "it heard nothing". This module reads what HA actually has
wired to the robot and says, in words, what is missing — and, for a Nabu Casa subscriber,
builds the whole thing: a pipeline with cloud speech in the chosen language, the robot pointed
at it, and dravix's own voice moved onto the same engine.

Read-only parts ask HA a few questions over its WebSocket API — each opens and closes a
connection, so they run on demand (a dashboard card, a button), never on a loop.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .integrations.homeassistant import HomeAssistant
    from .store import Store

# HA's built-in conversation agent — always present, needs no entity lookup.
HA_BUILTIN_AGENT = "conversation.home_assistant"
# The satellite's pipeline select shows this when it follows HA's preferred pipeline.
OPTION_PREFERRED = "preferred"
# Home Assistant Cloud (Nabu Casa) speech engines — fixed entity ids in HA core.
CLOUD_STT = "stt.home_assistant_cloud"
CLOUD_TTS = "tts.home_assistant_cloud"
# The pipeline dravix creates for the robot. Found again by its stored id, then by this name.
PIPELINE_NAME = "Dravix"
# Canonical region for a short language code (cloud voices are listed per full tag).
_REGION = {"he": "he-IL", "en": "en-US"}

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


def _by_id(states: list[dict] | dict[str, dict]) -> dict[str, dict]:
    return states if isinstance(states, dict) else {s.get("entity_id", ""): s for s in states}


def satellite_select(devices: list[dict], prefix: str | None) -> tuple[str | None, str]:
    """The robot's pipeline SELECT entity from ``assist_pipeline/device/list`` — taken verbatim,
    matched to the robot by the discovered prefix. Returns (entity_id, reason) where reason is
    "" / "none" (no satellites at all) / "ambiguous" (several, none matched)."""
    devices = [d for d in (devices or []) if d.get("pipeline_entity")]
    if not devices:
        return None, "none"
    if prefix:
        for d in devices:
            object_id = str(d["pipeline_entity"]).split(".", 1)[-1]
            if object_id.startswith(prefix):
                return str(d["pipeline_entity"]), ""
    if len(devices) == 1:
        return str(devices[0]["pipeline_entity"]), ""
    return None, "ambiguous"


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
    by_id = _by_id(states)
    checks: list[dict[str, Any]] = []
    out: dict[str, Any] = {"configured": False, "satellite": None, "pipeline": None, "checks": checks}

    # 1 · is the robot a voice satellite at all, and which one?
    sel_id, why = satellite_select(devices, prefix)
    if sel_id is None:
        if why == "none":
            checks.append(_check("satellite", False, "missing",
                                 "Home Assistant לא רואה את הרובוט כלוויין קולי — האם מכשיר ה-ESPHome אומץ ומחובר?",
                                 "Home Assistant doesn't list the robot as a voice satellite — is the ESPHome device adopted and connected?"))
        else:
            n = len([d for d in devices if d.get("pipeline_entity")])
            checks.append(_check("satellite", False, "ambiguous",
                                 f"יש {n} לוויינים קוליים ב-HA ולא הצלחתי לזהות איזה הוא הרובוט",
                                 f"{n} voice satellites in HA — couldn't tell which one is the robot"))
        out["problems"] = 1
        return out

    # 2 · which pipeline is it set to follow?
    selected = (by_id.get(sel_id) or {}).get("state")
    out["satellite"] = {"pipeline_entity": sel_id, "selected": selected,
                        "device_count": len([d for d in devices if d.get("pipeline_entity")])}
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


# ── Home Assistant Cloud (Nabu Casa) ─────────────────────────────────────────────────────────

def cloud_available(status: dict | None, states: list[dict] | dict[str, dict]) -> dict[str, Any]:
    """Pure: is cloud speech usable? Logged in + a subscription + both engine entities present."""
    by_id = _by_id(states)
    logged_in = bool(status and status.get("logged_in"))
    sub = bool(status and status.get("active_subscription"))
    stt, tts = CLOUD_STT in by_id, CLOUD_TTS in by_id
    return {"available": logged_in and sub and stt and tts, "logged_in": logged_in,
            "subscription": sub, "stt": stt, "tts": tts}


def pick_cloud_voice(tts_info: dict | None, language: str) -> tuple[str, str] | None:
    """Pure: (tts_language, voice_id) for a short code, from ``cloud/tts/info``'s
    ``[language, voice_id, name]`` rows. Prefers the canonical region and a plain voice over a
    "voice|style" variant. None when the cloud has no voice for that language."""
    short = (language or "").lower().split("-")[0]
    rows = [r for r in ((tts_info or {}).get("languages") or []) if len(r) >= 2
            and str(r[0]).lower().split("-")[0] == short]
    if not rows:
        return None
    prefer = _REGION.get(short)
    rows.sort(key=lambda r: (str(r[0]) != prefer, "|" in str(r[1])))
    return str(rows[0][0]), str(rows[0][1])


def pick_stt_language(providers: list[dict] | None, engine: str, language: str) -> str:
    """Pure: the full tag the STT engine advertises for a short code (``stt/engine/list``);
    the canonical region when the engine lists it, else its first match, else the canonical
    region on faith (HA validates the pair itself)."""
    short = (language or "").lower().split("-")[0]
    prefer = _REGION.get(short, short)
    for p in providers or []:
        if p.get("engine_id") != engine:
            continue
        langs = [str(x) for x in (p.get("supported_languages") or []) if str(x).lower().split("-")[0] == short]
        if prefer in langs:
            return prefer
        if langs:
            return langs[0]
    return prefer


def cloud_pipeline_fields(language: str, stt_language: str, tts_language: str, voice: str) -> dict[str, Any]:
    """Pure: the complete create/update payload HA requires (every key, nulls explicit)."""
    short = (language or "en").lower().split("-")[0]
    return {
        "name": PIPELINE_NAME, "language": short,
        "conversation_engine": HA_BUILTIN_AGENT, "conversation_language": short,
        "stt_engine": CLOUD_STT, "stt_language": stt_language,
        "tts_engine": CLOUD_TTS, "tts_language": tts_language, "tts_voice": voice,
        "wake_word_entity": None, "wake_word_id": None, "prefer_local_intents": True,
    }


async def _ws_soft(ha: "HomeAssistant", message: dict[str, Any]) -> Any:
    """A WS question that may not exist on this HA (cloud not loaded, older core) → None."""
    try:
        return await ha._ws_command(message)
    except Exception:  # noqa: BLE001 — absence is an answer here
        return None


async def check_voice_setup(ha: "HomeAssistant", discovered: dict[str, str]) -> dict[str, Any]:
    """Fetch what HA has and diagnose it. Never raises — a HA too old for these commands
    (or unreachable) comes back as a single failed check, not a 500."""
    try:
        pl = await ha._ws_command({"type": "assist_pipeline/pipeline/list"}) or {}
        devices = await ha._ws_command({"type": "assist_pipeline/device/list"}) or []
        states = await ha.states()
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the dashboard
        return {
            "configured": False, "satellite": None, "pipeline": None, "problems": 1, "languages": [],
            "cloud": {"available": False},
            "checks": [_check("ha", False, "error",
                              f"לא הצלחתי לשאול את Home Assistant על ה-Assist pipelines: {exc}",
                              f"Couldn't query Home Assistant's Assist pipelines: {exc}")],
        }
    langs = await _ws_soft(ha, {"type": "assist_pipeline/language/list"}) or {}
    result = diagnose(pl.get("pipelines") or [], pl.get("preferred_pipeline"), devices, states,
                      robot_prefix(discovered or {}))
    result["languages"] = (langs or {}).get("languages") or []
    result["cloud"] = cloud_available(await _ws_soft(ha, {"type": "cloud/status"}), states)
    return result


async def connect_cloud(ha: "HomeAssistant", discovered: dict[str, str], store: "Store | None",
                        language: str) -> dict[str, Any]:
    """Wire the robot's voice through Home Assistant Cloud, in one go:
    1. a pipeline named PIPELINE_NAME with cloud STT + TTS in ``language`` and HA's built-in
       agent — updated in place if dravix made one before (by stored id, then by name), never
       touching any other pipeline and never changing HA's preferred one;
    2. the robot's satellite pointed at it (its select's options refresh a beat after a create,
       so this waits for the name to appear before choosing it);
    3. dravix's own speech moved onto the same engine and voice, so dashboard chat and
       notifications speak in the same voice — the caller rebuilds the driver afterwards.
    Returns a plain result; the caller re-runs the diagnosis for the fresh picture."""
    short = (language or "en").lower().split("-")[0] or "en"
    states = await ha.states()
    cloud = cloud_available(await _ws_soft(ha, {"type": "cloud/status"}), states)
    if not cloud["available"]:
        return {"ok": False, "cloud": cloud,
                "he": "Home Assistant Cloud לא זמין — צריך להיות מחובר עם מנוי פעיל, ומנועי הדיבור של הענן צריכים להופיע ב-HA",
                "en": "Home Assistant Cloud isn't available — log in with an active subscription; the cloud speech engines must show up in HA"}
    picked = pick_cloud_voice(await _ws_soft(ha, {"type": "cloud/tts/info"}), short)
    if picked is None:
        return {"ok": False, "cloud": cloud,
                "he": f"ל-Home Assistant Cloud אין קול דיבור לשפה „{short}”",
                "en": f"Home Assistant Cloud has no text-to-speech voice for \"{short}\""}
    tts_language, voice = picked
    providers = (await _ws_soft(ha, {"type": "stt/engine/list"}) or {}).get("providers")
    stt_language = pick_stt_language(providers, CLOUD_STT, short)
    fields = cloud_pipeline_fields(short, stt_language, tts_language, voice)

    pipelines = (await ha._ws_command({"type": "assist_pipeline/pipeline/list"}) or {}).get("pipelines") or []
    pid = store.voice_pipeline_id() if store is not None else None
    existing = next((p for p in pipelines if pid and p.get("id") == pid), None) \
        or next((p for p in pipelines if p.get("name") == PIPELINE_NAME), None)
    if existing is not None:
        await ha._ws_command({"type": "assist_pipeline/pipeline/update", "pipeline_id": existing["id"], **fields})
        pid = existing["id"]
    else:
        created = await ha._ws_command({"type": "assist_pipeline/pipeline/create", **fields}) or {}
        pid = created.get("id")
    if store is not None and pid:
        store.set_voice_pipeline_id(pid)

    # point the robot at it — the select's option list catches up a moment after a create
    devices = await ha._ws_command({"type": "assist_pipeline/device/list"}) or []
    sel_id, _why = satellite_select(devices, robot_prefix(discovered or {}))
    assigned = False
    if sel_id:
        for _ in range(6):
            st = await ha.get_state(sel_id)
            if PIPELINE_NAME in ((st.get("attributes") or {}).get("options") or []):
                await ha.call_service("select", "select_option", {"entity_id": sel_id, "option": PIPELINE_NAME})
                assigned = True
                break
            await asyncio.sleep(0.4)

    # dravix's own voice follows the engine (a Piper voice name would fail on the cloud engine)
    if store is not None:
        ents = store.robot_entities()
        ents["tts_engine"] = CLOUD_TTS
        store.set_robot_entities(ents)
        store.set_voice(voice)
    return {"ok": True, "cloud": cloud, "pipeline_id": pid, "pipeline": PIPELINE_NAME,
            "updated": existing is not None, "language": short, "stt_language": stt_language,
            "tts_language": tts_language, "voice": voice, "satellite": sel_id, "assigned": assigned}
