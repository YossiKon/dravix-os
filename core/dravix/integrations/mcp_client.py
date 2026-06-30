"""A thin async wrapper over the MCP Python SDK client.

Supports both Streamable HTTP and SSE transports (the two ways an MCP server is exposed over
a URL) with ``auto`` fallback. The ``mcp`` package is imported lazily so the rest of
dravix-os runs (e.g. with the mock driver) even if ``mcp`` is not installed.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

import anyio

from ..logging import get_logger

log = get_logger("mcp.client")

# How long a single connect+initialize attempt may take before we give up (seconds).
CONNECT_TIMEOUT = 20.0


def _describe_exc(exc: BaseException | None) -> str:
    """Unwrap ExceptionGroups + cause chains into a concise, real error string.

    anyio task groups surface failures as ``unhandled errors in a TaskGroup
    (1 sub-exception)`` which hides the actual cause (e.g. a 401, a TLS error, a
    closed connection). Walk into the group/cause chain and report the leaves.
    """
    leaves: list[str] = []

    def walk(e: BaseException | None, depth: int = 0) -> None:
        if e is None or depth > 8:
            return
        subs = getattr(e, "exceptions", None)  # ExceptionGroup / BaseExceptionGroup
        if subs:
            for sub in subs:
                walk(sub, depth + 1)
            return
        leaves.append(f"{type(e).__name__}: {e}".strip())
        cause = e.__cause__ or e.__context__
        if cause is not None and cause is not e:
            walk(cause, depth + 1)

    walk(exc)
    seen: list[str] = []
    for s in leaves:
        if s and s not in seen:
            seen.append(s)
    return " | ".join(seen) if seen else f"{type(exc).__name__}: {exc}"


def _normalize_text(content: Any) -> str:
    """Flatten an MCP tool result's content list into a string."""
    parts: list[str] = []
    for item in content or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
        elif isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts)


class MCPClient:
    """Connect to one MCP server, list/call its tools, then close."""

    def __init__(self, url: str, transport: str = "auto", token: str | None = None) -> None:
        self.url = url
        self.transport = transport
        self.token = token or None
        self.active_transport: str = ""
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    @property
    def connected(self) -> bool:
        return self._session is not None

    def _headers(self) -> dict[str, str] | None:
        return {"Authorization": f"Bearer {self.token}"} if self.token else None

    def _transport_order(self) -> list[str]:
        if self.transport in ("websocket", "streamable_http", "sse"):
            return [self.transport]
        # auto: pick by URL scheme — ws(s):// is MCP-over-WebSocket (e.g. xiaozhi),
        # http(s):// is Streamable HTTP with an SSE fallback.
        if self.url.startswith(("ws://", "wss://")):
            return ["websocket"]
        return ["streamable_http", "sse"]

    async def connect(self) -> None:
        if not self.url:
            raise ValueError("MCPClient requires a non-empty url")
        from mcp import ClientSession  # lazy import

        last_err: Exception | None = None
        for transport in self._transport_order():
            stack = AsyncExitStack()
            try:
                with anyio.fail_after(CONNECT_TIMEOUT):
                    if transport == "websocket":
                        from mcp.client.websocket import websocket_client

                        # ws(s):// carries auth in the URL query (e.g. ?token=...), so no headers.
                        read, write = await stack.enter_async_context(
                            websocket_client(self.url)
                        )
                    elif transport == "streamable_http":
                        from mcp.client.streamable_http import streamablehttp_client

                        read, write, _ = await stack.enter_async_context(
                            streamablehttp_client(self.url, headers=self._headers())
                        )
                    else:
                        from mcp.client.sse import sse_client

                        read, write = await stack.enter_async_context(
                            sse_client(self.url, headers=self._headers())
                        )
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                self._stack = stack
                self._session = session
                self.active_transport = transport
                log.info("connected to %s via %s", self.url, transport)
                return
            except Exception as exc:  # noqa: BLE001 — try the next transport, but report real cause
                last_err = exc
                await stack.aclose()
                log.warning("transport %s failed for %s: %s", transport, self.url, _describe_exc(exc))
        raise ConnectionError(f"could not connect to {self.url}: {_describe_exc(last_err)}")

    async def list_tools(self) -> list[Any]:
        self._ensure()
        result = await self._session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self._ensure()
        return await self._session.call_tool(name, arguments or {})

    async def call_text(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        result = await self.call_tool(name, arguments)
        return _normalize_text(getattr(result, "content", None))

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    def _ensure(self) -> None:
        if self._session is None:
            raise RuntimeError("MCPClient is not connected; call connect() first")

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
