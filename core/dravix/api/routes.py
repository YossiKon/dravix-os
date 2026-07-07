"""REST API consumed by the dashboard (and usable directly with curl)."""
from __future__ import annotations

import asyncio
import ipaddress
import re
from urllib.parse import urlparse

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


class AccessoryBody(BaseModel):
    option: str  # None | Glasses | Sunglasses | Top hat | Cap | Crown | Bow tie | Headphones | Halo | Monocle | Flower


class AgentStatusBody(BaseModel):
    # working | waiting_permission | question | done | error | idle
    state: str
    text: str = ""          # optional line to show/speak instead of the state's default
    say: bool | None = None  # override whether the robot speaks (default depends on state)
    source: str = ""        # the agent's name (e.g. "claude-code" or a project) — the registry key


class AgentPrefsBody(BaseModel):
    display: str | None = None   # bubble | badge | both | off
    primary: str | None = None   # pin an agent name (always wins), or "" for auto (most urgent)
    muted: list[str] | None = None  # agent names whose speech is silenced (still shown)
    approvals: bool | None = None   # master on/off for on-robot tool approvals (default off)


class AgentPermissionBody(BaseModel):
    source: str = ""             # the agent asking
    tool: str = ""               # what it wants to do (e.g. "Bash")
    summary: str = ""            # human line shown on the robot (e.g. the command)


class AgentDecideBody(BaseModel):
    decision: str                # approve | reject


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
    data["vitals"] = request.app.state.vitals.snapshot()
    data["idle_motion"] = getattr(request.app.state.robot, "idle_motion", True)
    xz = getattr(request.app.state, "xiaozhi", None)
    data["xiaozhi"] = {
        "configured": xz is not None,
        "connected": bool(xz and xz.connected),
        "last_error": (xz.last_error if xz else ""),
        "tools": (xz.tools if xz else []),
    }
    agent = getattr(request.app.state, "agent", None)
    if agent is not None:
        data["agent"] = agent.snapshot()
    personality = getattr(request.app.state, "personality", None)
    if personality is not None:
        data["personality"] = personality.snapshot()
    return data


@router.get("/api/personality")
async def get_personality(request: Request):
    """The robot's slowly-evolving temperament (see personality.py)."""
    personality = getattr(request.app.state, "personality", None)
    if personality is None:
        raise HTTPException(status_code=503, detail="personality not available")
    return personality.snapshot()


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


_ROBOT_MODES = {"awake", "morning", "focus", "quiet", "night", "busy", "sleep"}


async def _mode_options(drv) -> list[str] | None:
    """The mode select's REAL options when the driver can report them (HA), else None."""
    getter = getattr(drv, "mode_options", None)
    if getter is None:
        return None
    try:
        return await getter()
    except Exception:  # noqa: BLE001 — unknown, fall back to the static set
        return None


@router.post("/api/robot/mode")
async def set_robot_mode(body: ModeBody, request: Request):
    """Put the robot to sleep / wake it via its HA ``mode_select`` entity."""
    mode = body.mode.strip().lower()
    drv = request.app.state.robot.driver
    # Validate against what the firmware ACTUALLY accepts (the select's options attribute)
    # when readable; the static set is only the fallback for backends that can't report it.
    options = await _mode_options(drv)
    if options is not None:
        if mode not in options:
            raise HTTPException(
                status_code=400,
                detail=f"unknown mode {body.mode!r} — available: {', '.join(options)}",
            )
    elif mode not in _ROBOT_MODES:
        raise HTTPException(status_code=400, detail=f"unknown mode {body.mode!r}")
    setter = getattr(drv, "set_mode", None)
    if setter is None:
        raise HTTPException(status_code=409, detail="active backend has no mode control")
    try:
        await setter(mode)
    except NotImplementedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        options = await _mode_options(drv)
        if options:
            raise HTTPException(
                status_code=400,
                detail=f"mode {mode!r} was rejected — available: {', '.join(options)}",
            ) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "mode": mode}


# The face cosmetics the firmware's "Face accessory" select offers (default None).
_ACCESSORIES = [
    "None", "Glasses", "Sunglasses", "Top hat", "Cap", "Crown",
    "Bow tie", "Headphones", "Halo", "Monocle", "Flower",
]


@router.get("/api/robot/accessory")
async def get_robot_accessory(request: Request):
    """The cosmetic shown now + the full list the dashboard picker renders."""
    drv = request.app.state.robot.driver
    getter = getattr(drv, "accessory_current", None)
    try:
        cur = await getter() if getter else None
    except Exception:  # noqa: BLE001 — best-effort highlight
        cur = None
    return {"current": cur, "options": _ACCESSORIES}


@router.post("/api/robot/accessory")
async def set_robot_accessory(body: AccessoryBody, request: Request):
    """Put a cosmetic on the robot's face (or 'None' to clear it) from the dashboard."""
    if body.option not in _ACCESSORIES:
        raise HTTPException(status_code=400, detail=f"unknown accessory {body.option!r}")
    drv = request.app.state.robot.driver
    setter = getattr(drv, "set_accessory", None)
    if setter is None:
        raise HTTPException(status_code=409, detail="active backend has no accessory control")
    try:
        await setter(body.option)
    except NotImplementedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "option": body.option}


@router.put("/api/robot/idle-motion")
async def set_idle_motion(body: IdleMotionBody, request: Request):
    """Enable/disable the robot's automatic idle head movement (manual control is unaffected)."""
    request.app.state.robot.idle_motion = body.enabled
    request.app.state.store.set_idle_motion(body.enabled)
    return {"idle_motion": body.enabled}


