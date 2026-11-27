"""Dravix add-on: one page in Home Assistant's sidebar for the Dravix robot.

It finds the robot by itself (the ESPHome device with the "Mode" select whose options are
Normal / Busy / Sleep), lets you pick its tiles and air conditioner from lists, switch its mode
and private mode, start games and faces, and install the voice-command and photo automations.
Everything goes through Home Assistant's own API with the Supervisor's token; the robot itself
needs nothing from this add-on to work.
"""
import asyncio
import copy
import json
import logging
import os
import time
from pathlib import Path

import aiohttp
import yaml
from aiohttp import web

HERE = Path(__file__).parent
STATIC = HERE / "static"
TEMPLATES = HERE / "templates"
VERSION = os.environ.get("DRAVIX_VERSION", "dev")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA = os.environ.get("DRAVIX_HA_URL", "http://supervisor/core").rstrip("/")
DEMO = os.environ.get("DRAVIX_DEMO") == "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dravix")

# the robot's entities, by their ESPHome names (these never change; the entity ids may)
NAMES = {
    "Mode": "mode", "Private mode": "private", "Face": "face", "Screen": "screen",
    "Microphone mute": "mic_mute", "Wake sound": "wake_sound", "Follow me": "follow",
    "Desk guard": "guard", "Battery": "battery", "Charging": "charging", "State": "state",
    "Last heard": "heard", "Last reply": "reply", "Last voice problem": "voice_problem",
    "Firmware": "firmware", "ESPHome version": "esphome", "Camera": "camera",
    "Air conditioner": "ac", "Screen brightness": "brightness", "LED brightness": "led_brightness",
    "Touchscreen": "touchscreen", "Loop time": "loop_time",
    "Sleep at": "sleep_at", "Wake up at": "wake_at", "Sleep on schedule": "sleep_sched",
    "Sleep when the room is dark": "sleep_dark",
    **{f"Tile {i}": f"tile{i}" for i in range(1, 9)},
}
TILE_DOMAINS = ("light", "switch", "fan", "cover", "scene", "script", "button", "input_boolean",
                "input_button", "lock", "media_player", "sensor", "binary_sensor", "climate")
GAMES = ("rps", "coin", "dice", "8ball", "reaction", "bang", "chameleon", "photo", "mirror", "guard", "follow", "games")
FACES = ("happy", "sad", "love", "done", "greet", "surprised", "angry", "doubt", "dizzy", "error")
AUTOMATIONS = {"voice": ("dravix_voice", "voice.yaml"), "photos": ("dravix_photos", "photos.yaml")}


class HAError(Exception):
    pass


def friendly(err) -> str:
    """Home Assistant's errors, in words a person can act on."""
    text = str(err)
    if "Not connected to" in text:
        return "The robot isn't connected to Home Assistant right now. Is it on, and on Wi-Fi?"
    if "not found" in text.lower() and "esphome" in text:
        return ("Home Assistant doesn't know the robot's actions yet: ESPHome → the robot → Configure → "
                "allow the device to perform Home Assistant actions.")
    return text


