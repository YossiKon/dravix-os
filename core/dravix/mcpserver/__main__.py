"""Run the dravix-os MCP server over stdio: ``python -m dravix.mcpserver``.

Wire this into an MCP client (e.g. Claude Desktop/Code) as a stdio server. It builds the same
robot controller + mode engine the HTTP service uses, then serves the tools from
``server.build_server`` over stdio.

All logging goes to stderr (stdout is the MCP protocol channel), so it is safe.
"""
from __future__ import annotations

import asyncio

from ..ai import build_provider
from ..config import PLUGINS_DIR, get_settings
from ..dal import RobotController, build_driver
from ..events import EventBus
from ..integrations.homeassistant import HomeAssistant
from ..logging import get_logger, setup_logging
from ..modes import ModeContext, ModeEngine
from ..state import RobotState
from .server import build_server

log = get_logger("mcpserver")


async def _amain() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    ha = None
    if settings.ha_url and settings.ha_token:
        ha = HomeAssistant(settings.ha_url, settings.ha_token)

    bus = EventBus()
    driver = build_driver(settings, ha)
    controller = RobotController(driver, bus, RobotState())
    try:
        await controller.connect()
    except Exception as exc:  # noqa: BLE001
        log.error("robot connect failed: %s", exc)

    ai = None
    try:
        ai = build_provider(settings, ha)
    except Exception as exc:  # noqa: BLE001
        log.warning("AI provider unavailable: %s", exc)

    engine = ModeEngine(PLUGINS_DIR, ModeContext(robot=controller, bus=bus, ai=ai, ha=ha))
    engine.discover()
    await engine.start()

    server = build_server(controller, engine, ai)
    log.info("dravix-os MCP server ready (stdio)")
    try:
        await server.run_stdio_async()
    finally:
        await engine.stop()
        try:
            await controller.close()
        except Exception:  # noqa: BLE001
            pass
        if ha is not None:
            await ha.close()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
