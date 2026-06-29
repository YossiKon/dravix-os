"""dravix-os's own MCP server — exposes the robot + modes as tools for external agents."""
from __future__ import annotations

from .server import build_server

__all__ = ["build_server"]
