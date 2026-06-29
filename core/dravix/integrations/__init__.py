"""External integrations: MCP client wrapper, Home Assistant client."""
from __future__ import annotations

from .homeassistant import HomeAssistant
from .mcp_client import MCPClient

__all__ = ["HomeAssistant", "MCPClient"]
