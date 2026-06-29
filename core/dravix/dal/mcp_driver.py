"""Robot driver that controls the StackChan via its MCP server.

The robot publishes an MCP endpoint at a URL (the same one Home Assistant connects to). We
map our DAL verbs to the robot's MCP tool names. The default map follows the common
StackChan-MCP tool names, but every mapping is overridable once ``discover.py`` tells us the
exact names this robot exposes — and unknown verbs simply report as unsupported instead of
guessing.
"""
from __future__ import annotations

from typing import Any

from ..integrations.mcp_client import MCPClient
from ..logging import get_logger
from .base import (
    CAP_DISPLAY,
    CAP_FACE,
    CAP_HEAD,
    CAP_LEDS,
    CAP_LISTEN,
    CAP_PHOTO,
    CAP_SAY,
    Expression,
    RobotDriver,
)

log = get_logger("dal.mcp")

# DAL verb -> candidate MCP tool names (first one that exists on the robot wins).
DEFAULT_TOOL_CANDIDATES: dict[str, tuple[str, ...]] = {
    CAP_FACE: ("set_avatar", "set_face", "set_expression", "face"),
    CAP_HEAD: ("move_head", "set_head", "look", "head"),
    CAP_SAY: ("say", "speak", "tts"),
    CAP_LEDS: ("set_leds", "set_led", "leds"),
    CAP_PHOTO: ("take_photo", "capture", "photo", "camera"),
    CAP_LISTEN: ("listen", "stt", "hear"),
    CAP_DISPLAY: ("show_image", "set_image", "display_image", "set_screen", "draw_image"),
}


class MCPRobotDriver(RobotDriver):
    name = "mcp"

    def __init__(
        self,
        url: str,
        transport: str = "auto",
        token: str | None = None,
        tool_overrides: dict[str, str] | None = None,
    ) -> None:
        self._client = MCPClient(url, transport=transport, token=token)
        self._overrides = tool_overrides or {}
        self._tool_for: dict[str, str] = {}
        self._available: set[str] = set()

    async def connect(self) -> None:
        await self._client.connect()
        self.transport = self._client.active_transport
        tools = await self._client.list_tools()
        names = {t.name for t in tools}
        self._available = names
        # Resolve each verb to a concrete tool name.
        for cap, candidates in DEFAULT_TOOL_CANDIDATES.items():
            chosen = self._overrides.get(cap)
            if chosen and chosen in names:
                self._tool_for[cap] = chosen
                continue
            for cand in candidates:
                if cand in names:
                    self._tool_for[cap] = cand
                    break
        log.info("robot MCP tools: %s | mapped: %s", sorted(names), self._tool_for)

    async def close(self) -> None:
        await self._client.close()

    async def capabilities(self) -> set[str]:
        return set(self._tool_for)

    async def _call(self, cap: str, **arguments: Any) -> Any:
        tool = self._tool_for.get(cap)
        if not tool:
            raise RuntimeError(f"no robot MCP tool mapped for {cap!r}")
        return await self._client.call_tool(tool, arguments)

    async def set_face(self, expression: Expression) -> None:
        await self._call(CAP_FACE, expression=expression.value)

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        await self._call(CAP_HEAD, yaw=yaw, pitch=pitch, speed=speed)

    async def say(self, text: str, voice: str | None = None) -> None:
        args: dict[str, Any] = {"text": text}
        if voice:
            args["voice"] = voice
        await self._call(CAP_SAY, **args)

    async def set_leds(self, color: str, brightness: float = 1.0) -> None:
        await self._call(CAP_LEDS, color=color, brightness=brightness)

    async def take_photo(self) -> bytes | None:
        result = await self._call(CAP_PHOTO)
        # Photo handling depends on how the robot returns image data (URL vs base64 vs
        # binary). discover.py records the real shape; we return raw for now.
        return result  # type: ignore[return-value]

    async def listen(self, timeout: float = 7.0) -> str | None:
        return await self._client.call_text(self._tool_for[CAP_LISTEN], {"timeout": timeout})

    async def show_image(self, image: bytes) -> None:
        import base64

        # Most robot MCP tools accept base64 JPEG; the exact arg name is tuned from discovery.
        await self._call(CAP_DISPLAY, image=base64.b64encode(image).decode("ascii"))

    async def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.name,
            "transport": self.transport,
            "available_tools": sorted(self._available),
            "mapped": self._tool_for,
        }

    async def raw_call(self, action: str, **kwargs: Any) -> Any:
        return await self._client.call_tool(action, kwargs)
