"""REST API consumed by the dashboard (and usable directly with curl)."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import datetime

from .. import __version__
from ..aifun import PROMPTS as AI_FUN_PROMPTS
from ..aifun import kinds as ai_fun_kinds
from ..app import build_ai, build_robot_driver
from ..dal.base import CAP_FACE, CAP_PHOTO, CAP_SAY, CapabilityError
from ..emotes import emote_names, play_emote
from ..fun import GAMES, game_names
from ..memory import build_memory_context
from ..persona import parse_expression, resolve_persona, resolve_voice
from ..routines import run_routine

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────
class SayBody(BaseModel):
    text: str
    voice: str | None = None


class FaceBody(BaseModel):
    expression: str


class HeadBody(BaseModel):
    # Normalised: -1..1 per axis, 0 = look straight. +1 = full right/up, -1 = full left/down.
    yaw: float = Field(..., ge=-1, le=1)
    pitch: float = Field(..., ge=-1, le=1)
    speed: float = Field(1.0, ge=0.0, le=1.0)


class LedsBody(BaseModel):
    color: str
    brightness: float = Field(1.0, ge=0.0, le=1.0)


class IdleMotionBody(BaseModel):
    enabled: bool


class ModeBody(BaseModel):
    mode: str  # awake | busy | sleep


class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    speak: bool = False


# ── helpers ───────────────────────────────────────────────────────────────────
def _robot(request: Request):
    return request.app.state.robot


def _engine(request: Request):
    return request.app.state.engine


async def _guard(coro):
    try:
        return await coro
    except CapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── routes ────────────────────────────────────────────────────────────────────
@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "dravix-os", "version": __version__}


@router.get("/api/status")
async def status(request: Request):
    runtime = request.app.state.runtime
    engine = request.app.state.engine
    data = runtime.to_dict()
    data["active_mode"] = engine.active
    data["ambient_modes"] = engine.ambient_active
    data["ai_available"] = request.app.state.ai is not None
    data["mood"] = request.app.state.mood.snapshot()
    data["idle_motion"] = getattr(request.app.state.robot, "idle_motion", True)
    xz = getattr(request.app.state, "xiaozhi", None)
    data["xiaozhi"] = {
        "configured": xz is not None,
        "connected": bool(xz and xz.connected),
        "last_error": (xz.last_error if xz else ""),
        "tools": (xz.tools if xz else []),
    }
    return data


@router.get("/api/modes")
async def list_modes(request: Request):
    return {"modes": _engine(request).list_modes(), "active": _engine(request).active}


@router.post("/api/modes/{name}/activate")
async def activate_mode(name: str, request: Request):
    try:
        await _engine(request).activate(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:  # e.g. mode is disabled
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"active": _engine(request).active}


@router.post("/api/modes/deactivate")
async def deactivate_mode(request: Request):
    await _engine(request).deactivate()
    return {"active": _engine(request).active}


@router.post("/api/robot/say")
async def robot_say(body: SayBody, request: Request):
    await _guard(_robot(request).say(body.text, body.voice))
    return {"ok": True}


@router.post("/api/robot/face")
async def robot_face(body: FaceBody, request: Request):
    await _guard(_robot(request).set_face(body.expression))
    return {"ok": True}


@router.post("/api/robot/head")
async def robot_head(body: HeadBody, request: Request):
    await _guard(_robot(request).move_head(body.yaw, body.pitch, body.speed))
    return {"ok": True}


@router.post("/api/robot/leds")
async def robot_leds(body: LedsBody, request: Request):
    await _guard(_robot(request).set_leds(body.color, body.brightness))
    return {"ok": True}


_ROBOT_MODES = {"awake", "busy", "sleep"}


@router.post("/api/robot/mode")
async def set_robot_mode(body: ModeBody, request: Request):
    """Put the robot to sleep / wake it via its HA ``mode_select`` entity."""
    mode = body.mode.strip().lower()
    if mode not in _ROBOT_MODES:
        raise HTTPException(status_code=400, detail=f"unknown mode {body.mode!r}")
    drv = request.app.state.robot.driver
    setter = getattr(drv, "set_mode", None)
    if setter is None:
        raise HTTPException(status_code=409, detail="active backend has no mode control")
    try:
        await setter(mode)
    except NotImplementedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "mode": mode}


@router.put("/api/robot/idle-motion")
async def set_idle_motion(body: IdleMotionBody, request: Request):
    """Enable/disable the robot's automatic idle head movement (manual control is unaffected)."""
    request.app.state.robot.idle_motion = body.enabled
    request.app.state.store.set_idle_motion(body.enabled)
    return {"idle_motion": body.enabled}


