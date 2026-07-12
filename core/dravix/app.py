"""FastAPI application factory + lifespan wiring.

Builds and connects all the pieces (config → event bus → HA client → robot driver/controller
→ AI provider → mode engine) and exposes them on ``app.state`` for the API layer.
"""
from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
from .vitals import VitalsEngine
from .pethead import PetHeadBehavior
from .reactions import ReactionEngine
from .scheduler import Scheduler
from .screens import ScreenPusher
from .state import RuntimeState
from .store import Store

log = get_logger("app")


def build_ai(settings: Settings, store: Store, ha: HomeAssistant | None):
    """Build the AI provider, honoring store overrides (provider + active persona) over env."""
    from .persona import resolve_persona

    provider = store.ai_provider() or settings.ai_provider
    # The master isLocal flag is the user's persisted dashboard choice (the add-on option
    # only seeds the very first run) — it decides whether cloud providers are allowed.
    merged = settings.model_copy(
        update={"ai_provider": provider, "local_only": store.local_only(settings.local_only)}
    )
    return build_provider(merged, ha, system=resolve_persona(store).system_prompt)


def build_robot_driver(
    settings: Settings, store: Store, ha: HomeAssistant | None,
    discovered: dict[str, str] | None = None,
):
    """Build the robot driver. Entity roles are AUTO-DISCOVERED from HA (``discovered``,
    see discovery.py) — explicit add-on/env options and anything saved in the store still
    override, but a fresh install needs zero manual mapping."""
    driver_name = (store.robot_driver() or settings.robot_driver).lower()
    if driver_name == "ha":
        from .dal.ha_driver import HARobotDriver

        if ha is None:
            raise ValueError("the 'ha' driver needs Home Assistant — set ha_url + ha_token")
        entities = {**(discovered or {}), **settings.ha_robot_entities, **store.robot_entities()}
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

    # AUTO-DISCOVER the robot's entities (suffix-anchored, prefix-agnostic) — the user
    # never hand-maps entities; explicit env/store values still override the discovery.
    discovered: dict[str, str] = {}
    if ha is not None:
        from .discovery import discover_robot_entities

        discovered = await discover_robot_entities(ha)

    # Robot driver + controller (dashboard picks in the store win over env defaults).
    # A driver that can't even be *built* (bad config, missing HA, ...) must not stop the
    # dashboard from booting — fall back to the mock driver and surface the error in /api/status.
    driver_error = ""
    try:
        driver = build_robot_driver(settings, store, ha, discovered=discovered)
    except Exception as exc:  # noqa: BLE001 — degrade to mock, surface in status
        from .dal.mock_driver import MockDriver

        driver_error = str(exc)
        log.error("robot driver build failed: %s — falling back to the mock driver", exc)
        driver = MockDriver()
    controller = RobotController(driver, bus, runtime.robot)
    controller.default_voice = resolve_voice(store)  # active persona/override TTS voice
    # The dashboard toggle (persisted in the store) wins; the add-on/env value is the default
    # only until the user flips it. (Previously this always used the env default, so a restart
    # silently re-enabled idle motion — the head then moved even in sleep/focus.)
    controller.idle_motion = store.idle_motion(settings.idle_motion)
    try:
        await controller.connect()
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, surface in status
        runtime.robot.online = False
        runtime.robot.last_error = str(exc)
        log.error("robot connect failed (%s): %s", settings.robot_driver, exc)
    if driver_error:
        runtime.robot.last_error = driver_error  # the build failure is the root cause

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

    # Vitals: the Tamagotchi "life" needs (energy/food/fun/calm) + wellness nudges. Silent in
    # calm modes (focus/quiet/night/busy/sleep) — the HARD do-not-disturb rule.
    vitals = VitalsEngine(
        bus, controller, store=store, engine=engine, ha=ha,
        # lazy — evaluated at nudge time, when app.state.discovered_entities exists
        discovered=lambda: getattr(app.state, "discovered_entities", {}) or {},
    )
    await vitals.start()

    # Pet reaction: lift the head up when petted (pleased), lower it after a hold.
    pet_head = PetHeadBehavior(
        bus, controller, hold_s=settings.pet_head_hold_s, raise_pitch=settings.pet_head_raise
    )
    if settings.pet_head_raise:
        await pet_head.start()

    # Scheduler: daily jobs (good-morning, reminders) + one-shot timers.
    scheduler = Scheduler(bus, controller, store=store, engine=engine)
    await scheduler.start()

    # Screens: push chosen HA entities onto the robot's 3 display cards (needs HA to read states).
    screen_pusher = ScreenPusher(ha, store)
    if ha is not None:
        await screen_pusher.start()

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
    # The cloud bridge respects the master isLocal flag (the dashboard can flip it at
    # runtime — /api/config/local_only stops/starts the bridge accordingly).
    if settings.xiaozhi_mcp_url and not store.local_only(settings.local_only):
        from .mcpserver.server import build_server

        # The robot body tools only work with a real driver; over the cloud the driver is
        # mock, so omit them and serve the useful set (HA / weather / agenda / memory / fun).
        # Use the store-merged driver — same pick build_robot_driver made above.
        _include_robot = (store.robot_driver() or settings.robot_driver).lower() != "mock"
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
    app.state.discovered_entities = discovered
    app.state.runtime = runtime
    app.state.ha = ha
    app.state.robot = controller
    app.state.ai = ai
    app.state.engine = engine
    app.state.ha_bridge = ha_bridge
    app.state.frigate = frigate
    app.state.reactions = reactions
    app.state.mood = mood
    app.state.vitals = vitals
    app.state.pet_head = pet_head
    app.state.scheduler = scheduler
    app.state.screen_pusher = screen_pusher
    app.state.xiaozhi = xiaozhi
    from .agent_status import AgentPresence

    app.state.agent = AgentPresence(controller, bus, store)
    await app.state.agent.start()  # staleness sweeper — releases the robot from dead agents
    from .personality import Personality

    app.state.personality = Personality(store)

    # ── isLocal ⇄ the robot's own "Local only" switch ─────────────────────────────
    # The choice can be made ON the robot (the LOCAL button on its status bar). The HA
    # event bridge republishes that switch's transitions as `islocal.set`; this watcher
    # applies them (without echoing back to the robot). And at startup dravix pushes the
    # persisted choice TO the robot, so the LOCAL button always shows the truth.
    islocal_eid = discovered.get("islocal_switch")
    if ha is not None and islocal_eid:
        try:
            await ha.call_service(
                "switch",
                "turn_on" if store.local_only(settings.local_only) else "turn_off",
                {"entity_id": islocal_eid},
            )
        except Exception:  # noqa: BLE001 — robot may be offline; the sync is best-effort
            pass

    async def _islocal_watcher() -> None:
        from .localmode import apply_local_only

        q = bus.subscribe()
        try:
            while True:
                ev = await q.get()
                # a tap on one of the robot's entity-card rows → perform the action
                if ev.type == "card.tap":
                    try:
                        await screen_pusher.handle_tap(
                            int(ev.data.get("card") or 0), int(ev.data.get("row") or 0)
                        )
                    except Exception:  # noqa: BLE001 — never kill the watcher
                        log.exception("card tap handling failed")
                    continue
                # a tap on the robot's CLIMATE page → control the configured AC
                if ev.type == "climate.control":
                    try:
                        from .climate_bridge import handle_control

                        await handle_control(ha, store.climate_entity(), str(ev.data.get("action") or ""))
                    except Exception:  # noqa: BLE001 — never kill the watcher
                        log.exception("climate control failed")
                    continue
                # a tap on the robot's Approve/Reject buttons → resolve the pending permission
                if ev.type == "agent.permission_decision":
                    try:
                        await app.state.agent.decide_current(str(ev.data.get("decision") or ""))
                    except Exception:  # noqa: BLE001 — never kill the watcher
                        log.exception("agent permission decision failed")
                    continue
                if ev.type != "islocal.set":
                    continue
                enabled = bool(ev.data.get("enabled"))
                try:
                    if enabled != store.local_only(settings.local_only):
                        await apply_local_only(app.state, enabled, push_to_robot=False)
                        log.info("isLocal set from the robot's switch: %s", enabled)
                except Exception:  # noqa: BLE001 — never kill the watcher
                    log.exception("applying isLocal from the robot failed")
        finally:
            bus.unsubscribe(q)

    islocal_task = asyncio.create_task(_islocal_watcher(), name="dravix-islocal")

    async def _fw_notifier() -> None:
        """Every 6h, tell the robot which firmware version this release ships — its
        FW+ badge + "Firmware update available" HA sensor come alive from that. Local
        data only (parsed from the bundled YAML), so it runs with isLocal on too."""
        from .updates import push_latest_fw

        while True:
            try:
                eid = (app.state.discovered_entities or {}).get("latest_fw_text")
                if ha is not None and eid:
                    await push_latest_fw(ha, eid)
            except Exception:  # noqa: BLE001 — never die
                pass
            await asyncio.sleep(6 * 3600)

    fw_notify_task = asyncio.create_task(_fw_notifier(), name="dravix-fw-notify")

    async def _climate_pusher() -> None:
        """Keep the robot's CLIMATE page fresh with the configured AC's live state."""
        from .climate_bridge import push_status

        while True:
            try:
                if ha is not None:
                    await push_status(ha, store.climate_entity(), app.state.discovered_entities or {})
            except Exception:  # noqa: BLE001 — never die
                pass
            await asyncio.sleep(5)

    climate_task = asyncio.create_task(_climate_pusher(), name="dravix-climate")

    async def _personality_drift() -> None:
        """Slowly fold the robot's mood into its long-horizon temperament (once/day drift)."""
        while True:
            await asyncio.sleep(20 * 60)
            try:
                m = mood.snapshot()
                app.state.personality.observe(
                    float(m.get("valence", 0.0)),
                    float(m.get("arousal", 0.3)),
                    float(m.get("affection", 0.3)),
                )
            except Exception:  # noqa: BLE001 — never die
                pass

    personality_task = asyncio.create_task(_personality_drift(), name="dravix-personality")

    try:
        yield
    finally:
        log.info("shutting down dravix-os")
        for t in (islocal_task, fw_notify_task, climate_task, personality_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        # read the CURRENT bridge from app.state — /api/config/local_only may have
        # stopped/replaced the one this scope created.
        if getattr(app.state, "xiaozhi", None) is not None:
            await app.state.xiaozhi.stop()
        if ha_bridge is not None:
            await ha_bridge.stop()
        await app.state.agent.stop()
        await screen_pusher.stop()
        await scheduler.stop()
        await pet_head.stop()
        await vitals.stop()
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

    @app.middleware("http")
    async def api_token_auth(request: Request, call_next):
        """Optional shared-token auth (DRAVIX_API_TOKEN). When the token is empty (the
        default) this is a no-op. When set, every /api/* and /camera/* request must carry
        it — via ``Authorization: Bearer``, ``X-API-Token``, or ``?token=``. /api/health
        stays open for probes."""
        settings = getattr(request.app.state, "settings", None) or get_settings()
        token = settings.api_token
        path = request.url.path
        if token and path != "/api/health" and (
            path.startswith("/api/") or path.startswith("/camera/")
        ):
            auth = request.headers.get("authorization", "")
            supplied = auth[len("Bearer "):].strip() if auth.lower().startswith("bearer ") else ""
            supplied = (
                supplied
                or request.headers.get("x-api-token", "")
                or request.query_params.get("token", "")
            )
            if not secrets.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse(
                    {"detail": "missing or invalid API token"}, status_code=401
                )
        return await call_next(request)

    from .api.routes import router  # imported here to avoid a circular import

    app.include_router(router)

    # Serve the dashboard. The API/WS routes are registered first, so they take priority;
    # this SPA mount catches everything else. Prefer the React build, fall back to the
    # built-in vanilla page.
    spa_dir = WEB_DIST_DIR if WEB_DIST_DIR.exists() else WEB_STATIC_DIR
    if spa_dir.exists():
        app.mount("/", StaticFiles(directory=str(spa_dir), html=True), name="spa")

    return app