# ── agent presence — an AI agent on your PC uses the robot as a status lamp ──────────
@router.post("/api/agent/status")
async def agent_status_set(body: AgentStatusBody, request: Request):
    """Report an AI agent's state; the robot reflects it (face + LED + optional speech).

    States: working | waiting_permission | question | done | error | idle. See
    docs/agent-bridge.md for wiring Claude Code (or any agent) to this endpoint.
    """
    from ..agent_status import STATES

    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    state = body.state.strip().lower()
    if state not in STATES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown state {body.state!r} — use one of: {', '.join(STATES)}",
        )
    snap = await agent.set(state, body.text, say=body.say, source=body.source)
    return {"ok": True, **snap}


@router.get("/api/agent/status")
async def agent_status_get(request: Request):
    """Every reporting agent + the current winner + display prefs (for the dashboard)."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    return agent.snapshot()


@router.delete("/api/agent/status/{name}")
async def agent_status_forget(name: str, request: Request):
    """Dismiss one agent from the board (and clear the robot if it was the winner)."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    await agent.forget(name)
    return agent.snapshot()


@router.post("/api/agent/status/clear")
async def agent_status_clear(request: Request):
    """Drop every agent and reset the robot to idle."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    return await agent.clear()


@router.put("/api/agent/prefs")
async def agent_prefs_set(body: AgentPrefsBody, request: Request):
    """Choose (from the dashboard) how agents show on the robot + who wins."""
    store = request.app.state.store
    display = body.display
    if display is not None and display not in ("bubble", "badge", "both", "off"):
        raise HTTPException(status_code=400, detail="display must be bubble|badge|both|off")
    store.set_agent_prefs(
        display=display, primary=body.primary, muted=body.muted, approvals=body.approvals
    )
    agent = getattr(request.app.state, "agent", None)
    return agent.snapshot() if agent is not None else {"ok": True}


# ── on-robot permission approvals — an agent asks, you tap Approve/Reject on the robot ──
@router.post("/api/agent/permission")
async def agent_permission_request(body: AgentPermissionBody, request: Request):
    """An agent asks for a yes/no; the robot shows Approve/Reject (and so does the dashboard).

    Returns the request (with its ``id``); the agent then polls GET
    /api/agent/permission/{id} until ``decision`` is ``approved`` or ``rejected``."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    return await agent.request_permission(body.source, tool=body.tool, summary=body.summary)


@router.get("/api/agent/permission")
async def agent_permission_current(request: Request):
    """The permission request currently awaiting a decision (or null)."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    return {"permission": agent.current_permission()}


@router.get("/api/agent/permission/{pid}")
async def agent_permission_poll(pid: str, request: Request):
    """Poll one request's decision: pending | approved | rejected | expired."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    view = agent.permission_view(pid)
    if view is None:
        raise HTTPException(status_code=404, detail="no such permission request")
    return view


@router.post("/api/agent/permission/{pid}/decide")
async def agent_permission_decide(pid: str, body: AgentDecideBody, request: Request):
    """Approve/reject a request from the dashboard (the robot's buttons do the same)."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="agent presence not available")
    view = await agent.decide_permission(pid, body.decision)
    if view is None:
        raise HTTPException(status_code=404, detail="no such permission request")
    return view


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
    {"key": "privacy_switch", "label": "Privacy mode (switch)", "domains": ["switch"]},
    {"key": "islocal_switch", "label": "Local-only (switch)", "domains": ["switch"]},
    {"key": "battery_sensor", "label": "Battery % (sensor)", "domains": ["sensor"]},
    {"key": "presence_sensor", "label": "Presence nearby (sensor)", "domains": ["binary_sensor"]},
    {"key": "bubble_text", "label": "Speech bubble (text)", "domains": ["text"]},
    {"key": "latest_fw_text", "label": "Latest firmware (text)", "domains": ["text"]},
    {"key": "brightness_number", "label": "Screen brightness (number)", "domains": ["number"]},
    {"key": "climate_name_text", "label": "Climate name (text)", "domains": ["text"]},
    {"key": "climate_set_text", "label": "Climate target (text)", "domains": ["text"]},
    {"key": "climate_info_text", "label": "Climate info (text)", "domains": ["text"]},
]
_ROLE_KEYS = {r["key"] for r in ROBOT_ENTITY_ROLES}


class RobotConfigBody(BaseModel):
    driver: str | None = None  # mock | ha | mcp
    entities: dict[str, str] | None = None  # {role: entity_id}
    calibration: dict | None = None  # {yaw:{center,min,max,invert}, pitch:{...}}


class ScreenBody(BaseModel):
    screensaver_min: float | None = Field(None, ge=0, le=1440)
    sleep_min: float | None = Field(None, ge=0, le=1440)
    brightness: float | None = Field(None, ge=10, le=100)  # the screen % (firmware number)


def _effective_entities(request: Request) -> dict[str, str]:
    # discovery fills everything automatically; explicit env/store values still override
    s = request.app.state
    discovered = getattr(s, "discovered_entities", None) or {}
    return {**discovered, **s.settings.ha_robot_entities, **s.store.robot_entities()}


def _robot_config_payload(request: Request) -> dict:
    s = request.app.state
    st = s.robot.state
    return {
        "driver": (s.store.robot_driver() or s.settings.robot_driver),
        "drivers": ["ha"],
        "roles": ROBOT_ENTITY_ROLES,
        "entities": _effective_entities(request),
        "calibration": s.store.head_calibration(),
        "capabilities": list(st.capabilities),
        "online": st.online,
        "last_error": getattr(st, "last_error", "") or "",
        "ha_configured": s.ha is not None,
        "robot_name": s.store.robot_name(),
    }


async def _apply_robot_config(request: Request) -> str | None:
    """Rebuild the driver from the merged config and reconnect. Returns an error string or None."""
    s = request.app.state
    try:
        # refresh the auto-discovery too — a reconnect is exactly when new entities appear
        # (first flash, device rename, robot back online)
        if s.ha is not None:
            from ..discovery import discover_robot_entities

            s.discovered_entities = await discover_robot_entities(s.ha)
        driver = build_robot_driver(
            s.settings, s.store, s.ha,
            discovered=getattr(s, "discovered_entities", None),
        )
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
            "state": stt.get("state"),
        })
    out.sort(key=lambda e: (e["domain"], e["name"].lower()))
    return {"entities": out, "ha_configured": True}


class HASwitchBody(BaseModel):
    entity_id: str
    on: bool


@router.post("/api/ha/switch")
async def ha_switch(body: HASwitchBody, request: Request):
    """Flip a Home Assistant switch — used for the robot's behaviour toggles."""
    ha = request.app.state.ha
    if ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    if not body.entity_id.startswith("switch."):
        raise HTTPException(status_code=400, detail="only switch.* entities can be flipped here")
    try:
        await ha.call_service(
            "switch", "turn_on" if body.on else "turn_off", {"entity_id": body.entity_id}
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"switch flip failed: {exc}") from exc
    return {"ok": True, "entity_id": body.entity_id, "on": body.on}


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


