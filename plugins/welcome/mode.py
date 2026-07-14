"""Welcome-home celebration — now BY NAME (the beloved Vector "greets you by name" moment).

Two ways to know who arrived, both fully local:
  * a Home Assistant ``person.*`` entity flips to ``home`` → ``presence.home`` (the name is
    the person's friendly name);
  * Frigate **face recognition** — while active this ambient mode polls Frigate for a
    recognised face (``sub_label``) and greets that person.

The robot wakes, perks toward the door, shows the love face, LEDs green and says e.g.
"Welcome back, Yossi!". A configured ``primary`` person gets an extra-warm greeting.

Quiet rules: a per-name throttle (``min_gap_min``) so a flapping phone / a lingering face
doesn't spam the party, and skipped while the robot reports a do-not-disturb state
(focus/quiet/night/busy) — arriving still wakes it from sleep/screensaver.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from dravix.config import get_settings
from dravix.dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.integrations.frigate import Frigate
from dravix.modes import Mode, ModeMeta

_DND_STATES = {"focus", "quiet", "night", "busy"}


def _pretty(name: str) -> str:
    """"yossi" / "person.yossi" → "Yossi" (a friendly capitalised first name)."""
    n = (name or "").strip().split(".")[-1].replace("_", " ").strip()
    return (n[:1].upper() + n[1:]) if n else n


def _greeting_line(base: str, name: str, he: bool) -> str:
    """Build the spoken greeting. ``base`` may contain ``{name}``; otherwise the name is
    appended. Falls back to a sensible default when there's no name (so a ``{name}`` template
    with an unknown person never says a dangling comma)."""
    base = (base or "").strip()
    if name:
        if "{name}" in base:
            return base.replace("{name}", name).strip()
        if base:
            return f"{base} {name}".strip()
        return f"ברוך שובך, {name}!" if he else f"Welcome back, {name}!"
    # no name known
    if base and "{name}" not in base:
        return base
    return "ברוך שובך!" if he else "Welcome back!"


class WelcomeMode(Mode):
    meta = ModeMeta(
        name="welcome",
        description="Greets people by name when they arrive (HA person → home, or Frigate face)",
        kind="ambient",
    )

    def __init__(self, ctx) -> None:  # noqa: ANN001 — ctx is ModeContext
        super().__init__(ctx)
        self._last: dict[str, float] = {}  # name -> last celebration (monotonic)
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._frigate: Frigate | None = None

    # ── Frigate face polling (optional, self-contained) ─────────────────────────────
    async def on_enter(self) -> None:
        if not bool(self.ctx.config.get("use_frigate_faces", True)):
            return
        url = str(self.ctx.config.get("frigate_url") or get_settings().frigate_url or "").strip()
        if not url:
            return  # no Frigate → HA-person greetings still work via on_event
        self._client = httpx.AsyncClient(timeout=5.0)
        self._frigate = Frigate(self.ctx.ha, base_url=url, client=self._client)
        self._task = asyncio.create_task(self._face_loop(), name="dravix-welcome-faces")
        self.ctx.log.info("welcome: watching Frigate for known faces via %s", url)

    async def on_exit(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._frigate = None

    async def _face_loop(self) -> None:
        cam = str(self.ctx.config.get("frigate_camera") or "").strip()
        poll = max(2.0, float(self.ctx.config.get("face_poll_s", 6)))
        while True:
            try:
                name = await self._frigate.latest_face(cam) if self._frigate else None
                if name:
                    # let the rest of the house react too — reaction rules can key on
                    # {"on": "face.seen", "match": {"person": "..."}} for per-person magic
                    await self.ctx.bus.publish("face.seen", person=_pretty(name))
                    await self._maybe_greet(_pretty(name))
            except Exception as exc:  # noqa: BLE001 — a poll failure must not stop the loop
                self.ctx.log.debug("welcome: face poll failed: %s", exc)
            await asyncio.sleep(poll)

    # ── HA person → home ────────────────────────────────────────────────────────────
    async def on_event(self, event: Event) -> None:
        if event.type != "presence.home":
            return
        entity = str(event.data.get("entity_id") or "")
        await self._maybe_greet(await self._friendly_name(entity))

    async def _friendly_name(self, entity_id: str) -> str:
        """The person's display name — HA friendly_name if we can read it, else derived."""
        if entity_id and self.ctx.ha is not None:
            try:
                st = await self.ctx.ha.get_state(entity_id)
                fn = (st.get("attributes") or {}).get("friendly_name")
                if fn:
                    return _pretty(str(fn))
            except Exception:  # noqa: BLE001 — fall back to the entity id
                pass
        return _pretty(entity_id) or ""

    # ── the greeting ────────────────────────────────────────────────────────────────
    def _person(self, name: str) -> dict:
        """The person's dashboard record (Settings → People) — custom greeting + primary."""
        if not name or self.ctx.store is None:
            return {}
        try:
            return self.ctx.store.person(name) or {}
        except Exception:  # noqa: BLE001 — a store hiccup must not kill the greeting
            return {}

    async def _maybe_greet(self, name: str) -> None:
        key = name or "someone"
        gap_s = max(0.0, float(self.ctx.config.get("min_gap_min", 15))) * 60.0
        now = time.monotonic()
        if now - self._last.get(key, -1e12) < gap_s:
            return
        if await self._do_not_disturb():
            return
        self._last[key] = now
        person = self._person(name)
        primary = _pretty(str(self.ctx.config.get("primary") or ""))
        warm = bool(person.get("primary")) or (bool(primary) and name.lower() == primary.lower())
        await self._celebrate(name, warm=warm, person=person)
        self.ctx.log.info("welcome: greeted %s", key)

    async def _do_not_disturb(self) -> bool:
        reader = getattr(self.ctx.robot.driver, "get_text", None)
        if reader is None:
            return False
        try:
            state = await reader("state_sensor")
        except Exception:  # noqa: BLE001
            return False
        return (state or "").strip().lower() in _DND_STATES

    async def _celebrate(self, name: str, warm: bool = False, person: dict | None = None) -> None:
        robot = self.ctx.robot
        cfg = self.ctx.config
        person = person or {}
        if await self.ctx.is_asleep():  # coming home should WAKE it
            setter = getattr(robot.driver, "set_mode", None)
            if setter is not None:
                try:
                    await setter("awake")
                    await asyncio.sleep(0.4)
                except Exception:  # noqa: BLE001
                    pass
        if robot.supports(CAP_FACE):
            await robot.set_face(Expression.LOVE)
        if robot.supports(CAP_LEDS):
            # a burst of green, not permanent lighting — it returns to itself
            await robot.flash_leds("green", 1.0 if warm else 0.8, revert_s=6.0)
        if robot.supports(CAP_HEAD):
            await robot.move_head(0.0, 0.5, speed=1.0)  # perk up toward the door
            if warm:  # a happy extra bob for your favourite person
                await asyncio.sleep(0.35)
                await robot.move_head(0.0, 0.2, speed=1.0)
        he = self.ctx.language().startswith("he")
        # the person's OWN line (Settings → People) wins; the mode's generic line is the fallback
        base = str((person.get("line_he") if he else person.get("line")) or "").strip()
        if not base:
            base = str((cfg.get("line_he") if he else cfg.get("line")) or "").strip()
        line = _greeting_line(base, name, he)
        if line and robot.supports(CAP_SAY):
            try:
                await robot.say(line, proactive=True)
            except Exception:  # noqa: BLE001 — greeting is best-effort
                pass
        if robot.supports(CAP_HEAD):
            # the perk is a gesture, not a pose — settle back so the head doesn't stay up
            await asyncio.sleep(1.6)
            try:
                await robot.move_head(0.0, 0.0, speed=0.7)
            except Exception:  # noqa: BLE001
                pass