# ── robot wiring: pick the driver + HA entities + head calibration from the UI ──
# Each role → which HA domains are valid for its picker. The dashboard renders one
# dropdown per role, filtered to these domains.
ROBOT_ENTITY_ROLES = [
    {"key": "face_select", "label": "Face (expression)", "domains": ["select"]},
    {"key": "head_yaw", "label": "Head — left / right", "domains": ["number"]},
    {"key": "head_pitch", "label": "Head — up / down", "domains": ["number"]},
    {"key": "media_player", "label": "Speaker (for TTS)", "domains": ["media_player"]},
    {"key": "tts_engine", "label": "Voice — TTS engine or satellite",
     "domains": ["tts", "assist_satellite"]},
    {"key": "led_light", "label": "LED bar", "domains": ["light"]},
    {"key": "camera", "label": "Camera", "domains": ["camera"]},
    {"key": "screensaver_number", "label": "Screensaver-after (min)", "domains": ["number"]},
    {"key": "sleep_number", "label": "Sleep-after (min)", "domains": ["number"]},
    {"key": "mode_select", "label": "Mode (awake / busy / sleep)", "domains": ["select"]},
    # Live-state sensors published by the dravix ESPHome firmware (all optional):
    {"key": "state_sensor", "label": "Live state (State sensor)", "domains": ["sensor"]},
    {"key": "heard_sensor", "label": "Last heard (STT sensor)", "domains": ["sensor"]},
    {"key": "reply_sensor", "label": "Last reply (TTS sensor)", "domains": ["sensor"]},
    {"key": "image_url_text", "label": "Show-image URL (text)", "domains": ["text"]},
]
_ROLE_KEYS = {r["key"] for r in ROBOT_ENTITY_ROLES}


class RobotConfigBody(BaseModel):
    driver: str | None = None  # mock | ha | mcp
    entities: dict[str, str] | None = None  # {role: entity_id}
    calibration: dict | None = None  # {yaw:{center,min,max,invert}, pitch:{...}}


class ScreenBody(BaseModel):
    screensaver_min: float | None = Field(None, ge=0, le=1440)
    sleep_min: float | None = Field(None, ge=0, le=1440)


def _effective_entities(request: Request) -> dict[str, str]:
    s = request.app.state
    return {**s.settings.ha_robot_entities, **s.store.robot_entities()}


def _robot_config_payload(request: Request) -> dict:
    s = request.app.state
    st = s.robot.state
    return {
        "driver": (s.store.robot_driver() or s.settings.robot_driver),
        "drivers": ["mock", "ha", "mcp"],
        "roles": ROBOT_ENTITY_ROLES,
        "entities": _effective_entities(request),
        "calibration": s.store.head_calibration(),
        "capabilities": list(st.capabilities),
        "online": st.online,
        "last_error": getattr(st, "last_error", "") or "",
        "ha_configured": s.ha is not None,
    }


async def _apply_robot_config(request: Request) -> str | None:
    """Rebuild the driver from the merged config and reconnect. Returns an error string or None."""
    s = request.app.state
    try:
        driver = build_robot_driver(s.settings, s.store, s.ha)
        await s.robot.reconnect_with(driver)
    except Exception as exc:  # noqa: BLE001 — surface as a field, don't 500
        s.robot.state.online = False
        s.robot.state.last_error = str(exc)
        return str(exc)
    return None


@router.get("/api/ha/entities")
async def ha_entities(request: Request, domains: str = ""):
    """List Home Assistant entities (optionally filtered by comma-separated domains) for the
    dashboard's entity pickers. Returns [] if HA isn't configured."""
    ha = request.app.state.ha
    if ha is None:
        return {"entities": [], "ha_configured": False}
    want = {d.strip() for d in domains.split(",") if d.strip()}
    try:
        states = await ha.states()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"HA states fetch failed: {exc}") from exc
    out = []
    for stt in states:
        eid = stt.get("entity_id", "")
        dom = eid.split(".", 1)[0] if "." in eid else ""
        if want and dom not in want:
            continue
        attrs = stt.get("attributes") or {}
        out.append({
            "entity_id": eid,
            "name": attrs.get("friendly_name") or eid,
            "domain": dom,
        })
    out.sort(key=lambda e: (e["domain"], e["name"].lower()))
    return {"entities": out, "ha_configured": True}


@router.get("/api/robot/config")
async def get_robot_config(request: Request):
    return _robot_config_payload(request)


