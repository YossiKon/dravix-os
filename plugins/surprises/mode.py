"""Spontaneous surprises — the unprompted aliveness every companion robot is loved for.

Vector/EMO reviewers agree: what sells the illusion isn't commands, it's the robot doing
tiny things on its own. Every ~75±30 minutes (config), when the robot is awake and NOT in
a do-not-disturb state, it performs one small random delight — a happy wiggle, a curious
glance, a love flash, a tiny emote.

Ambient mode; disable it any time from the dashboard's Modes manager.
"""
from __future__ import annotations

import asyncio
import random

from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, Expression
from dravix.emotes import emote_names, play_emote
from dravix.modes import Mode, ModeMeta

_DND_STATES = {"focus", "quiet", "night", "busy", "sleep", "screensaver"}


class SurprisesMode(Mode):
    meta = ModeMeta(
        name="surprises",
        description="Small unprompted delights every hour or two",
        kind="ambient",
    )

    def __init__(self, ctx) -> None:  # noqa: ANN001 — ctx is ModeContext
        super().__init__(ctx)
        self._task: asyncio.Task | None = None

    async def on_enter(self) -> None:
        self._task = asyncio.create_task(self._run(), name="dravix-surprises")

    async def on_exit(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        cfg = self.ctx.config
        base = max(10.0, float(cfg.get("every_min", 75))) * 60.0
        jitter = max(0.0, float(cfg.get("jitter_min", 30))) * 60.0
        while True:
            await asyncio.sleep(base + random.uniform(-jitter, jitter))
            try:
                if await self._awake():
                    await self._delight()
            except Exception as exc:  # noqa: BLE001 — a failed surprise is just skipped
                self.ctx.log.debug("surprise skipped: %s", exc)

    async def _awake(self) -> bool:
        reader = getattr(self.ctx.robot.driver, "get_text", None)
        if reader is None:
            return True  # mock/unknown backend — surprise away
        try:
            state = (await reader("state_sensor") or "").strip().lower()
        except Exception:  # noqa: BLE001
            return False
        return state not in _DND_STATES

    async def _outdoor_temp(self) -> float | None:
        """The outdoor temperature from a weather entity (config, or the first one)."""
        if self.ctx.ha is None:
            return None
        entity = str(self.ctx.config.get("weather_entity") or "").strip()
        try:
            if not entity:
                for st in await self.ctx.ha.states():
                    if str(st.get("entity_id", "")).startswith("weather."):
                        entity = st["entity_id"]
                        break
            if not entity:
                return None
            st = await self.ctx.ha.get_state(entity)
            t = (st.get("attributes") or {}).get("temperature")
            return float(t) if t is not None else None
        except Exception:  # noqa: BLE001
            return None

    async def _delight(self) -> None:
        robot = self.ctx.robot
        # occasionally it just… sneezes (the beloved EMO bit): dizzy face, a shake,
        # and an "Achoo!" that also pops in its speech bubble. When it's genuinely
        # COLD outside, it "catches a cold" — sneezes much more, and says so.
        temp = await self._outdoor_temp()
        cold = temp is not None and temp < float(self.ctx.config.get("cold_c", 10))
        if random.random() < (0.45 if cold else 0.12):
            he = self.ctx.language().startswith("he")  # dashboard toggle wins over env
            try:
                if robot.supports(CAP_FACE):
                    await robot.set_face(Expression.DIZZY)
                if cold:
                    line = "אַפְּצִ'י! קר בחוץ, אני קצת מצונן" if he else "Achoo! It's cold out — I've caught the sniffles"
                else:
                    line = "אַפְּצִ'י!" if he else "Achoo!"
                if robot.supports(CAP_SAY):
                    await robot.say(line)
                await asyncio.sleep(2.0)
                if robot.supports(CAP_FACE):
                    await robot.set_face(Expression.NEUTRAL)
                self.ctx.log.info("surprise: sneeze")
                return
            except Exception:  # noqa: BLE001 — fall through to a regular delight
                pass
        # prefer a random named emote when the backend can express them
        names = [n for n in emote_names() if n not in ("wake", "sleep")]
        if names and random.random() < 0.7:
            await play_emote(robot, random.choice(names))
            self.ctx.log.info("surprise: emote")
            return
        # otherwise a simple homemade delight
        if robot.supports(CAP_FACE):
            await robot.set_face(random.choice([Expression.HAPPY, Expression.LOVE, Expression.DOUBT]))
        if robot.supports(CAP_LEDS):
            await robot.set_leds(random.choice(["green", "purple", "cyan"]), 0.6)
        if robot.supports(CAP_HEAD):
            await robot.move_head(random.uniform(-0.3, 0.3), random.uniform(0.0, 0.3), speed=0.6)
        await asyncio.sleep(2.5)
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.NEUTRAL)
        if robot.supports(CAP_LEDS):
            await robot.set_leds("off", 0.0)
        self.ctx.log.info("surprise: little delight")
