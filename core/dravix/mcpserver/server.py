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
    weather_entity: str = "",
    include_robot_control: bool = True,
):
    """Build the dravix MCP server.

    ``include_robot_control`` gates the robot body tools (say/face/head/leds): set it False
    when the robot driver is ``mock`` (e.g. the cloud/xiaozhi bridge) so the robot's AI isn't
    offered tools that can't actually move the hardware. The HA / weather / agenda / memory /
    fun tools below work regardless and are the useful set over the cloud.
    """
    from mcp.server.fastmcp import FastMCP  # lazy import

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
            """Aim the robot's head. yaw -180..180, pitch -90..90, speed 0..1."""
            return await _guard(controller.move_head(yaw, pitch, speed))

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

    return mcp