@router.put("/api/robot/config")
async def put_robot_config(body: RobotConfigBody, request: Request):
    s = request.app.state
    if body.driver is not None:
        if body.driver not in ("mock", "ha", "mcp"):
            raise HTTPException(status_code=400, detail=f"unknown driver {body.driver!r}")
        s.store.set_robot_driver(body.driver)
    if body.entities is not None:
        clean = {k: v for k, v in body.entities.items() if k in _ROLE_KEYS}
        s.store.set_robot_entities(clean)
    if body.calibration is not None:
        s.store.set_head_calibration(body.calibration)
    error = await _apply_robot_config(request)
    payload = _robot_config_payload(request)
    payload["error"] = error
    return payload


@router.post("/api/robot/head/home")
async def set_head_home(request: Request):
    """StackChan-style 'set current position as home': capture the servos' current angles as
    the calibrated centre (= look straight ahead). Position the head straight, then call this."""
    drv = request.app.state.robot.driver
    reader = getattr(drv, "read_head_raw", None)
    if reader is None:
        raise HTTPException(status_code=409, detail="active backend can't read head position")
    try:
        raw = await reader()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    calib = request.app.state.store.head_calibration()
    for axis in ("yaw", "pitch"):
        if raw.get(axis) is not None:
            calib.setdefault(axis, {})["center"] = raw[axis]
    request.app.state.store.set_head_calibration(calib)
    error = await _apply_robot_config(request)
    return {"calibration": request.app.state.store.head_calibration(), "captured": raw, "error": error}


@router.get("/api/robot/live")
async def robot_live(request: Request):
    """The robot's live state as published by the firmware: state / last heard / last reply.

    Everything is optional — roles that aren't mapped (or a backend without ``get_text``)
    simply come back as None, so the dashboard can render whatever is available.
    """
    drv = request.app.state.robot.driver
    reader = getattr(drv, "get_text", None)
    if reader is None:
        return {"supported": False, "state": None, "heard": None, "reply": None}
    state, heard, reply = await asyncio.gather(
        reader("state_sensor"), reader("heard_sensor"), reader("reply_sensor")
    )
    return {"supported": True, "state": state, "heard": heard, "reply": reply}


@router.get("/api/robot/screen")
async def get_screen(request: Request):
    """Read the on-device screensaver/sleep timeouts (the ESPHome number entities)."""
    drv = request.app.state.robot.driver
    getter = getattr(drv, "get_number", None)
    if getter is None:
        return {"supported": False, "screensaver_min": None, "sleep_min": None}
    return {
        "supported": True,
        "screensaver_min": await getter("screensaver_number"),
        "sleep_min": await getter("sleep_number"),
    }


@router.put("/api/robot/screen")
async def put_screen(body: ScreenBody, request: Request):
    """Set the screensaver / sleep timeouts on the robot (writes the ESPHome number entities)."""
    drv = request.app.state.robot.driver
    setter = getattr(drv, "set_number", None)
    if setter is None:
        raise HTTPException(status_code=409, detail="active backend has no screen timers")
    try:
        if body.screensaver_min is not None:
            await setter("screensaver_number", body.screensaver_min)
        if body.sleep_min is not None:
            await setter("sleep_number", body.sleep_min)
    except NotImplementedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/ai/chat")
async def ai_chat(body: ChatBody, request: Request):
    robot = _robot(request)
    store = request.app.state.store
    text = body.text.strip()

    # "remember ..." → store a fact (no LLM needed).
    if text.lower().startswith("remember "):
        fact = text[len("remember "):].strip()
        if fact.lower().startswith("that "):
            fact = fact[len("that "):].strip()
        if fact:
            store.add_memory(fact)
            confirm = "Got it — I'll remember that."
            if body.speak and robot.supports(CAP_FACE):
                try:
                    await robot.set_face("happy")
                except Exception:  # noqa: BLE001
                    pass
            if body.speak and robot.supports(CAP_SAY):
                try:
                    await robot.say(confirm)
                except Exception:  # noqa: BLE001
                    pass
            return {
                "text": confirm,
                "expression": "happy",
                "remembered": fact,
                "conversation_id": body.conversation_id,
            }

    ai = request.app.state.ai
    if ai is None:
        raise HTTPException(status_code=503, detail="AI provider not configured")
    # System prompt = active persona + remembered facts.
    system = resolve_persona(store).system_prompt
    mem = build_memory_context(store)
    if mem:
        system = f"{system}\n\n{mem}"
    reply = await _guard(ai.converse(body.text, system=system, conversation_id=body.conversation_id))
    expression, clean = parse_expression(reply.text)
    if body.speak:
        if robot.supports(CAP_FACE):
            try:
                await robot.set_face(expression)
            except Exception:  # noqa: BLE001 — emoting is best-effort
                pass
        if clean:
            try:
                await robot.say(clean)
            except Exception:  # noqa: BLE001 — speaking is best-effort
                pass
    return {
        "text": clean or reply.text,
        "expression": expression.value,
        "conversation_id": reply.conversation_id,
    }


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    """Stream event-bus events to the dashboard as JSON ``{type, data, ts}``."""
    await ws.accept()
    bus = ws.app.state.bus
    q = bus.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json({"type": event.type, "data": event.data, "ts": event.ts})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # noqa: BLE001 — never let a socket error crash the app
        pass
    finally:
        bus.unsubscribe(q)


