"""Screens — push chosen Home Assistant entities onto the robot's 3 display cards.

The ESPHome firmware exposes six generic ``text`` entities (a title + a body per card),
named ``card{1,2,3}_title`` / ``card{1,2,3}_body``. Their FULL entity ids depend on how the
device is named in HA (e.g. ``text.dravix_card1_title`` vs ``text.study_room_dravix_card1_title``
after a rename), so the slots are DISCOVERED from HA by their unique object-id suffix — and
re-discovered EVERY cycle from the same state fetch, so a device rename or re-flash can
never leave the pusher writing to dead entities.

Freshness is judged against the slot's REAL state from that same fetch (not a local
"last written" cache): the robot wipes its optimistic text slots on every reboot, and a
local cache used to believe the text was still there — cards then stayed blank until the
add-on restarted. Comparing to the actual state makes the pusher self-heal within one
cycle of any robot reboot.

Each card shows up to ``ROW_COUNT`` entities (one per tappable row on the robot — tapping
a row fires ``esphome.dravix_card`` back to dravix, which performs the right action for
the entity's domain). The user picks the cards from the dashboard (``/api/screens``).
One bad entity never kills the task — the whole loop body is guarded. Only runs with HA.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .logging import get_logger

if TYPE_CHECKING:
    from .integrations.homeassistant import HomeAssistant
    from .store import Store

log = get_logger("screens")

CARD_COUNT = 3  # the firmware exposes exactly three cards
ROW_COUNT = 4  # tappable rows per card — more won't fit a 320x240 screen comfortably
NAME_MAX = 14  # truncate long friendly names so a line fits the small display


class ScreenPusher:
    def __init__(
        self,
        ha: "HomeAssistant | None",
        store: "Store",
        interval: float = 5.0,
    ) -> None:
        self._ha = ha
        self._store = store
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._pump(), name="dravix-screens")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _pump(self) -> None:
        try:
            while True:
                await self._push_once()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _resolve_slots(states: list[dict[str, Any]]) -> dict[str, str]:
        """Card slot ("card1_title") → entity_id, from a full state dump. When a rename
        left BOTH an old dead entity and a live one, the available one wins."""
        slots: dict[str, str] = {}
        for st in states:
            eid = st.get("entity_id", "")
            if not eid.startswith("text."):
                continue
            for n in range(1, CARD_COUNT + 1):
                for kind in ("title", "body"):
                    key = f"card{n}_{kind}"
                    if not eid.endswith(key):
                        continue
                    known = slots.get(key)
                    alive = st.get("state") != "unavailable"
                    if known is None or alive:
                        slots[key] = eid
        return slots

    async def _push_once(self) -> None:
        """Render every card and write whatever differs from the robot's actual text."""
        if self._ha is None:
            return
        try:
            states = await self._ha.states()
        except Exception as exc:  # noqa: BLE001 — HA hiccup; retry next cycle
            log.debug("screens: state fetch failed: %s", exc)
            return
        smap = {st.get("entity_id", ""): st for st in states}
        slots = self._resolve_slots(states)
        cards = self._store.screens()
        for i in range(CARD_COUNT):
            n = i + 1
            title_ent = slots.get(f"card{n}_title")
            body_ent = slots.get(f"card{n}_body")
            if not (title_ent and body_ent):
                continue  # robot not flashed with the card firmware (yet)
            card = cards[i] if i < len(cards) else None
            try:
                # truncate to the firmware slots' max_length (30 / 160) — an over-long
                # value fails text.set_value validation and the card would stay stale
                title = str(card.get("title", ""))[:30] if card else ""
                body = self._render_body(card, smap)[:160] if card else ""
                await self._sync_text(title_ent, title, smap)
                await self._sync_text(body_ent, body, smap)
            except Exception as exc:  # noqa: BLE001 — one bad card must not stop the rest
                log.debug("screen card %d push failed: %s", n, exc)

    def _render_body(self, card: dict[str, Any], smap: dict[str, dict]) -> str:
        lines: list[str] = []
        for entity_id in (card.get("entities", []) or [])[:ROW_COUNT]:
            st = smap.get(entity_id)
            if st is None:
                continue
            attrs = st.get("attributes") or {}
            name = str(attrs.get("friendly_name") or entity_id)[:NAME_MAX]
            state = st.get("state", "")
            # Climate entities read nicer as "Name  cool 24>21" (mode + current>target)
            # than the bare hvac state; fall back to the plain line if attrs are missing.
            if entity_id.startswith("climate."):
                try:
                    current = attrs.get("current_temperature")
                    target = attrs.get("temperature")
                    if current is not None and target is not None:
                        lines.append(
                            f"{name}  {state} {float(current):.0f}>{float(target):.0f}"
                        )
                        continue
                except Exception as exc:  # noqa: BLE001 — never let one card break the loop
                    log.debug("climate format for %s failed: %s", entity_id, exc)
            lines.append(f"{name}  {state}")
        return "\n".join(lines)

    async def handle_tap(self, card: int, row: int) -> None:
        """A row was tapped ON THE ROBOT — do the right thing for that entity's type.

        toggle-ables toggle, buttons press, scripts/scenes run, automations trigger,
        climate flips on/off. Read-only domains (sensors, text…) are simply ignored.
        """
        if self._ha is None:
            return
        cards = self._store.screens()
        try:
            picked = (cards[card - 1].get("entities") or [])[:ROW_COUNT]
        except (IndexError, AttributeError, TypeError):
            return
        # CRITICAL: the rendered rows skip entities that are missing from HA — the tapped
        # row index refers to that same FILTERED list, or a tap could actuate the wrong
        # device (renamed entity above a lock/cover…).
        try:
            known = {st.get("entity_id") for st in await self._ha.states()}
        except Exception:  # noqa: BLE001 — can't verify alignment → don't act
            return
        visible = [e for e in picked if e in known]
        try:
            entity = visible[row]
        except IndexError:
            return
        domain = entity.split(".", 1)[0]
        action: tuple[str, str] | None = None
        if domain in ("switch", "light", "fan", "input_boolean", "media_player",
                      "cover", "lock", "siren", "humidifier"):
            action = ("homeassistant", "toggle")
        elif domain in ("button", "input_button"):
            action = (domain, "press")
        elif domain in ("script", "scene"):
            action = (domain, "turn_on")
        elif domain == "automation":
            action = ("automation", "trigger")
        elif domain == "climate":
            action = ("climate", "toggle")
        if action is None:
            return  # read-only row (sensor / text / …) — display only
        try:
            await self._ha.call_service(action[0], action[1], {"entity_id": entity})
            log.info("card tap: %s.%s -> %s", action[0], action[1], entity)
        except Exception as exc:  # noqa: BLE001 — a failed tap must not crash anything
            log.warning("card tap on %s failed: %s", entity, exc)

    async def _sync_text(self, entity_id: str, value: str, smap: dict[str, dict]) -> None:
        """Write only when the robot's ACTUAL slot text differs (self-heals after reboots)."""
        actual = str((smap.get(entity_id) or {}).get("state") or "")
        if actual in ("unknown", "unavailable"):
            actual = ""
        if actual == value:
            return
        await self._ha.call_service(  # type: ignore[union-attr]
            "text", "set_value", {"entity_id": entity_id, "value": value}
        )
