"""Device Abstraction Layer package — driver factory + public types."""
from __future__ import annotations

from ..config import Settings
from ..integrations.homeassistant import HomeAssistant
from .base import (
    ALL_CAPABILITIES,
    CapabilityError,
    Expression,
    RobotController,
    RobotDriver,
)

__all__ = [
    "ALL_CAPABILITIES",
    "CapabilityError",
    "Expression",
    "RobotController",
    "RobotDriver",
    "build_driver",
]


def build_driver(settings: Settings, ha: HomeAssistant | None = None) -> RobotDriver:
    """Construct the robot driver selected by configuration."""
    driver = settings.robot_driver.lower()
    if driver == "mcp":
        from .mcp_driver import MCPRobotDriver

        return MCPRobotDriver(
            url=settings.robot_mcp_url,
            transport=settings.robot_mcp_transport,
            token=settings.robot_mcp_token,
        )
    if driver == "ha":
        from .ha_driver import HARobotDriver

        if ha is None:
            raise ValueError("ha driver requires a configured HomeAssistant client")
        return HARobotDriver(ha=ha)
    if driver == "mock":
        from .mock_driver import MockDriver

        return MockDriver()
    raise ValueError(f"unknown DRAVIX_ROBOT_DRIVER: {settings.robot_driver!r}")