class PrivacyBody(BaseModel):
    private: bool


async def _camera_blocked(request: Request) -> bool:
    """True while privacy mode is on — the camera endpoints must serve nothing.

    Uses the controller's cached privacy read, the same choke point that also blocks
    take_photo() itself (security snapshots, the ritual, the stream)."""
    robot = request.app.state.robot
    checker = getattr(robot, "is_private", None)
    if checker is not None:
        return await checker()
    reader = getattr(robot.driver, "is_private", None)
    return bool(reader is not None and await reader())


@router.get("/api/robot/privacy")
async def get_privacy(request: Request):
    drv = request.app.state.robot.driver
    reader = getattr(drv, "is_private", None)
    return {
        "supported": getattr(drv, "set_privacy", None) is not None,
        "private": bool(reader is not None and await reader()),
    }


@router.put("/api/robot/privacy")
async def put_privacy(body: PrivacyBody, request: Request):
    setter = getattr(request.app.state.robot.driver, "set_privacy", None)
    if setter is None:
        raise HTTPException(status_code=409, detail="active backend has no privacy control")
    try:
        await setter(body.private)
    except NotImplementedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # drop the controller's privacy cache so the camera blocks/unblocks THIS instant, not
    # up to ~1.5s later (no window where the camera still serves after Privacy goes ON).
    invalidate = getattr(request.app.state.robot, "invalidate_privacy", None)
    if invalidate is not None:
        invalidate()
    return {"ok": True, "private": body.private}


@router.get("/api/robot/live")
async def robot_live(request: Request):
    """The robot's live state as published by the firmware: state / last heard / last reply.

    Everything is optional — roles that aren't mapped (or a backend without ``get_text``)
    simply come back as None, so the dashboard can render whatever is available.
    """
    drv = request.app.state.robot.driver
    reader = getattr(drv, "get_text", None)
    if reader is None:
        return {"supported": False, "state": None, "heard": None, "reply": None, "battery": None}
    state, heard, reply, battery = await asyncio.gather(
        reader("state_sensor"), reader("heard_sensor"), reader("reply_sensor"),
        reader("battery_sensor"),
    )
    try:
        battery = round(float(battery)) if battery not in (None, "", "unknown", "unavailable") else None
    except (TypeError, ValueError):
        battery = None
    return {"supported": True, "state": state, "heard": heard, "reply": reply, "battery": battery}