# ── runtime configuration ─────────────────────────────────────────────────────
class AIProviderBody(BaseModel):
    provider: str | None = None  # None resets to the env default


class ModeConfigBody(BaseModel):
    config: dict = Field(default_factory=dict)


class DisabledBody(BaseModel):
    disabled: bool


def _rebuild_ai(request: Request) -> str | None:
    app = request.app
    try:
        app.state.ai = build_ai(app.state.settings, app.state.store, app.state.ha)
    except Exception as exc:  # noqa: BLE001 — surface as a field, don't 500
        app.state.ai = None
        return str(exc)
    app.state.runtime.ai_provider = app.state.store.ai_provider() or app.state.settings.ai_provider
    return None


def _known_mode(request: Request, name: str) -> bool:
    return any(m["name"] == name for m in _engine(request).list_modes())


@router.get("/api/config")
async def get_config(request: Request):
    s = request.app.state
    return {
        "store": s.store.to_dict(),
        "ai_provider": s.runtime.ai_provider,
        "ai_available": s.ai is not None,
        "providers": ["ha_assist", "claude", "openai", "ollama"],
        "local_only": s.settings.local_only,
        "cloud_providers": ["claude", "openai"],
    }


@router.put("/api/config/ai_provider")
async def set_ai_provider(body: AIProviderBody, request: Request):
    request.app.state.store.set_ai_provider(body.provider)
    error = _rebuild_ai(request)
    s = request.app.state
    return {"ai_provider": s.runtime.ai_provider, "ai_available": s.ai is not None, "error": error}


@router.put("/api/config/modes/{name}")
async def set_mode_config(name: str, body: ModeConfigBody, request: Request):
    if not _known_mode(request, name):
        raise HTTPException(status_code=404, detail=f"unknown mode {name!r}")
    request.app.state.store.set_mode_config(name, body.config)
    await _engine(request).reload(name)  # apply now if active
    return {"ok": True, "config": request.app.state.store.mode_config(name)}


@router.post("/api/config/modes/{name}/disabled")
async def set_mode_disabled(name: str, body: DisabledBody, request: Request):
    if not _known_mode(request, name):
        raise HTTPException(status_code=404, detail=f"unknown mode {name!r}")
    engine = _engine(request)
    request.app.state.store.set_disabled(name, body.disabled)
    if body.disabled and engine.is_active(name):
        await engine.deactivate(name)
    return {"disabled": body.disabled}


# ── camera / Frigate (all local) ──────────────────────────────────────────────
class ShowImageBody(BaseModel):
    url: str


class FrigateShowBody(BaseModel):
    camera: str | None = None
    alert: bool = False


@router.post("/api/robot/show_image")
async def robot_show_image(body: ShowImageBody, request: Request):
    """Display an image URL on the robot's screen.

    Preferred path: the robot downloads the URL itself (the firmware's Show-image slot).
    Fallback: fetch here and push the bytes (MCP driver)."""
    shower = getattr(request.app.state.robot.driver, "show_image_url", None)
    if shower is not None:
        try:
            await shower(body.url)
            return {"ok": True, "mode": "url"}
        except NotImplementedError:
            pass  # role not mapped — fall through to the bytes path
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    async with httpx.AsyncClient(timeout=10.0) as c:
        try:
            r = await c.get(body.url)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from exc
    await _guard(_robot(request).show_image(r.content))
    return {"ok": True, "bytes": len(r.content)}


