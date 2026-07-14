"""Reactions — user-configurable event→action rules (no plugin code required).

A rule maps a bus event type to one or more robot/home actions, with optional matching and
throttling. Rules live in the store (persisted, editable at runtime via ``/api/reactions``),
so a user can wire "front-door person → say X + show that camera" from config alone.

Example rule::

    {
      "name": "front-door",
      "on": "presence.detected",
      "match": {"entity_id": "binary_sensor.front_door_person"},
      "throttle_s": 30,
      "face": "doubt",
      "leds": {"color": "amber", "brightness": 0.6},
      "say": "Someone is at the {entity_id}.",
      "frigate_show": "camera.front_door",
      "activate_mode": null,
      "enabled": true
    }
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from .dal.base import CAP_DISPLAY, CAP_FACE, CAP_LEDS, CAP_SAY, RobotController, robot_is_quiet
from .emotes import play_emote
from .events import Event, EventBus
from .logging import get_logger

if TYPE_CHECKING:
    from .integrations.frigate import Frigate
    from .modes import ModeEngine
    from .store import Store

log = get_logger("reactions")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class ReactionEngine:
    def __init__(
        self,
        controller: RobotController,
        bus: EventBus,
        frigate: "Frigate | None" = None,
        engine: "ModeEngine | None" = None,
        store: "Store | None" = None,
    ) -> None:
        self._robot = controller
        self._bus = bus
        self._frigate = frigate
        self._engine = engine
        self._store = store
        self._last_fired: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    def _rules(self) -> list[dict[str, Any]]:
        return self._store.reactions() if self._store is not None else []

    # ── runtime ───────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._task = asyncio.create_task(self._pump(), name="dravix-reactions")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _pump(self) -> None:
        q = self._bus.subscribe()
        try:
            while True:
                event = await q.get()
                try:
                    await self.handle(event)
                except Exception as exc:  # noqa: BLE001 — one bad rule must never kill the pump
                    log.warning("reaction handling failed for %s: %s", event.type, exc)
        except asyncio.CancelledError:
            raise
        finally:
            self._bus.unsubscribe(q)

    # ── matching ───────────────────────────────────────────────────────────────
    async def handle(self, event: Event) -> None:
        for rule in self._rules():
            if not rule.get("enabled", True) or rule.get("on") != event.type:
                continue
            match = rule.get("match") or {}
            if any(event.data.get(k) != v for k, v in match.items()):
                continue
            if self._throttled(rule):
                continue
            await self._run(rule, event)

    def _throttled(self, rule: dict[str, Any]) -> bool:
        window = float(rule.get("throttle_s", 0) or 0)
        if window <= 0:
            return False
        name = rule.get("name") or rule.get("on") or "?"
        now = time.monotonic()
        last = self._last_fired.get(name)
        if last is not None and now - last < window:
            return True
        self._last_fired[name] = now
        return False

    # ── actions ────────────────────────────────────────────────────────────────
    async def _run(self, rule: dict[str, Any], event: Event) -> None:
        robot = self._robot
        ctx = _SafeDict(event.data)
        try:
            # DND: a motion rule must not flash faces/LEDs/speech at 3am — same hard rule
            # mood/vitals/agents follow. A rule that MUST fire at night (an alarm) opts
            # out with "respect_quiet": false.
            if rule.get("respect_quiet", True) and await robot_is_quiet(robot):
                return
            if rule.get("face") and robot.supports(CAP_FACE):
                await robot.set_face(rule["face"])
            leds = rule.get("leds")
            if leds and robot.supports(CAP_LEDS):
                # a reaction's light is a flourish — it returns to itself a few seconds later
                await robot.flash_leds(leds.get("color", "white"), float(leds.get("brightness", 1.0)))
            if rule.get("emote"):
                await play_emote(robot, rule["emote"], proactive=True)
            if rule.get("frigate_show") and self._frigate is not None and robot.supports(CAP_DISPLAY):
                img = await self._frigate.snapshot(rule["frigate_show"])
                await robot.show_image(img)
            if rule.get("say") and robot.supports(CAP_SAY):
                await robot.say(str(rule["say"]).format_map(ctx), proactive=True)
            if rule.get("activate_mode") and self._engine is not None:
                await self._engine.activate(rule["activate_mode"])
            await self._bus.publish("reaction.fired", rule=rule.get("name"), source=event.type)
        except Exception as exc:  # noqa: BLE001 — a bad rule must not kill the pump
            log.warning("reaction %s failed: %s", rule.get("name"), exc)