@router.get("/api/robot/screen")
async def get_screen(request: Request):
    """Read the on-device screensaver/sleep timeouts + screen brightness."""
    drv = request.app.state.robot.driver
    getter = getattr(drv, "get_number", None)
    if getter is None:
        return {"supported": False, "screensaver_min": None, "sleep_min": None, "brightness": None}
    return {
        "supported": True,
        "screensaver_min": await getter("screensaver_number"),
        "sleep_min": await getter("sleep_number"),
        "brightness": await getter("brightness_number"),
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
        if body.brightness is not None:
            await setter("brightness_number", body.brightness)
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


def _local_only(request: Request) -> bool:
    """The EFFECTIVE master isLocal flag (dashboard override, else the add-on/env default)."""
    s = request.app.state
    return s.store.local_only(s.settings.local_only)


@router.get("/api/config")
async def get_config(request: Request):
    s = request.app.state
    return {
        "store": s.store.to_dict(),
        "ai_provider": s.runtime.ai_provider,
        "ai_available": s.ai is not None,
        "providers": ["ha_assist", "claude", "openai", "ollama"],
        "local_only": _local_only(request),
        "cloud_providers": ["claude", "openai"],
    }


@router.get("/api/updates")
async def get_updates(request: Request):
    """Version report for the dashboard: add-on vs the newest release, and the firmware
    the robot runs vs the firmware this release ships. Never calls the internet while
    the master isLocal flag is on."""
    from ..updates import push_latest_fw, update_report

    s = request.app.state
    report = await update_report(s.ha, allow_network=not _local_only(request))
    # opportunistically refresh the robot's "Latest firmware" slot (FW+ badge / HA sensor)
    eid = (getattr(s, "discovered_entities", None) or {}).get("latest_fw_text")
    if eid:
        await push_latest_fw(s.ha, eid)
    return report


class LocalOnlyBody(BaseModel):
    enabled: bool  # the user's explicit choice — there is no "auto" value


@router.put("/api/config/local_only")
async def set_local_only(body: LocalOnlyBody, request: Request):
    """The MASTER isLocal flag — the USER's explicit on/off choice, nothing automatic.
    ON = everything stays inside the home network (cloud AI blocked, cloud bridge
    disconnected, non-LAN image URLs rejected, update checks stopped). OFF = everything
    behaves normally. Persisted until the user flips it again; applied immediately,
    and mirrored onto the robot's own "Local only" switch."""
    from ..localmode import apply_local_only

    return await apply_local_only(request.app.state, body.enabled)


@router.post("/api/robot/photo")
async def take_photo_ritual(request: Request):
    """📸 The photo ritual: the robot smiles, snaps a picture through its eyes, and the
    shot lands in the same browsable gallery the security mode uses."""
    from datetime import datetime

    from ..config import security_dir
    from ..dal.base import CAP_FACE, CAP_PHOTO, Expression

    robot = request.app.state.robot
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=501, detail="this robot has no camera")
    if await _camera_blocked(request):
        raise HTTPException(status_code=503, detail="privacy mode is on")
    try:
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.HAPPY)  # say cheese!
        data = await robot.take_photo()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"photo failed: {exc}") from exc
    finally:
        if robot.supports(CAP_FACE):
            try:
                await robot.set_face(Expression.NEUTRAL)
            except Exception:  # noqa: BLE001
                pass
    if not data:
        raise HTTPException(status_code=502, detail="camera returned no frame")
    now = datetime.now()
    day_dir = security_dir() / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    name = f"{now.strftime('%H%M%S')}.jpg"
    (day_dir / name).write_bytes(data)
    return {"ok": True, "day": now.strftime("%Y-%m-%d"), "name": name}


@router.post("/api/robot/photobooth")
async def photobooth(request: Request):
    """📸 A joyful photobooth: the robot counts "3… 2… 1…" out loud (with faces + LED
    pulses), flashes the LED bar like a shutter, then snaps the shot into the gallery."""
    from datetime import datetime

    from ..config import security_dir
    from ..dal.base import CAP_FACE, CAP_LEDS, CAP_PHOTO, CAP_SAY, Expression

    robot = request.app.state.robot
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=501, detail="this robot has no camera")
    if await _camera_blocked(request):
        raise HTTPException(status_code=503, detail="privacy mode is on")

    from ..config import get_settings

    he = (get_settings().language or "en").startswith("he")

    async def _try(coro):
        try:
            await coro
        except Exception:  # noqa: BLE001 — the whole ritual is best-effort theatre
            pass

    # 3 … 2 … 1 — a face + a spoken number + an amber pulse per beat
    faces = [Expression.HAPPY, Expression.DOUBT, Expression.HAPPY]
    for i, n in enumerate((3, 2, 1)):
        if robot.supports(CAP_FACE):
            await _try(robot.set_face(faces[i]))
        if robot.supports(CAP_LEDS):
            await _try(robot.set_leds("#E69F00", 0.9))
        if robot.supports(CAP_SAY):
            await _try(robot.say(str(n)))
        await asyncio.sleep(0.9)
    if robot.supports(CAP_SAY):
        await _try(robot.say("חייכו!" if he else "Say cheese!"))
    if robot.supports(CAP_LEDS):
        await _try(robot.set_leds("#FFFFFF", 1.0))  # shutter flash
    if robot.supports(CAP_FACE):
        await _try(robot.set_face(Expression.HAPPY))

    try:
        data = await robot.take_photo()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"photo failed: {exc}") from exc
    finally:
        if robot.supports(CAP_LEDS):
            await _try(robot.set_leds("off", 0.0))
        if robot.supports(CAP_FACE):
            await _try(robot.set_face(Expression.NEUTRAL))
    if not data:
        raise HTTPException(status_code=502, detail="camera returned no frame")
    now = datetime.now()
    day_dir = security_dir() / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    name = f"{now.strftime('%H%M%S')}.jpg"
    (day_dir / name).write_bytes(data)
    return {"ok": True, "day": now.strftime("%Y-%m-%d"), "name": name}


# event-class → LED colour (Okabe–Ito, colour-blind-safe) for physical notifications
_NOTIFY_COLORS = {
    "calendar": "#E69F00",   # amber
    "message": "#56B4E9",    # blue
    "doorbell": "#009E73",   # green
    "delivery": "#009E73",   # green
    "alert": "#D55E00",      # vermillion
    "info": "#2EE6C8",       # teal
}


class RobotNotifyBody(BaseModel):
    kind: str = "info"    # calendar | message | doorbell | delivery | alert | info
    text: str = ""        # optional line to speak
    say: bool = True


async def _robot_state_text(request: Request) -> str:
    getter = getattr(request.app.state.robot.driver, "get_text", None)
    if getter is None:
        return ""
    try:
        return (await getter("state_sensor")) or ""
    except Exception:  # noqa: BLE001
        return ""