class Robot:
    """What we know about the robot; rediscovered at most once a minute."""

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.entities: dict[str, str] = {}
        self.node = ""            # the ESPHome node name in its actions: esphome.<node>_play_game
        self.name = ""
        self.found_at = 0.0
        self.problem = ""

    @property
    def headers(self):
        return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    async def api(self, method: str, path: str, body=None):
        async with self.session.request(method, f"{HA}{path}", headers=self.headers,
                                        data=None if body is None else json.dumps(body),
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
            text = await r.text()
            if r.status >= 400:
                raise HAError(f"{method} {path}: HTTP {r.status} {text[:200]}")
            return json.loads(text) if text else None

    async def registry(self):
        """The entity registry (it ties entities to devices), over the websocket API."""
        url = HA.replace("http", "ws", 1) + "/websocket"
        async with self.session.ws_connect(url, timeout=15) as ws:
            await ws.receive_json()                                  # auth_required
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise HAError("websocket: authentication failed")
            await ws.send_json({"id": 1, "type": "config/entity_registry/list"})
            while True:
                msg = await ws.receive_json()
                if msg.get("id") == 1:
                    if not msg.get("success"):
                        raise HAError(f"entity registry: {msg.get('error')}")
                    return msg["result"]

    async def discover(self, force=False):
        if not force and self.entities and time.time() - self.found_at < 60:
            return
        states = {s["entity_id"]: s for s in await self.api("GET", "/api/states")}
        entities, name = {}, ""
        try:
            reg = await self.registry()
            device = None
            for e in reg:
                st = states.get(e["entity_id"])
                if (e.get("original_name") == "Mode" and e["entity_id"].startswith("select.") and st
                        and st["attributes"].get("options") == ["Normal", "Busy", "Sleep"]):
                    device = e.get("device_id")
                    name = st["attributes"].get("friendly_name", "Dravix")[: -len(" Mode")] or "Dravix"
                    break
            if device:
                for e in reg:
                    key = NAMES.get(e.get("original_name") or "")
                    if e.get("device_id") == device and key:
                        entities[key] = e["entity_id"]
        except Exception as err:                                     # no registry: match the names instead
            log.warning("entity registry unavailable (%s); matching friendly names", err)
        if not entities:
            for st in states.values():
                if st["entity_id"].startswith("select.") and st["attributes"].get("options") == ["Normal", "Busy", "Sleep"]:
                    fn = st["attributes"].get("friendly_name", "")
                    prefix = fn[: -len("Mode")] if fn.endswith("Mode") else ""
                    name = prefix.strip() or "Dravix"
                    for s2 in states.values():
                        f2 = s2["attributes"].get("friendly_name", "")
                        if prefix and f2.startswith(prefix) and f2[len(prefix):] in NAMES:
                            entities[NAMES[f2[len(prefix):]]] = s2["entity_id"]
                    break
        services = await self.api("GET", "/api/services")
        node = ""
        for dom in services:
            if dom.get("domain") == "esphome":
                for svc in dom.get("services", {}):
                    if svc.endswith("_play_game"):
                        node = svc[: -len("_play_game")]
        self.entities, self.node, self.name = entities, node, name or "Dravix"
        self.found_at = time.time()
        self.problem = "" if entities else "No Dravix robot found in Home Assistant yet."
        log.info("robot: %s, %d entities, node %s", self.name, len(entities), node or "?")

    async def call(self, domain: str, service: str, data: dict):
        return await self.api("POST", f"/api/services/{domain}/{service}", data)


robot = Robot()


# ── demo data, for working on the page without a Home Assistant (DRAVIX_DEMO=1) ─────────────────
def demo_robot():
    return {
        "found": True, "name": "Dravix", "version": VERSION, "node": "stackchan", "problem": "",
        "online": True,
        "state": {"mode": "Normal", "private": "off", "face": "neutral", "screen": "Face", "mic_mute": "off",
                  "wake_sound": "on", "follow": "off", "guard": "off", "battery": "87", "charging": "on",
                  "state": "awake", "heard": "turn on the desk lamp", "reply": "Turned on the light",
                  "voice_problem": "", "firmware": "2.0.0", "esphome": "2026.11.1", "touchscreen": "OK",
                  "loop_time": "16", "sleep_at": "23:00:00", "wake_at": "07:00:00", "sleep_sched": "on"},
        "tiles": [{"slot": i, "entity_id": e, "name": n, "state": s} for i, (e, n, s) in enumerate([
            ("light.desk_lamp", "Desk lamp", "on"), ("light.ceiling", "Ceiling light", "off"),
            ("switch.coffee_machine", "Coffee machine", "off"), ("scene.movie_time", "Movie time", "scening"),
            ("fan.office", "Office fan", "off"), ("", "", ""), ("", "", ""), ("", "", "")], start=1)],
        "ac": {"entity_id": "climate.living_room", "name": "Living room AC", "state": "cool"},
        "automations": {"voice": False, "photos": True},
    }


DEMO_ENTITIES = [{"entity_id": e, "name": n, "domain": e.split(".")[0], "state": s} for e, n, s in [
    ("light.desk_lamp", "Desk lamp", "on"), ("light.ceiling", "Ceiling light", "off"), ("fan.office", "Office fan", "off"),
    ("switch.coffee_machine", "Coffee machine", "off"), ("scene.movie_time", "Movie time", "scening"),
    ("script.good_night", "Good night", "off"), ("climate.living_room", "Living room AC", "cool"),
    ("climate.bedroom", "Bedroom AC", "off"), ("cover.blinds", "Blinds", "open"), ("lock.front_door", "Front door", "locked")]]


# ── the page's API ──────────────────────────────────────────────────────────────────────────────
async def api_robot(request):
    if DEMO:
        return web.json_response(demo_robot())
    try:
        await robot.discover()
        states = {s["entity_id"]: s for s in await robot.api("GET", "/api/states")}
    except Exception as err:
        return web.json_response({"found": False, "version": VERSION, "problem": f"Home Assistant: {err}"})
    e = robot.entities
    st = {k: states.get(eid, {}).get("state", "") for k, eid in e.items()}
    online = st.get("mode", "unavailable") not in ("unavailable", "unknown", "")

    def label(eid):
        s = states.get(eid)
        return (s["attributes"].get("friendly_name") or eid) if s else eid

    tiles = []
    for i in range(1, 9):
        target = st.get(f"tile{i}", "") or ""
        target = "" if target in ("unknown", "unavailable") else target
        tiles.append({"slot": i, "entity_id": target, "name": label(target) if target else "",
                      "state": states.get(target, {}).get("state", "") if target else ""})
    ac = st.get("ac", "") or ""
    ac = "" if ac in ("unknown", "unavailable") else ac
    autos = {}
    for kind, (aid, _) in AUTOMATIONS.items():
        try:
            await robot.api("GET", f"/api/config/automation/config/{aid}")
            autos[kind] = True
        except Exception:
            autos[kind] = False
    return web.json_response({
        "found": bool(e), "name": robot.name, "version": VERSION, "node": robot.node, "problem": robot.problem,
        "online": online, "state": st, "tiles": tiles,
        "ac": {"entity_id": ac, "name": label(ac) if ac else "", "state": states.get(ac, {}).get("state", "") if ac else ""},
        "automations": autos,
    })


async def api_entities(request):
    if DEMO:
        return web.json_response(DEMO_ENTITIES)
    try:
        states = await robot.api("GET", "/api/states")
    except Exception as err:
        raise web.HTTPBadGateway(text=str(err))
    out = [{"entity_id": s["entity_id"], "name": s["attributes"].get("friendly_name") or s["entity_id"],
            "domain": s["entity_id"].split(".")[0], "state": s["state"]}
           for s in states if s["entity_id"].split(".")[0] in TILE_DOMAINS]
    out.sort(key=lambda x: (x["domain"], x["name"].lower()))
    return web.json_response(out)


async def api_do(request):
    body = await request.json()
    what = body.get("what")
    if DEMO:
        log.info("demo: %s", body)
        return web.json_response({"ok": True})
    try:
        await robot.discover()
        e = robot.entities
        if what in ("tile", "ac"):
            key = f"tile{int(body['slot'])}" if what == "tile" else "ac"
            value = (body.get("entity_id") or "").strip()
            if value and "." not in value:
                raise HAError("not an entity id")
            await robot.call("text", "set_value", {"entity_id": e[key], "value": value})
        elif what == "mode":
            if body.get("mode") not in ("Normal", "Busy", "Sleep"):
                raise HAError("unknown mode")
            await robot.call("select", "select_option", {"entity_id": e["mode"], "option": body["mode"]})
        elif what == "private":
            await robot.call("switch", "turn_on" if body.get("on") else "turn_off", {"entity_id": e["private"]})
        elif what == "game":
            if body.get("game") not in GAMES or not robot.node:
                raise HAError("unknown game, or the robot's actions are not allowed yet")
            await robot.call("esphome", f"{robot.node}_play_game", {"game": body["game"]})
        elif what == "face":
            if body.get("face") not in FACES or not robot.node:
                raise HAError("unknown face, or the robot's actions are not allowed yet")
            await robot.call("esphome", f"{robot.node}_show_face", {"face": body["face"]})
        elif what == "schedule":
            for key in ("sleep_at", "wake_at"):
                value = (body.get(key) or "").strip()
                if value:
                    if len(value) == 5:
                        value += ":00"
                    await robot.call("time", "set_value", {"entity_id": e[key], "time": value})
        elif what in ("switch_on", "switch_off"):
            key = body.get("key")
            if key not in ("mic_mute", "wake_sound", "follow", "guard", "sleep_sched", "sleep_dark"):
                raise HAError("unknown switch")
            await robot.call("switch", "turn_on" if what == "switch_on" else "turn_off", {"entity_id": e[key]})
        else:
            raise HAError("unknown action")
    except KeyError as err:
        return web.json_response({"ok": False, "error": f"the robot has no {err} entity (update its firmware?)"}, status=400)
    except Exception as err:
        return web.json_response({"ok": False, "error": friendly(err)}, status=400)
    return web.json_response({"ok": True})


def automation_body(kind: str) -> tuple[str, dict]:
    aid, file = AUTOMATIONS[kind]
    data = yaml.safe_load((TEMPLATES / file).read_text(encoding="utf-8"))
    text = json.dumps(data, ensure_ascii=False)
    if robot.node:
        text = text.replace("esphome.stackchan_", f"esphome.{robot.node}_")
    cam = robot.entities.get("camera")
    if cam:
        text = text.replace("camera.stackchan_camera", cam)
    body = json.loads(text)
    body["id"] = aid
    return aid, body


async def api_automation(request):
    kind = request.match_info["kind"]
    if kind not in AUTOMATIONS:
        raise web.HTTPNotFound()
    if DEMO:
        return web.json_response({"ok": True})
    try:
        await robot.discover(force=True)
        aid, body = automation_body(kind)
        await robot.api("POST", f"/api/config/automation/config/{aid}", body)
    except Exception as err:
        aid, body = AUTOMATIONS[kind][0], {}
        try:
            body = automation_body(kind)[1]
        except Exception:
            pass
        return web.json_response({"ok": False, "error": str(err), "yaml": yaml.safe_dump(body, allow_unicode=True, sort_keys=False)}, status=400)
    return web.json_response({"ok": True})


async def index(request):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


async def on_startup(app):
    robot.session = aiohttp.ClientSession()
    if not DEMO and not TOKEN:
        log.warning("no SUPERVISOR_TOKEN: is homeassistant_api enabled for the add-on?")


async def on_cleanup(app):
    if robot.session:
        await robot.session.close()


def make_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/robot", api_robot)
    app.router.add_get("/api/entities", api_entities)
    app.router.add_post("/api/do", api_do)
    app.router.add_post("/api/automation/{kind}", api_automation)
    app.router.add_static("/static/", STATIC)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    log.info("Dravix add-on %s%s", VERSION, " (demo)" if DEMO else "")
    web.run_app(make_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8800")), print=None)