@router.get("/api/frigate/cameras")
async def frigate_cameras(request: Request):
    try:
        return {"cameras": await request.app.state.frigate.cameras()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/frigate/show")
async def frigate_show(body: FrigateShowBody, request: Request):
    """Show a Frigate camera snapshot on the robot's screen (all local).

    With the ESPHome firmware + a direct Frigate URL, the robot downloads the snapshot
    itself (?height=240 keeps it light). Otherwise falls back to pushing the bytes."""
    s = request.app.state
    camera = body.camera or s.settings.frigate_camera
    if not camera:
        raise HTTPException(status_code=400, detail="no camera given and DRAVIX_FRIGATE_CAMERA is empty")
    shown = False
    shower = getattr(s.robot.driver, "show_image_url", None)
    frigate_base = (s.settings.frigate_url or "").rstrip("/")
    if shower is not None and frigate_base and not camera.startswith("camera."):
        try:
            await shower(f"{frigate_base}/api/{camera}/latest.jpg?height=240")
            shown = True
        except NotImplementedError:
            pass  # image slot not mapped — fall back to bytes below
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not shown:
        try:
            img = await s.frigate.snapshot(camera)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"frigate snapshot failed: {exc}") from exc
        await _guard(_robot(request).show_image(img))
    if body.alert and _robot(request).supports(CAP_FACE):
        try:
            await _robot(request).set_face("doubt")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "camera": camera, "mode": "url" if shown else "bytes"}


# Robot's own camera, served as a standard HTTP camera so Frigate (or HA) can ingest it.
@router.get("/camera/robot/snapshot.jpg", include_in_schema=False)
async def robot_camera_snapshot(request: Request):
    robot = _robot(request)
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=503, detail="robot has no camera capability")
    img = await _guard(robot.take_photo())
    if not img:
        raise HTTPException(status_code=503, detail="no frame from robot camera")
    return Response(content=img, media_type="image/jpeg")


@router.get("/camera/robot/stream.mjpeg", include_in_schema=False)
async def robot_camera_stream(request: Request, fps: float = 2.0):
    robot = _robot(request)
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=503, detail="robot has no camera capability")
    delay = 1.0 / max(0.2, min(fps, 10.0))

    async def frames():
        while True:
            try:
                img = await robot.take_photo()
            except Exception:  # noqa: BLE001
                img = None
            if img:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(img)).encode()
                    + b"\r\n\r\n"
                    + img
                    + b"\r\n"
                )
            await asyncio.sleep(delay)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


# ── announce + reactions ──────────────────────────────────────────────────────
class AnnounceBody(BaseModel):
    text: str
    expression: str | None = None


class ReactionsBody(BaseModel):
    reactions: list[dict]


@router.post("/api/announce")
async def announce(body: AnnounceBody, request: Request):
    """Speak a message (for HA automations, Frigate, etc.), with a matching face."""
    robot = _robot(request)
    if body.expression is None:
        expr, text = parse_expression(body.text)
        expr_value = expr.value
    else:
        expr_value, text = body.expression, body.text
    if robot.supports(CAP_FACE):
        try:
            await robot.set_face(expr_value)
        except Exception:  # noqa: BLE001
            pass
    if text:
        await _guard(robot.say(text))
    return {"ok": True}


@router.get("/api/reactions")
async def get_reactions(request: Request):
    return {"reactions": request.app.state.store.reactions()}


@router.put("/api/reactions")
async def put_reactions(body: ReactionsBody, request: Request):
    request.app.state.store.set_reactions(body.reactions)  # the engine reads these live
    return {"reactions": request.app.state.store.reactions()}


# ── screens (HA entities shown on the robot's 3 display cards) ─────────────────
class ScreensBody(BaseModel):
    screens: list[dict]


@router.get("/api/screens")
async def get_screens(request: Request):
    return {"screens": request.app.state.store.screens()}


@router.put("/api/screens")
async def put_screens(body: ScreensBody, request: Request):
    if len(body.screens) > 3:
        raise HTTPException(status_code=400, detail="at most 3 screen cards are allowed")
    clean: list[dict] = []
    for card in body.screens:
        if not isinstance(card, dict):
            raise HTTPException(status_code=400, detail="each card must be an object")
        entities = card.get("entities", [])
        if not isinstance(entities, list) or any(not isinstance(e, str) for e in entities):
            raise HTTPException(status_code=400, detail="card 'entities' must be a list of ids")
        clean.append({"title": str(card.get("title", "")), "entities": entities})
    request.app.state.store.set_screens(clean)  # the pusher reads these live
    return {"screens": request.app.state.store.screens()}


# ── climate (AC / thermostat control) ─────────────────────────────────────────
class ClimateSetBody(BaseModel):
    entity_id: str
    temperature: float | None = None
    hvac_mode: str | None = None


class ClimateConfigBody(BaseModel):
    entity: str = ""