@router.post("/api/robot/notify")
async def robot_notify(body: RobotNotifyBody, request: Request):
    """📢 A physical, glanceable notification: the robot faces you + nods, pulses the LED in
    an event-class colour, and (optionally) speaks the text. Meant to be called from Home
    Assistant automations via a rest_command (doorbell, calendar, a message…). All
    best-effort + capability-guarded; movement is auto-dropped while the robot sleeps, and
    speech is skipped while it's asleep. See docs/home-assistant.md."""
    from ..dal.base import ASLEEP_STATES, CAP_HEAD, CAP_LEDS, CAP_SAY

    robot = request.app.state.robot
    color = _NOTIFY_COLORS.get(body.kind.strip().lower(), _NOTIFY_COLORS["info"])

    async def _try(coro):
        try:
            await coro
        except Exception:  # noqa: BLE001 — a notification must never raise
            pass

    if robot.supports(CAP_LEDS):
        await _try(robot.set_leds(color, 1.0))
    if robot.supports(CAP_HEAD):  # a little "hey, look at me" nod (dropped while asleep)
        await _try(robot.move_head(0.0, -0.15, speed=0.6))
        await asyncio.sleep(0.25)
        await _try(robot.move_head(0.0, 0.1, speed=0.6))
        await asyncio.sleep(0.2)
        await _try(robot.move_head(0.0, 0.0, speed=0.6))
    spoken = False
    if body.say and body.text and robot.supports(CAP_SAY):
        if (await _robot_state_text(request)).strip().lower() not in ASLEEP_STATES:
            await _try(robot.say(body.text))
            spoken = True
    return {"ok": True, "kind": body.kind, "color": color, "spoken": spoken}


class VolumeBody(BaseModel):
    volume: int = Field(ge=0, le=100)


@router.get("/api/robot/volume")
async def get_volume(request: Request):
    """The robot speaker's current volume (0-100), from the media_player entity."""
    s = request.app.state
    eid = _effective_entities(request).get("media_player")
    if not eid or s.ha is None:
        return {"supported": False, "volume": None}
    try:
        st = await s.ha.get_state(eid)
        level = (st.get("attributes") or {}).get("volume_level")
        return {"supported": True, "volume": round(float(level) * 100) if level is not None else None}
    except Exception:  # noqa: BLE001
        return {"supported": True, "volume": None}


@router.put("/api/robot/volume")
async def set_volume(body: VolumeBody, request: Request):
    """Set the robot speaker's volume (0-100)."""
    s = request.app.state
    eid = _effective_entities(request).get("media_player")
    if not eid or s.ha is None:
        raise HTTPException(status_code=503, detail="no media player discovered")
    try:
        await s.ha.call_service(
            "media_player", "volume_set",
            {"entity_id": eid, "volume_level": body.volume / 100.0},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"volume set failed: {exc}") from exc
    return {"ok": True, "volume": body.volume}


class LedsEffectBody(BaseModel):
    effect: str  # one of the light bar's effect names, or "None" to stop


@router.post("/api/robot/leds/effect")
async def robot_leds_effect(body: LedsEffectBody, request: Request):
    """Run one of the LED bar's built-in animated effects (BSP: Random / Rainbow /
    Twinkle) — or "None" to stop. Uses the auto-discovered light entity."""
    s = request.app.state
    if s.ha is None:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    eid = _effective_entities(request).get("led_light")
    if not eid:
        raise HTTPException(status_code=404, detail="no LED light discovered")
    data: dict = {"entity_id": eid, "effect": body.effect}
    if body.effect != "None":
        data["brightness_pct"] = 70
    try:
        await s.ha.call_service("light", "turn_on", data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"effect failed: {exc}") from exc
    return {"ok": True, "effect": body.effect}


# ── security mode — browse / manage the saved captures ────────────────────────
_SEC_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEC_FILE_RE = re.compile(r"^\d{6}\.jpg$")          # snapshots: HHMMSS.jpg
_SEC_VIDEO_RE = re.compile(r"^vid_\d{6}\.mp4$")     # recorded clips: vid_HHMMSS.mp4


def _sec_ts(day: str, name: str) -> str:
    """ISO timestamp from a day folder + HHMMSS(.jpg)/vid_HHMMSS(.mp4) name."""
    hms = name[4:10] if name.startswith("vid_") else name[0:6]
    return f"{day}T{hms[0:2]}:{hms[2:4]}:{hms[4:6]}"


def _sec_recording(request: Request) -> bool:
    """True while security mode is armed AND set to record continuous video."""
    engine = _engine(request)
    return engine.is_active("security") and bool(
        engine.effective_config("security").get("record_video")
    )


def _sec_day_dir(day: str):
    """Validated day directory (or a 400)."""
    from ..config import security_dir

    if not _SEC_DAY_RE.match(day):
        raise HTTPException(status_code=400, detail="bad day")
    return security_dir() / day


def _sec_prune_empty(day_dir) -> None:
    """Drop a day folder once it holds no photos AND no recorded clips (also clears a
    lingering timelapse)."""
    try:
        keep = any(
            _SEC_FILE_RE.match(f.name) or _SEC_VIDEO_RE.match(f.name)
            for f in day_dir.iterdir()
        )
        if not keep:
            (day_dir / "timelapse.mp4").unlink(missing_ok=True)
            (day_dir / "_frames.txt").unlink(missing_ok=True)
            day_dir.rmdir()
    except OSError:
        pass


