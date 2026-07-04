"""Welcome-home celebration (the beloved Vector behavior, done the smart-home way).

Vector "gets excited when you come home" by seeing you. We know EARLIER: the moment a
Home Assistant ``person.*`` entity flips to ``home``, the event bridge publishes
``presence.home`` — and the robot lights up, perks its head toward the door, shows the
love face and greets out loud.

Runs as an AMBIENT mode (alongside whatever else is active). Quiet rules:
  * per-person throttle (``min_gap_min``) so a flapping phone doesn't spam the party;
  * skipped entirely while the robot reports a do-not-disturb state
    (focus / quiet / night / busy) — coming home wakes it from sleep/screensaver though.
"""
from __future__ import annotations

import time

from dravix.config import get_settings
from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.modes import Mode, ModeMeta

_DND_STATES = {"focus", "quiet", "night", "busy"}


class WelcomeMode(Mode):
    meta = ModeMeta(
        name="welcome",
        description="Celebrates when someone arrives home (HA person → home)",
        kind="ambient",
    )

    def __init__(self, ctx) -> None:  # noqa: ANN001 — ctx is ModeContext
        super().__init__(ctx)
        self._last: dict[str, float] = {}  # person entity -> last celebration (monotonic)

    async def on_event(self, event: Event) -> None:
        if event.type != "presence.home":
            return
        person = str(event.data.get("entity_id") or "someone")
        gap_s = max(0.0, float(self.ctx.config.get("min_gap_min", 15))) * 60.0
        now = time.monotonic()
        if now - self._last.get(person, -1e12) < gap_s:
            return
        if await self._do_not_disturb():
            return
        self._last[person] = now
        await self._celebrate()
        self.ctx.log.info("welcome: celebrated %s arriving home", person)

    async def _do_not_disturb(self) -> bool:
        reader = getattr(self.ctx.robot.driver, "get_text", None)
        if reader is None:
            return False
        try:
            state = await reader("state_sensor")
        except Exception:  # noqa: BLE001
            return False
        return (state or "").strip().lower() in _DND_STATES

    async def _celebrate(self) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.LOVE)
        if robot.supports(CAP_LEDS):
            await robot.set_leds("green", 0.8)
        if robot.supports(CAP_HEAD):
            # perk up toward the door — a clear "I noticed you!" pose
            await robot.move_head(0.0, 0.5, speed=1.0)
        line = str(
            cfg.get("line_he") if (get_settings().language or "en").startswith("he")
            else cfg.get("line") or ""
        ).strip()
        if line and robot.supports(CAP_SAY):
            try:
                await robot.say(line)
            except Exception:  # noqa: BLE001 — greeting is best-effort
                pass