@router.get("/api/climate/state")
async def get_climate_state(request: Request, entity_id: str):
    ha = request.app.state.ha
    if ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        st = await ha.get_state(entity_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"climate state fetch failed: {exc}") from exc
    attrs = st.get("attributes") or {}
    return {
        "state": st.get("state"),
        "current_temperature": attrs.get("current_temperature"),
        "temperature": attrs.get("temperature"),
        "hvac_mode": st.get("state"),
        "hvac_modes": attrs.get("hvac_modes"),
        "min_temp": attrs.get("min_temp"),
        "max_temp": attrs.get("max_temp"),
        "target_temp_step": attrs.get("target_temp_step"),
    }


@router.post("/api/climate/set")
async def set_climate(body: ClimateSetBody, request: Request):
    ha = request.app.state.ha
    if ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        if body.temperature is not None:
            await ha.call_service(
                "climate", "set_temperature",
                {"entity_id": body.entity_id, "temperature": body.temperature},
            )
        if body.hvac_mode is not None:
            await ha.call_service(
                "climate", "set_hvac_mode",
                {"entity_id": body.entity_id, "hvac_mode": body.hvac_mode},
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"climate set failed: {exc}") from exc
    return {"ok": True}


@router.get("/api/config/climate")
async def get_climate_config(request: Request):
    return {"entity": request.app.state.store.climate_entity()}


@router.put("/api/config/climate")
async def put_climate_config(body: ClimateConfigBody, request: Request):
    request.app.state.store.set_climate_entity(body.entity)
    return {"entity": request.app.state.store.climate_entity()}


# ── personality: mood + emotes ────────────────────────────────────────────────
class EmoteBody(BaseModel):
    name: str


class InteractBody(BaseModel):
    kind: str  # pet | tap | touched | spoke


_INTERACT_EVENTS = {
    "pet": "touch.pet",
    "tap": "touch.tap",
    "touched": "robot.touched",
    "spoke": "user.spoke",
}


@router.get("/api/mood")
async def get_mood(request: Request):
    return request.app.state.mood.snapshot()


@router.get("/api/emotes")
async def get_emotes(request: Request):
    return {"emotes": emote_names()}


@router.post("/api/robot/emote")
async def robot_emote(body: EmoteBody, request: Request):
    if body.name not in emote_names():
        raise HTTPException(status_code=404, detail=f"unknown emote {body.name!r}")
    await _guard(play_emote(_robot(request), body.name))
    return {"ok": True}


@router.post("/api/robot/interact")
async def robot_interact(body: InteractBody, request: Request):
    """Simulate an interaction (pet/tap/touched/spoke) — feeds the mood engine.

    Until the robot's hardware touch channel is wired, this is how you 'pet' it.
    """
    etype = _INTERACT_EVENTS.get(body.kind)
    if etype is None:
        raise HTTPException(status_code=400, detail=f"unknown kind {body.kind!r}")
    await request.app.state.bus.publish(etype, source="api")
    return {"ok": True, "event": etype}


class EventBody(BaseModel):
    type: str
    data: dict = Field(default_factory=dict)


@router.post("/api/event")
async def ingest_event(body: EventBody, request: Request):
    """Inject a bus event from an external source (robot firmware/MCP, HA webhook, ...).

    e.g. the robot's head-touch sensor can POST ``{"type":"touch.pet"}`` so the robot 'feels' it
    and the mood engine + reactions respond.
    """
    await request.app.state.bus.publish(body.type, **(body.data or {}))
    return {"ok": True, "type": body.type}


# ── schedule + timers ─────────────────────────────────────────────────────────
class ScheduleBody(BaseModel):
    schedule: list[dict]


class TimerBody(BaseModel):
    seconds: float = Field(..., gt=0, le=86400)
    label: str = ""
    say: str | None = None


@router.get("/api/schedule")
async def get_schedule(request: Request):
    return {"schedule": request.app.state.store.schedule()}


@router.put("/api/schedule")
async def put_schedule(body: ScheduleBody, request: Request):
    request.app.state.store.set_schedule(body.schedule)  # the scheduler reads these live
    return {"schedule": request.app.state.store.schedule()}


@router.post("/api/timer")
async def set_timer(body: TimerBody, request: Request):
    action = {"say": body.say} if body.say else None
    tid = await request.app.state.scheduler.set_timer(body.seconds, body.label, action)
    return {"id": tid, "seconds": body.seconds, "label": body.label}


# ── personas (switchable personalities) ───────────────────────────────────────
class PersonasBody(BaseModel):
    personas: list[dict]


class ActivePersonaBody(BaseModel):
    name: str | None = None  # None resets to the built-in default


@router.get("/api/personas")
async def get_personas(request: Request):
    s = request.app.state.store
    return {"personas": s.personas(), "active": s.active_persona()}