@router.get("/api/security/days")
async def security_days(request: Request):
    """A per-day summary of the saved captures (newest first) for the gallery."""
    from ..config import security_dir

    root = security_dir()
    days: list[dict] = []
    if root.exists():
        for d in sorted((x for x in root.iterdir() if x.is_dir() and _SEC_DAY_RE.match(x.name)), reverse=True):
            files = [f for f in d.iterdir() if _SEC_FILE_RE.match(f.name)]
            clips = [f for f in d.iterdir() if _SEC_VIDEO_RE.match(f.name)]
            if not files and not clips:
                continue
            days.append({
                "day": d.name,
                "count": len(files),
                "videos": len(clips),
                "bytes": sum(f.stat().st_size for f in files) + sum(f.stat().st_size for f in clips),
                "has_video": (d / "timelapse.mp4").is_file(),
            })
    return {
        "armed": _engine(request).is_active("security"),
        "recording": _sec_recording(request),
        "days": days,
    }


@router.get("/api/security/photos")
async def security_photos(request: Request, limit: int = 24, day: str = ""):
    """Saved snapshots (newest first) with timestamps; ``day`` filters to one day."""
    from ..config import security_dir

    root = security_dir()
    if day:
        if not _SEC_DAY_RE.match(day):
            raise HTTPException(status_code=400, detail="bad day")
        day_dirs = [root / day] if (root / day).is_dir() else []
    else:
        day_dirs = (
            sorted((d for d in root.iterdir() if d.is_dir() and _SEC_DAY_RE.match(d.name)), reverse=True)
            if root.exists() else []
        )
    cap = max(1, min(2000, limit))
    photos: list[dict] = []
    total = 0
    for d in day_dirs:
        files = sorted((f for f in d.iterdir() if _SEC_FILE_RE.match(f.name)), reverse=True)
        total += len(files)
        for f in files:
            if len(photos) < cap:
                photos.append({
                    "day": d.name, "name": f.name,
                    "size": f.stat().st_size, "ts": _sec_ts(d.name, f.name),
                })
    return {
        "armed": _engine(request).is_active("security"),
        "recording": _sec_recording(request),
        "total": total,
        "photos": photos,
    }


@router.get("/api/security/photo/{day}/{name}")
async def security_photo(day: str, name: str, download: int = 0):
    """Serve one saved snapshot. Path parts are strictly validated — no traversal."""
    if not _SEC_DAY_RE.match(day) or not _SEC_FILE_RE.match(name):
        raise HTTPException(status_code=400, detail="bad photo path")
    path = _sec_day_dir(day) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such photo")
    headers = (
        {"Content-Disposition": f'attachment; filename="dravix-{day}-{name}"'} if download else None
    )
    return Response(content=path.read_bytes(), media_type="image/jpeg", headers=headers)


@router.delete("/api/security/photo/{day}/{name}")
async def security_delete_photo(day: str, name: str):
    """Delete a single snapshot."""
    if not _SEC_DAY_RE.match(day) or not _SEC_FILE_RE.match(name):
        raise HTTPException(status_code=400, detail="bad photo path")
    day_dir = _sec_day_dir(day)
    path = day_dir / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such photo")
    path.unlink()
    _sec_prune_empty(day_dir)
    return {"ok": True}


@router.delete("/api/security/day/{day}")
async def security_delete_day(day: str):
    """Delete a whole day's captures (photos + any built video)."""
    day_dir = _sec_day_dir(day)
    if not day_dir.is_dir():
        raise HTTPException(status_code=404, detail="no such day")
    n = 0
    for f in list(day_dir.iterdir()):
        try:
            f.unlink()
            n += 1 if _SEC_FILE_RE.match(f.name) else 0
        except OSError:
            pass
    try:
        day_dir.rmdir()
    except OSError:
        pass
    return {"ok": True, "deleted": n}


@router.delete("/api/security/photos")
async def security_delete_all():
    """Clear ALL saved captures."""
    from ..config import security_dir

    root = security_dir()
    n = 0
    if root.exists():
        for d in list(root.iterdir()):
            if not (d.is_dir() and _SEC_DAY_RE.match(d.name)):
                continue
            for f in list(d.iterdir()):
                try:
                    f.unlink()
                    n += 1 if _SEC_FILE_RE.match(f.name) else 0
                except OSError:
                    pass
            try:
                d.rmdir()
            except OSError:
                pass
    return {"ok": True, "deleted": n}


@router.get("/api/security/day/{day}/zip")
async def security_day_zip(day: str):
    """Download a whole day's photos as a single zip."""
    import io
    import zipfile

    day_dir = _sec_day_dir(day)
    if not day_dir.is_dir():
        raise HTTPException(status_code=404, detail="no such day")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # JPEGs are already compressed
        for f in sorted(day_dir.iterdir()):
            if _SEC_FILE_RE.match(f.name):
                z.write(f, arcname=f"{day}/{f.name}")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="dravix-security-{day}.zip"'},
    )


@router.post("/api/security/day/{day}/video")
async def security_day_video(day: str, fps: int = 8):
    """Build a timelapse MP4 from a day's snapshots (needs ffmpeg in the image)."""
    import shutil

    day_dir = _sec_day_dir(day)
    if not day_dir.is_dir():
        raise HTTPException(status_code=404, detail="no such day")
    if shutil.which("ffmpeg") is None:
        raise HTTPException(status_code=501, detail="ffmpeg is not available in this image")
    frames = sorted(f for f in day_dir.iterdir() if _SEC_FILE_RE.match(f.name))
    if not frames:
        raise HTTPException(status_code=404, detail="no photos to build a video from")
    per = 1.0 / max(1, min(30, fps))
    listf = day_dir / "_frames.txt"
    listf.write_text(
        "".join(f"file '{f.name}'\nduration {per:.4f}\n" for f in frames) + f"file '{frames[-1].name}'\n",
        encoding="utf-8",
    )
    out = day_dir / "timelapse.mp4"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
        "-vf", "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        cwd=str(day_dir),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    listf.unlink(missing_ok=True)
    if proc.returncode != 0 or not out.is_file():
        raise HTTPException(status_code=502, detail=f"video build failed: {err.decode('utf-8', 'replace')[-160:]}")
    return {"ok": True, "day": day, "bytes": out.stat().st_size}


