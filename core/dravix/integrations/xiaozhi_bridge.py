"""Bridge dravix's MCP server to a xiaozhi MCP接入点 (access point).

The xiaozhi MCP endpoint (``wss://api.xiaozhi.me/mcp/?token=...``) is *reverse*: it
expects the connecting side to be an MCP **server** that provides tools to the robot's
AI (the robot/cloud is the MCP *client* — it sends ``initialize``). So dravix opens an
outbound WebSocket and runs its MCP server over it; the robot's voice can then call
dravix + Home Assistant tools ("turn on the kitchen light", "what's on my calendar").

Runs as a background task with reconnect + backoff, managed by the app lifespan. This is
the opposite direction from the ``mcp`` robot *driver* (which would call the robot's tools);
controlling the robot itself needs a different channel (a local xiaozhi server).
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..logging import get_logger
from .mcp_client import _describe_exc

log = get_logger("xiaozhi.bridge")


class XiaoZhiBridge:
    """Serve dravix's MCP tools to a xiaozhi access point over an outbound WebSocket."""

    def __init__(self, url: str, server_factory: Callable[[], Any]) -> None:
        self.url = url
        self._server_factory = server_factory
        self._task: asyncio.Task | None = None
        self.connected = False
        self.last_error = ""

    async def _serve_once(self) -> None:
        from mcp.client.websocket import websocket_client  # lazy import

        server = self._server_factory()
        low = server._mcp_server  # FastMCP -> underlying low-level Server
        # websocket_client opens the *client* socket; we drive it with the *server*
        # protocol so xiaozhi (the MCP client) can list + call our tools.
        async with websocket_client(self.url) as (read, write):
            self.connected = True
            self.last_error = ""
            log.info("xiaozhi bridge connected — serving dravix tools to the robot")
            await low.run(read, write, low.create_initialization_options())

    async def _loop(self) -> None:
        backoff = 2.0
        while True:
            try:
                await self._serve_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep retrying, surface the cause
                self.last_error = _describe_exc(exc)
                log.warning("xiaozhi bridge dropped: %s (retry in %.0fs)", self.last_error, backoff)
            else:
                log.info("xiaozhi bridge connection closed (retry in %.0fs)", backoff)
            finally:
                self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    async def start(self) -> None:
        if self.url and self._task is None:
            self._task = asyncio.create_task(self._loop())
            log.info("xiaozhi bridge starting -> %s", self.url)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except BaseException:  # noqa: BLE001 — best-effort shutdown
                pass
            self._task = None
            self.connected = False