def _refresh_voice(request: Request) -> None:
    request.app.state.robot.default_voice = resolve_voice(request.app.state.store)


@router.put("/api/personas")
async def put_personas(body: PersonasBody, request: Request):
    request.app.state.store.set_personas(body.personas)
    _refresh_voice(request)  # a persona may carry a voice
    return {"personas": request.app.state.store.personas()}


@router.post("/api/personas/active")
async def set_active_persona(body: ActivePersonaBody, request: Request):
    request.app.state.store.set_active_persona(body.name)
    error = _rebuild_ai(request)  # apply the persona's system prompt to the AI provider
    _refresh_voice(request)  # and its voice
    return {
        "active": request.app.state.store.active_persona(),
        "ai_available": request.app.state.ai is not None,
        "error": error,
    }


# ── voice (TTS) ───────────────────────────────────────────────────────────────
class VoiceBody(BaseModel):
    voice: str | None = None  # None = use the active persona's voice / default


class VoicesBody(BaseModel):
    voices: list[str]


@router.get("/api/voice")
async def get_voice(request: Request):
    s = request.app.state
    return {
        "voice": resolve_voice(s.store),  # effective
        "override": s.store.voice(),
        "voices": s.store.voices(),
    }


@router.put("/api/voice")
async def put_voice(body: VoiceBody, request: Request):
    request.app.state.store.set_voice(body.voice)
    _refresh_voice(request)
    return {"voice": resolve_voice(request.app.state.store)}


@router.put("/api/voices")
async def put_voices(body: VoicesBody, request: Request):
    request.app.state.store.set_voices(body.voices)
    return {"voices": request.app.state.store.voices()}


# ── agenda (Home Assistant calendars) ─────────────────────────────────────────
@router.post("/api/say/agenda")
async def say_agenda(request: Request):
    s = request.app.state
    if s.ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        states = await s.ha.states()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"agenda fetch failed: {exc}") from exc
    items: list[str] = []
    for st in states:
        if not st.get("entity_id", "").startswith("calendar."):
            continue
        attrs = st.get("attributes") or {}
        msg = attrs.get("message")
        if not msg:
            continue
        start = str(attrs.get("start_time", ""))
        when = start[11:16] if len(start) >= 16 else start  # HH:MM
        items.append(f"{msg}" + (f" at {when}" if when else ""))
    text = ("On your calendar: " + "; ".join(items[:5]) + ".") if items else "Nothing on your calendar."
    await _guard(_robot(request).say(text))
    return {"text": text, "events": items}


# ── notifications inbox (HA → robot speaks) ───────────────────────────────────
class NotifyBody(BaseModel):
    text: str
    speak: bool = True  # speak now, or just queue for later


@router.post("/api/notify")
async def notify(body: NotifyBody, request: Request):
    item = request.app.state.store.add_inbox(body.text)
    if body.speak:
        robot = _robot(request)
        if robot.supports(CAP_FACE):
            try:
                await robot.set_face("happy")
            except Exception:  # noqa: BLE001
                pass
        if robot.supports(CAP_SAY):
            try:
                await robot.say(body.text)
            except Exception:  # noqa: BLE001
                pass
    return {"id": item["id"], "queued": not body.speak}


@router.get("/api/inbox")
async def get_inbox(request: Request):
    return {"messages": request.app.state.store.inbox()}


@router.post("/api/inbox/play")
async def play_inbox(request: Request):
    store = request.app.state.store
    robot = _robot(request)
    msgs = store.inbox()
    for m in msgs:
        try:
            if robot.supports(CAP_SAY):
                await robot.say(m.get("text", ""))
        except Exception:  # noqa: BLE001
            pass
    store.clear_inbox()
    return {"spoken": len(msgs)}


@router.delete("/api/inbox")
async def clear_inbox(request: Request):
    request.app.state.store.clear_inbox()
    return {"ok": True}


# ── AI party tricks (joke / fact / riddle / ...) ──────────────────────────────
@router.get("/api/ai/fun")
async def list_ai_fun():
    return {"kinds": ai_fun_kinds()}


_MOOD_LINES = {
    "excited": "I'm feeling excited!",
    "happy": "I'm feeling happy!",
    "content": "I'm doing alright.",
    "bored": "I'm a little bored, honestly.",
    "sad": "I'm feeling a bit down.",
    "sleepy": "I'm getting sleepy.",
    "down": "Eh, could be better.",
}