@router.get("/api/security/day/{day}/video")
async def security_get_video(day: str, download: int = 0):
    """Serve a previously built day timelapse MP4."""
    path = _sec_day_dir(day) / "timelapse.mp4"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no video built for this day yet")
    headers = (
        {"Content-Disposition": f'attachment; filename="dravix-security-{day}.mp4"'} if download else None
    )
    return Response(content=path.read_bytes(), media_type="video/mp4", headers=headers)


# ── recorded video clips (security mode records the camera stream while armed) ──
@router.get("/api/security/videos")
async def security_videos(request: Request, limit: int = 200, day: str = ""):
    """The recorded MP4 clips (newest first), with timestamps; ``day`` filters to one day."""
    from ..config import security_dir

    root = security_dir()
    if day:
        if not _SEC_DAY_RE.match(day):
            raise HTTPException(status_code=400, detail="bad day")
        day_dirs = [root / day] if (root / day).is_dir() else []
    else:
        day_dirs = (
            sorted((d for d in root.iterdir() if d.is_dir() and _SEC_DAY_RE.match(d.name)), reverse=True)
            if root.exists() else []
        )
    cap = max(1, min(1000, limit))
    clips: list[dict] = []
    total = 0
    for d in day_dirs:
        files = sorted((f for f in d.iterdir() if _SEC_VIDEO_RE.match(f.name)), reverse=True)
        total += len(files)
        for f in files:
            if len(clips) < cap:
                clips.append({
                    "day": d.name, "name": f.name,
                    "size": f.stat().st_size, "ts": _sec_ts(d.name, f.name),
                })
    return {"total": total, "clips": clips}


@router.get("/api/security/video/{day}/{name}")
async def security_get_clip(day: str, name: str, download: int = 0):
    """Serve one recorded MP4 clip."""
    if not _SEC_DAY_RE.match(day) or not _SEC_VIDEO_RE.match(name):
        raise HTTPException(status_code=400, detail="bad clip path")
    path = _sec_day_dir(day) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such clip")
    headers = (
        {"Content-Disposition": f'attachment; filename="dravix-{day}-{name}"'} if download else None
    )
    return Response(content=path.read_bytes(), media_type="video/mp4", headers=headers)


@router.delete("/api/security/video/{day}/{name}")
async def security_delete_clip(day: str, name: str):
    """Delete one recorded clip."""
    if not _SEC_DAY_RE.match(day) or not _SEC_VIDEO_RE.match(name):
        raise HTTPException(status_code=400, detail="bad clip path")
    day_dir = _sec_day_dir(day)
    path = day_dir / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such clip")
    path.unlink()
    _sec_prune_empty(day_dir)
    return {"ok": True}


class LanguageBody(BaseModel):
    language: str = "en"  # en | he (any code the tips tables know)


@router.put("/api/config/language")
async def set_language(body: LanguageBody, request: Request):
    """Persist the UI language server-side too, so server-generated content (wellness
    tips, greetings) speaks the same language as the dashboard."""
    lang = body.language.strip().lower()[:8]
    request.app.state.store.set_language(lang or None)
    return {"language": lang}


class BirthdayBody(BaseModel):
    date: str = ""  # "MM-DD" ("" clears it)


@router.put("/api/config/birthday")
async def set_birthday(body: BirthdayBody, request: Request):
    """Set the user's birthday (MM-DD). Once a year, on the first scheduler tick after
    09:00, the robot celebrates — love face, party lights and a spoken greeting."""
    date = body.date.strip()
    if date and not re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", date):
        raise HTTPException(status_code=400, detail="birthday must be MM-DD")
    request.app.state.store.set_birthday(date)
    return {"birthday": date}


class TipsBody(BaseModel):
    tips: list[str] = Field(default_factory=list)  # [] = back to the built-in tips


@router.put("/api/vitals/tips")
async def set_wellness_tips(body: TipsBody, request: Request):
    """Replace the built-in wellness tips with your own lines ([] restores the defaults)."""
    if any(not isinstance(t, str) or len(t) > 120 for t in body.tips):
        raise HTTPException(status_code=400, detail="tips must be strings up to 120 chars")
    request.app.state.store.set_wellness_tips(body.tips)
    return {"tips": request.app.state.store.wellness_tips()}


class RobotNameBody(BaseModel):
    name: str = ""


@router.put("/api/config/robot_name")
async def set_robot_name(body: RobotNameBody, request: Request):
    """Name the robot. Shows in the dashboard header and is fed to the AI persona
    ("your name is …"), so it answers to the name. Empty = default branding."""
    name = body.name.strip()
    if len(name) > 40:
        raise HTTPException(status_code=400, detail="name too long (max 40 chars)")
    request.app.state.store.set_robot_name(name)
    return {"robot_name": name}


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


# SSRF guards: a Frigate camera is a bare name; a HA camera is camera.<object_id>. Anything
# else (path tricks, spaces, schemes) is rejected before it reaches a URL or the HA proxy.
_CAMERA_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CAMERA_ENTITY_RE = re.compile(r"^camera\.[A-Za-z0-9_]+$")
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # cap server-side fetches of user-supplied URLs


