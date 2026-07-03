"""Builds the dravix-os MCP server.

Exposes the robot (say / face / head / LEDs), mode control, and an optional AI chat passthrough
as MCP tools. Point any MCP client (Claude Desktop/Code, etc.) at this server to drive the
robot + your custom modes. The tools call the same ``RobotController`` + ``ModeEngine`` the
HTTP API uses, so behavior is identical across surfaces.
"""
from __future__ import annotations

import json
from typing import Any

from ..dal.base import CapabilityError, RobotController
from ..modes import ModeEngine


def build_server(
    controller: RobotController,
    engine: ModeEngine,
    ai: Any | None = None,
    ha: Any | None = None,
    store: Any | None = None,
    mood: Any | None = None,
    weather_entity: str = "",
    include_robot_control: bool = True,
    expose_risky_tools: bool | None = None,
):
    """Build the dravix MCP server.

    ``include_robot_control`` gates the robot body tools (say/face/head/leds): set it False
    when the robot driver is ``mock`` (e.g. the cloud/xiaozhi bridge) so the robot's AI isn't
    offered tools that can't actually move the hardware. The HA / weather / agenda / memory /
    fun tools below work regardless and are the useful set over the cloud.

    ``expose_risky_tools`` gates the dangerous HA tools (the generic service call, lock/
    unlock, alarm disarm) — off by default (DRAVIX_EXPOSE_RISKY_TOOLS) so a compromised /
    over-eager cloud bridge can't unlock the house. None = read the setting.
    """
    from mcp.server.fastmcp import FastMCP  # lazy import

    if expose_risky_tools is None:
        from ..config import get_settings

        expose_risky_tools = get_settings().expose_risky_tools

    mcp = FastMCP("dravix-os")

    async def _guard(coro) -> str:
        try:
            await coro
            return "ok"
        except CapabilityError as exc:
            return f"unsupported: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"error: {exc}"

    if include_robot_control:

        @mcp.tool()
        async def robot_say(text: str) -> str:
            """Make the robot speak the given text aloud."""
            return await _guard(controller.say(text))

        @mcp.tool()
        async def robot_set_face(expression: str) -> str:
            """Set the robot's facial expression: neutral|happy|sad|angry|sleepy|doubt."""
            return await _guard(controller.set_face(expression))

        @mcp.tool()
        async def robot_move_head(yaw: float, pitch: float, speed: float = 1.0) -> str:
            """Aim the robot's head. yaw and pitch are NORMALISED -1..1 (0 = look straight,
            +1 = full right / full up), speed 0..1. Values beyond 1 are treated as degrees
            (yaw -180..180, pitch -90..90) and scaled."""

            def _norm(value: float, degrees_full_scale: float) -> float:
                if abs(value) > 1.0:  # the model sent degrees — map onto the -1..1 facade
                    value = value / degrees_full_scale
                return max(-1.0, min(1.0, value))

            return await _guard(
                controller.move_head(_norm(yaw, 180.0), _norm(pitch, 90.0), speed)
            )

        @mcp.tool()
        async def robot_set_leds(color: str, brightness: float = 1.0) -> str:
            """Set the robot's LED color (name) and brightness 0..1."""
            return await _guard(controller.set_leds(color, brightness))

    @mcp.tool()
    async def list_modes() -> str:
        """List available modes and which are active (JSON)."""
        return json.dumps({"modes": engine.list_modes(), "active": engine.active})

    @mcp.tool()
    async def activate_mode(name: str) -> str:
        """Activate a mode by name (e.g. focus, pomodoro, companion, guard)."""
        try:
            await engine.activate(name)
        except KeyError as exc:
            return f"unknown mode: {exc}"
        return f"active: {engine.active}"

    @mcp.tool()
    async def deactivate_mode() -> str:
        """Deactivate the current foreground mode."""
        await engine.deactivate()
        return "ok"

    @mcp.tool()
    async def get_status() -> str:
        """Get the robot's current status + capabilities (JSON)."""
        return json.dumps(await controller.get_status())

    if ai is not None:

        @mcp.tool()
        async def chat(text: str, speak: bool = True) -> str:
            """Send a message through dravix's AI router; optionally speak the reply."""
            reply = await ai.converse(text)
            if speak and reply.text:
                try:
                    await controller.say(reply.text)
                except Exception:  # noqa: BLE001
                    pass
            return reply.text or "(no reply)"

        @mcp.tool()
        async def ai_fun(kind: str) -> str:
            """A short AI-generated bit. kind = joke | fact | riddle | compliment |
            would_you_rather | story."""
            from .. import aifun

            prompt = aifun.PROMPTS.get(kind)
            if not prompt:
                return f"unknown kind; try: {', '.join(aifun.kinds())}"
            reply = await ai.converse(prompt)
            return reply.text or "(no reply)"

    # Home Assistant tools — let the robot's voice control the smart home.
    if ha is not None and getattr(ha, "configured", False):

        @mcp.tool()
        async def home_assistant_list_entities(domain: str = "") -> str:
            """List Home Assistant entities (id, name, state) as JSON. Optionally filter by
            domain, e.g. 'light', 'switch', 'climate', 'cover', 'sensor'."""
            try:
                states = await ha.states()
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"
            out = []
            for s in states:
                eid = s.get("entity_id", "")
                if domain and not eid.startswith(f"{domain}."):
                    continue
                out.append(
                    {
                        "entity_id": eid,
                        "name": s.get("attributes", {}).get("friendly_name"),
                        "state": s.get("state"),
                    }
                )
            return json.dumps(out[:200])

        @mcp.tool()
        async def home_assistant_get_state(entity_id: str) -> str:
            """Get one Home Assistant entity's state + attributes (JSON), e.g. light.kitchen."""
            try:
                return json.dumps(await ha.get_state(entity_id))
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        # Risky: the generic service call can do ANYTHING (unlock, disarm, delete). Only
        # registered when DRAVIX_EXPOSE_RISKY_TOOLS is on — e.g. never on the cloud bridge.
        if expose_risky_tools:

            @mcp.tool()
            async def home_assistant_call_service(
                domain: str, service: str, entity_id: str = "", data_json: str = ""
            ) -> str:
                """Call a Home Assistant service to control devices. Examples:
                domain=light service=turn_on entity_id=light.kitchen;
                domain=cover service=close_cover entity_id=cover.garage.
                data_json is optional extra JSON service data (e.g. {"brightness_pct": 50})."""
                data: dict[str, Any] = {}
                if entity_id:
                    data["entity_id"] = entity_id
                if data_json:
                    try:
                        data.update(json.loads(data_json))
                    except Exception:  # noqa: BLE001 — ignore bad extra data
                        pass
                try:
                    await ha.call_service(domain, service, data)
                    return "ok"
                except Exception as exc:  # noqa: BLE001
                    return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_assist(command: str) -> str:
            """Run a NATURAL-LANGUAGE command through Home Assistant's Assist pipeline — it
            handles lights, climate, covers, timers, scenes, and any custom HA intents/scripts.
            Use this for anything not covered by the specific tools, e.g.
            'turn off all the lights downstairs', 'set a 10 minute timer', 'arm the alarm'."""
            try:
                res = await ha.conversation(command)
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"
            try:
                return res["response"]["speech"]["plain"]["speech"] or "ok"
            except Exception:  # noqa: BLE001
                return "ok"

        @mcp.tool()
        async def home_assistant_notify(message: str, title: str = "") -> str:
            """Send a notification into Home Assistant (shows in the HA UI / mobile app)."""
            data: dict[str, Any] = {"message": message}
            if title:
                data["title"] = title
            try:
                await ha.call_service("persistent_notification", "create", data)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_run_scene(scene: str) -> str:
            """Activate a Home Assistant scene, e.g. scene.movie_night."""
            try:
                await ha.call_service("scene", "turn_on", {"entity_id": scene})
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_run_script(script: str) -> str:
            """Run a Home Assistant script, e.g. script.goodnight."""
            try:
                await ha.call_service("script", "turn_on", {"entity_id": script})
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_toggle(entity_id: str) -> str:
            """Toggle any Home Assistant entity on/off, e.g. light.kitchen, switch.fan."""
            try:
                await ha.call_service("homeassistant", "toggle", {"entity_id": entity_id})
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_set_light(
            entity_id: str, brightness_pct: int = -1, color: str = ""
        ) -> str:
            """Turn on a light with optional brightness (0-100) and color name
            (e.g. 'warm white', 'red', 'blue'). entity_id like light.kitchen."""
            data: dict[str, Any] = {"entity_id": entity_id}
            if brightness_pct is not None and brightness_pct >= 0:
                data["brightness_pct"] = max(0, min(100, brightness_pct))
            if color:
                data["color_name"] = color
            try:
                await ha.call_service("light", "turn_on", data)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_set_temperature(entity_id: str, temperature: float) -> str:
            """Set a thermostat's target temperature, e.g. climate.living_room."""
            try:
                await ha.call_service(
                    "climate", "set_temperature",
                    {"entity_id": entity_id, "temperature": temperature},
                )
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        @mcp.tool()
        async def home_assistant_media(entity_id: str, action: str) -> str:
            """Control a media player. action = play | pause | stop | next | previous |
            volume_up | volume_down. entity_id like media_player.living_room."""
            svc = {
                "play": "media_play", "pause": "media_pause", "stop": "media_stop",
                "next": "media_next_track", "previous": "media_previous_track",
                "volume_up": "volume_up", "volume_down": "volume_down",
            }.get(action)
            if not svc:
                return "unknown action (use play|pause|stop|next|previous|volume_up|volume_down)"
            try:
                await ha.call_service("media_player", svc, {"entity_id": entity_id})
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        async def _svc(domain: str, service: str, entity_id: str) -> str:
            try:
                await ha.call_service(domain, service, {"entity_id": entity_id})
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        # Risky: unlocking doors from a cloud-reachable tool is opt-in only.
        if expose_risky_tools:

            @mcp.tool()
            async def home_assistant_lock(entity_id: str, action: str = "lock") -> str:
                """Lock or unlock a door. action = lock | unlock.
                entity_id like lock.front_door."""
                if action not in ("lock", "unlock"):
                    return "unknown action (use lock|unlock)"
                return await _svc("lock", action, entity_id)

        @mcp.tool()
        async def home_assistant_cover(entity_id: str, action: str) -> str:
            """Control a cover/blind/garage. action = open | close | stop.
            entity_id like cover.garage_door."""
            svc = {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"}.get(action)
            if not svc:
                return "unknown action (use open|close|stop)"
            return await _svc("cover", svc, entity_id)

        @mcp.tool()
        async def home_assistant_fan(entity_id: str, action: str) -> str:
            """Turn a fan on or off. action = on | off. entity_id like fan.bedroom."""
            svc = {"on": "turn_on", "off": "turn_off"}.get(action)
            if not svc:
                return "unknown action (use on|off)"
            return await _svc("fan", svc, entity_id)

        @mcp.tool()
        async def home_assistant_alarm(entity_id: str, action: str) -> str:
            """Arm (or, when allowed, disarm) a security alarm. action = arm_home |
            arm_away | disarm. entity_id like alarm_control_panel.home."""
            svc = {
                "arm_home": "alarm_arm_home", "arm_away": "alarm_arm_away", "disarm": "alarm_disarm",
            }.get(action)
            if not svc:
                return "unknown action (use arm_home|arm_away|disarm)"
            if action == "disarm" and not expose_risky_tools:
                # Risky: disarming from a cloud-reachable tool is opt-in only.
                return "disarm is disabled (set DRAVIX_EXPOSE_RISKY_TOOLS=true to allow it)"
            return await _svc("alarm_control_panel", svc, entity_id)

        @mcp.tool()
        async def home_assistant_vacuum(entity_id: str, action: str) -> str:
            """Control a robot vacuum. action = start | stop | return | pause.
            entity_id like vacuum.roborock."""
            svc = {
                "start": "start", "stop": "stop", "return": "return_to_base", "pause": "pause",
            }.get(action)
            if not svc:
                return "unknown action (use start|stop|return|pause)"
            return await _svc("vacuum", svc, entity_id)

        @mcp.tool()
        async def get_weather() -> str:
            """Get the current weather (from the configured Home Assistant weather entity)."""
            if not weather_entity:
                return "weather entity not configured"
            try:
                st = await ha.get_state(weather_entity)
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"
            cond = st.get("state", "unknown")
            temp = (st.get("attributes") or {}).get("temperature")
            return f"It's {cond}" + (f", {temp} degrees." if temp is not None else ".")

        @mcp.tool()
        async def get_agenda() -> str:
            """Read upcoming events from the user's Home Assistant calendars."""
            try:
                states = await ha.states()
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"
            items: list[str] = []
            for st in states:
                if not st.get("entity_id", "").startswith("calendar."):
                    continue
                attrs = st.get("attributes") or {}
                msg = attrs.get("message")
                if not msg:
                    continue
                start = str(attrs.get("start_time", ""))
                when = start[11:16] if len(start) >= 16 else start
                items.append(f"{msg}" + (f" at {when}" if when else ""))
            return ("On your calendar: " + "; ".join(items[:5]) + ".") if items else \
                "Nothing on your calendar."

    # Memory — let the robot remember + recall facts (persisted in dravix's store).
    if store is not None:

        @mcp.tool()
        async def remember_fact(text: str) -> str:
            """Remember a fact the user tells you (persisted), e.g. 'I like tea'."""
            store.add_memory(text)
            return "ok, I'll remember that"

        @mcp.tool()
        async def list_memories() -> str:
            """List the facts the robot has remembered (JSON)."""
            return json.dumps([m.get("text") for m in store.memories()])

    # Fun / party tricks — return a line for the robot's voice to say.
    from .. import fun as _fun

    @mcp.tool()
    async def roll_dice() -> str:
        """Roll a six-sided die and return the result."""
        return _fun.play_dice()["text"]

    @mcp.tool()
    async def flip_coin() -> str:
        """Flip a coin (heads or tails)."""
        return _fun.play_coin()["text"]

    @mcp.tool()
    async def magic_8ball(question: str = "") -> str:
        """Ask the magic 8-ball a yes/no question."""
        return _fun.play_eightball()["text"]

    @mcp.tool()
    async def fortune() -> str:
        """Get a short fortune / good-luck line."""
        return _fun.play_fortune()["text"]

    @mcp.tool()
    async def get_time() -> str:
        """Get the current local date and time."""
        from datetime import datetime

        return datetime.now().strftime("It's %A %H:%M, %B %d.")

    if mood is not None:

        @mcp.tool()
        async def get_mood() -> str:
            """Get the robot's current mood / how it's feeling (JSON)."""
            return json.dumps(mood.snapshot())

    return mcp
