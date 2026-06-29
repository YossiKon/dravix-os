"""REST API consumed by the dashboard (and usable directly with curl)."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import datetime

from .. import __version__
from ..app import build_ai
from ..dal.base import CAP_FACE, CAP_PHOTO, CAP_SAY, CapabilityError
from ..emotes import emote_names, play_emote
from ..fun import GAMES, game_names
from ..persona import parse_expression

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────
class SayBody(BaseModel):
    text: str
    voice: str | None = None


class FaceBody(BaseModel):
    expression: str


class HeadBody(BaseModel):
    yaw: float = Field(..., ge=-180, le=180)
    pitch: float = Field(..., ge=-90, le=90)
    speed: float = Field(1.0, ge=0.0, le=1.0)


class LedsBody(BaseModel):
    color: str
    brightness: float = Field(1.0, ge=0.0, le=1.0)


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


@router.post("/api/ai/chat")
async def ai_chat(body: ChatBody, request: Request):
    ai = request.app.state.ai
    if ai is None:
        raise HTTPException(status_code=503, detail="AI provider not configured")
    reply = await _guard(ai.converse(body.text, conversation_id=body.conversation_id))
    # Pull a leading emotion tag (e.g. "(happy)") out of the reply to drive the face.
    expression, clean = parse_expression(reply.text)
    if body.speak:
        robot = _robot(request)
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
    """Fetch an image URL and display it on the robot's screen."""
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
    """Pull a Frigate camera snapshot (locally) and display it on the robot's screen."""
    s = request.app.state
    camera = body.camera or s.settings.frigate_camera
    if not camera:
        raise HTTPException(status_code=400, detail="no camera given and DRAVIX_FRIGATE_CAMERA is empty")
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
    return {"ok": True, "camera": camera, "bytes": len(img)}


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


@router.put("/api/personas")
async def put_personas(body: PersonasBody, request: Request):
    request.app.state.store.set_personas(body.personas)
    return {"personas": request.app.state.store.personas()}


@router.post("/api/personas/active")
async def set_active_persona(body: ActivePersonaBody, request: Request):
    request.app.state.store.set_active_persona(body.name)
    error = _rebuild_ai(request)  # apply the persona's system prompt to the AI provider
    return {
        "active": request.app.state.store.active_persona(),
        "ai_available": request.app.state.ai is not None,
        "error": error,
    }


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
