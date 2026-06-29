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


def build_server(controller: RobotController, engine: ModeEngine, ai: Any | None = None):
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

    return mcp