def _is_local_host(host: str) -> bool:
    """True for LAN-ish hosts: private/loopback IPs, .local/.lan names, bare hostnames."""
    if not host:
        return False
    h = host.lower().strip("[]")  # tolerate bracketed IPv6
    if h == "localhost" or h.endswith(".local") or h.endswith(".lan") or "." not in h:
        return True
    try:
        return ipaddress.ip_address(h).is_private or ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False  # a public DNS name


async def _fetch_image(url: str) -> bytes:
    """Fetch a user-supplied image URL with a short timeout + a hard size cap."""
    buf = bytearray()
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as c:
        try:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > _MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=400, detail="image too large (max 5 MB)")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from exc
    return bytes(buf)


@router.post("/api/robot/show_image")
async def robot_show_image(body: ShowImageBody, request: Request):
    """Display an image URL on the robot's screen.

    Preferred path: the robot downloads the URL itself (the firmware's Show-image slot).
    Fallback: fetch here (size-capped) and push the bytes (MCP driver)."""
    # Empty is allowed only for the firmware slot (it means "back to the face").
    if body.url and urlparse(body.url).scheme.lower() not in ("http", "https"):
        raise HTTPException(status_code=400, detail="url must be http(s)")
    # Master isLocal flag: only LAN image sources while it's on.
    if body.url and _local_only(request) and not _is_local_host(urlparse(body.url).hostname or ""):
        raise HTTPException(
            status_code=400,
            detail="isLocal mode is on — only local (LAN) image URLs are allowed",
        )
    shower = getattr(request.app.state.robot.driver, "show_image_url", None)
    if shower is not None:
        try:
            await shower(body.url)
            return {"ok": True, "mode": "url"}
        except NotImplementedError:
            pass  # role not mapped — fall through to the bytes path
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    img = await _fetch_image(body.url)
    await _guard(_robot(request).show_image(img))
    return {"ok": True, "bytes": len(img)}


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
    if not (_CAMERA_NAME_RE.fullmatch(camera) or _CAMERA_ENTITY_RE.fullmatch(camera)):
        raise HTTPException(
            status_code=400,
            detail="invalid camera — use a Frigate camera name or a camera.* entity id",
        )
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
# Both endpoints go dark while the robot's Privacy-mode switch is ON.
@router.get("/camera/robot/snapshot.jpg", include_in_schema=False)
async def robot_camera_snapshot(request: Request):
    robot = _robot(request)
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=503, detail="robot has no camera capability")
    if await _camera_blocked(request):
        raise HTTPException(status_code=503, detail="privacy mode is on")
    img = await _guard(robot.take_photo())
    if not img:
        raise HTTPException(status_code=503, detail="no frame from robot camera")
    return Response(content=img, media_type="image/jpeg")


@router.get("/camera/robot/stream.mjpeg", include_in_schema=False)
async def robot_camera_stream(request: Request, fps: float = 2.0):
    robot = _robot(request)
    if not robot.supports(CAP_PHOTO):
        raise HTTPException(status_code=503, detail="robot has no camera capability")
    if await _camera_blocked(request):
        raise HTTPException(status_code=503, detail="privacy mode is on")
    delay = 1.0 / max(0.2, min(fps, 10.0))

    async def frames():
        misses = 0
        try:
            while True:
                if await request.is_disconnected():
                    break  # client (browser / ffmpeg) went away — stop doing take_photo work
                if await _camera_blocked(request):
                    break  # privacy flipped on mid-stream → end the stream immediately
                try:
                    img = await robot.take_photo()
                except Exception:  # noqa: BLE001
                    img = None
                if img:
                    misses = 0
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(img)).encode()
                        + b"\r\n\r\n"
                        + img
                        + b"\r\n"
                    )
                else:
                    misses += 1
                    if misses >= 30:  # camera down for ~a while → end the stream, don't spin
                        break
                await asyncio.sleep(delay)
        except asyncio.CancelledError:  # client disconnect surfaces here — exit quietly
            return

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


@router.get("/api/vitals")
async def get_vitals(request: Request):
    """The robot's live needs (energy/food/fun/calm, 0-100) + whether nudges are on."""
    return request.app.state.vitals.snapshot()


class VitalsActionBody(BaseModel):
    action: str  # feed | rest | play | calm


@router.post("/api/vitals/action")
async def vitals_action(body: VitalsActionBody, request: Request):
    """Satisfy a need — feed / rest / play / calm. User-initiated: always runs + shows feedback."""
    action = body.action.strip().lower()
    if action not in {"feed", "rest", "play", "calm"}:
        raise HTTPException(status_code=400, detail=f"unknown action {body.action!r}")
    return await request.app.state.vitals.satisfy(action)


class NudgesBody(BaseModel):
    enabled: bool


@router.put("/api/vitals/nudges")
async def set_nudges(body: NudgesBody, request: Request):
    """Turn the wellness nudges (rest/hydrate/eye-break tips) on or off."""
    request.app.state.store.set_nudges_enabled(body.enabled)
    return {"nudges": body.enabled}


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


@router.get("/api/timers")
async def list_timers(request: Request):
    """The running one-shot timers (for the dashboard's timers card)."""
    return {"timers": request.app.state.scheduler.list_timers()}


@router.delete("/api/timers/{timer_id}")
async def cancel_timer(timer_id: str, request: Request):
    if not request.app.state.scheduler.cancel_timer(timer_id):
        raise HTTPException(status_code=404, detail="no such timer")
    return {"ok": True}


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
    bad = request.app.state.store.validate_patch(body.store)
    if bad:
        raise HTTPException(status_code=400, detail="invalid keys: " + ", ".join(bad))
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