@router.post("/api/say/mood")
async def say_mood(request: Request):
    """The robot reports how it currently feels."""
    mood = request.app.state.mood
    label = mood.label()
    text = _MOOD_LINES.get(label, f"I'm feeling {label}.")
    robot = _robot(request)
    if robot.supports(CAP_FACE):
        try:
            await robot.set_face(mood.expression())
        except Exception:  # noqa: BLE001
            pass
    await _guard(robot.say(text))
    return {"text": text, "mood": label}


# ── backup / restore the whole config ─────────────────────────────────────────
class ImportBody(BaseModel):
    store: dict


@router.get("/api/export")
async def export_store(request: Request):
    """The full runtime config (personas, routines, memories, schedule, reactions, ...)."""
    return request.app.state.store.to_dict()


@router.post("/api/import")
async def import_store(body: ImportBody, request: Request):
    request.app.state.store.update(body.store)  # only known keys are applied
    _rebuild_ai(request)
    _refresh_voice(request)
    return {"ok": True}


@router.post("/api/ai/fun/{kind}")
async def ai_fun(kind: str, request: Request):
    prompt = AI_FUN_PROMPTS.get(kind)
    if prompt is None:
        raise HTTPException(status_code=404, detail=f"unknown kind {kind!r}")
    ai = request.app.state.ai
    if ai is None:
        raise HTTPException(status_code=503, detail="AI provider not configured")
    system = resolve_persona(request.app.state.store).system_prompt
    reply = await _guard(ai.converse(prompt, system=system))
    expression, clean = parse_expression(reply.text)
    robot = _robot(request)
    if robot.supports(CAP_FACE):
        try:
            await robot.set_face(expression)
        except Exception:  # noqa: BLE001
            pass
    if clean and robot.supports(CAP_SAY):
        try:
            await robot.say(clean)
        except Exception:  # noqa: BLE001
            pass
    return {"text": clean or reply.text, "expression": expression.value}


# ── fun / games + time + weather ──────────────────────────────────────────────
@router.get("/api/fun")
async def list_fun():
    return {"games": game_names()}


@router.post("/api/fun/{name}")
async def play_fun(name: str, request: Request):
    fn = GAMES.get(name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"unknown game {name!r}")
    result = fn()
    robot = _robot(request)
    if result.get("emote"):
        try:
            await play_emote(robot, result["emote"])
        except Exception:  # noqa: BLE001
            pass
    if result.get("text") and robot.supports(CAP_SAY):
        try:
            await robot.say(result["text"])
        except Exception:  # noqa: BLE001
            pass
    return result


@router.post("/api/say/time")
async def say_time(request: Request):
    text = "It's " + datetime.datetime.now().strftime("%H:%M") + "."
    await _guard(_robot(request).say(text))
    return {"text": text}


@router.post("/api/say/weather")
async def say_weather(request: Request):
    s = request.app.state
    entity = s.settings.weather_entity
    if not entity:
        raise HTTPException(status_code=400, detail="DRAVIX_WEATHER_ENTITY is not set")
    if s.ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        st = await s.ha.get_state(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"weather fetch failed: {exc}") from exc
    condition = st.get("state", "unknown")
    temp = (st.get("attributes") or {}).get("temperature")
    text = f"It's {condition}" + (f", {temp} degrees." if temp is not None else ".")
    await _guard(_robot(request).say(text))
    return {"text": text, "state": condition, "temperature": temp}


# ── memory (facts the robot remembers) ────────────────────────────────────────
class MemoryBody(BaseModel):
    text: str


@router.get("/api/memory")
async def get_memory(request: Request):
    return {"memories": request.app.state.store.memories()}


@router.post("/api/memory")
async def add_memory(body: MemoryBody, request: Request):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="empty memory")
    return request.app.state.store.add_memory(body.text.strip())


@router.delete("/api/memory/{mem_id}")
async def delete_memory(mem_id: str, request: Request):
    if not request.app.state.store.remove_memory(mem_id):
        raise HTTPException(status_code=404, detail=f"no memory {mem_id!r}")
    return {"ok": True}


# ── routines (named action macros) ────────────────────────────────────────────
class RoutinesBody(BaseModel):
    routines: list[dict]


@router.get("/api/routines")
async def get_routines(request: Request):
    return {"routines": request.app.state.store.routines()}


@router.put("/api/routines")
async def put_routines(body: RoutinesBody, request: Request):
    request.app.state.store.set_routines(body.routines)
    return {"routines": request.app.state.store.routines()}


@router.post("/api/routines/{name}/run")
async def run_routine_endpoint(name: str, request: Request):
    match = next((r for r in request.app.state.store.routines() if r.get("name") == name), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"unknown routine {name!r}")
    await run_routine(_robot(request), match.get("steps", []), request.app.state.engine)
    return {"ok": True, "name": name}
