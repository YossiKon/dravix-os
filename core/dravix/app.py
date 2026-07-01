"""FastAPI application factory + lifespan wiring.

Builds and connects all the pieces (config → event bus → HA client → robot driver/controller
→ AI provider → mode engine) and exposes them on ``app.state`` for the API layer.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .ai import build_provider
from .config import DATA_DIR, PLUGINS_DIR, WEB_DIST_DIR, WEB_STATIC_DIR, Settings, get_settings
from .dal import RobotController, build_driver
from .events import EventBus
from .integrations.frigate import Frigate
from .integrations.ha_events import HAEventBridge, ha_ws_url
from .integrations.homeassistant import HomeAssistant
from .integrations.xiaozhi_bridge import XiaoZhiBridge
from .logging import get_logger, setup_logging
from .modes import ModeContext, ModeEngine
from .mood import MoodEngine
from .persona import resolve_voice
from .reactions import ReactionEngine
from .scheduler import Scheduler
from .state import RuntimeState
from .store import Store

log = get_logger("app")


def build_ai(settings: Settings, store: Store, ha: HomeAssistant | None):
    """Build the AI provider, honoring store overrides (provider + active persona) over env."""
    from .persona import resolve_persona

    provider = store.ai_provider() or settings.ai_provider
    merged = settings.model_copy(update={"ai_provider": provider})
    return build_provider(merged, ha, system=resolve_persona(store).system_prompt)


def build_robot_driver(settings: Settings, store: Store, ha: HomeAssistant | None):
    """Build the robot driver, letting dashboard picks (driver type + HA entities + head
    calibration, saved in the store) override the add-on/env defaults."""
    driver_name = (store.robot_driver() or settings.robot_driver).lower()
    if driver_name == "ha":
        from .dal.ha_driver import HARobotDriver

        if ha is None:
            raise ValueError("the 'ha' driver needs Home Assistant — set ha_url + ha_token")
        entities = {**settings.ha_robot_entities, **store.robot_entities()}
        entities = {k: v for k, v in entities.items() if v}
        return HARobotDriver(ha=ha, entities=entities, calibration=store.head_calibration())
    merged = settings.model_copy(update={"robot_driver": driver_name})
    return build_driver(merged, ha)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("starting dravix-os %s", __version__)

    bus = EventBus()
    data_dir = Path(settings.data_dir) if settings.data_dir else DATA_DIR
    store = Store(data_dir / "store.json")
    runtime = RuntimeState(ai_provider=store.ai_provider() or settings.ai_provider)

    # Home Assistant client (optional — only if configured).
    ha: HomeAssistant | None = None
    if settings.ha_url and settings.ha_token:
        ha = HomeAssistant(settings.ha_url, settings.ha_token)
    frigate = Frigate(ha, settings.frigate_url)

    # Robot driver + controller (dashboard picks in the store win over env defaults).
    driver = build_robot_driver(settings, store, ha)
    controller = RobotController(driver, bus, runtime.robot)
    controller.default_voice = resolve_voice(store)  # active persona/override TTS voice
    controller.idle_motion = settings.idle_motion  # ambient head-glance toggle (add-on option)
    try:
        await controller.connect()
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, surface in status
        runtime.robot.online = False
        runtime.robot.last_error = str(exc)
        log.error("robot connect failed (%s): %s", settings.robot_driver, exc)

    # AI provider (optional — honors the store override, else the env default).
    ai = None
    try:
        ai = build_ai(settings, store, ha)
    except Exception as exc:  # noqa: BLE001
        log.warning("AI provider unavailable: %s", exc)

    # Mode engine.
    engine = ModeEngine(
        PLUGINS_DIR,
        ModeContext(robot=controller, bus=bus, ai=ai, ha=ha),
        store=store,
    )
    engine.discover()
    await engine.start()

    # User-configurable event→action rules (persisted in the store).
    reactions = ReactionEngine(controller, bus, frigate=frigate, engine=engine, store=store)
    await reactions.start()

    # Personality: persistent mood that drifts + shows on the face when idle.
    mood = MoodEngine(bus, controller, store=store, engine=engine)
    await mood.start()

    # Scheduler: daily jobs (good-morning, reminders) + one-shot timers.
    scheduler = Scheduler(bus, controller, store=store, engine=engine)
    await scheduler.start()

    # Home Assistant event bridge (motion/presence/door -> bus -> modes like guard).
    ha_bridge: HAEventBridge | None = None
    if ha is not None and settings.ha_events_enabled:
        ha_bridge = HAEventBridge(
            ha_ws_url(settings.ha_url), settings.ha_token, bus, settings.ha_event_map
        )
        ha_bridge.start()

    # xiaozhi bridge: expose dravix's MCP tools to the robot's AI (the robot can control
    # HA / run dravix features by voice). dravix is the MCP *server* on this connection.
    xiaozhi: XiaoZhiBridge | None = None
    if settings.xiaozhi_mcp_url:
        from .mcpserver.server import build_server

        # The robot body tools only work with a real driver; over the cloud the driver is
        # mock, so omit them and serve the useful set (HA / weather / agenda / memory / fun).
        _include_robot = settings.robot_driver != "mock"
        xiaozhi = XiaoZhiBridge(
            settings.xiaozhi_mcp_url,
            lambda: build_server(
                controller, engine, ai, ha=ha, store=store, mood=mood,
                weather_entity=settings.weather_entity,
                include_robot_control=_include_robot,
            ),
        )
        await xiaozhi.start()

    app.state.settings = settings
    app.state.bus = bus
    app.state.store = store
    app.state.runtime = runtime
    app.state.ha = ha
    app.state.robot = controller
    app.state.ai = ai
    app.state.engine = engine
    app.state.ha_bridge = ha_bridge
    app.state.frigate = frigate
    app.state.reactions = reactions
    app.state.mood = mood
    app.state.scheduler = scheduler
    app.state.xiaozhi = xiaozhi

    try:
        yield
    finally:
        log.info("shutting down dravix-os")
        if xiaozhi is not None:
            await xiaozhi.stop()
        if ha_bridge is not None:
            await ha_bridge.stop()
        await scheduler.stop()
        await mood.stop()
        await reactions.stop()
        await engine.stop()
        try:
            await controller.close()
        except Exception:  # noqa: BLE001
            pass
        if ha is not None:
            await ha.close()


def create_app() -> FastAPI:
    app = FastAPI(title="dravix-os", version=__version__, lifespan=lifespan)

    from .api.routes import router  # imported here to avoid a circular import

    app.include_router(router)

    # Serve the dashboard. The API/WS routes are registered first, so they take priority;
    # this SPA mount catches everything else. Prefer the React build, fall back to the
    # built-in vanilla page.
    spa_dir = WEB_DIST_DIR if WEB_DIST_DIR.exists() else WEB_STATIC_DIR
    if spa_dir.exists():
        app.mount("/", StaticFiles(directory=str(spa_dir), html=True), name="spa")

    return app
