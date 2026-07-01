"""Screens — push chosen Home Assistant entities onto the robot's 3 display cards.

The ESPHome firmware exposes six generic ``text`` entities (a title + a body per card):
``text.dravix_card{1,2,3}_title`` / ``text.dravix_card{1,2,3}_body``. The body is rendered
multi-line, lines split on ``"\n"``. This pusher polls HA every ``interval`` seconds, reads
the entities the user picked (per card, in the store), formats each card as
``"<friendly name>  <state>"`` lines, and writes title + body via ``text.set_value``.

The user picks the cards from the dashboard (``/api/screens``); this loop makes them live.
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

    async def _push_once(self) -> None:
        """Render every card and write it to the robot. Guarded so a bad entity can't kill us."""
        if self._ha is None:
            return
        cards = self._store.screens()
        for i in range(CARD_COUNT):
            n = i + 1
            card = cards[i] if i < len(cards) else None
            try:
                title = str(card.get("title", "")) if card else ""
                body = await self._render_body(card) if card else ""
                await self._set_text(f"text.dravix_card{n}_title", title)
                await self._set_text(f"text.dravix_card{n}_body", body)
            except Exception as exc:  # noqa: BLE001 — one bad card must not stop the rest
                log.debug("screen card %d push failed: %s", n, exc)

    async def _render_body(self, card: dict[str, Any]) -> str:
        lines: list[str] = []
        for entity_id in card.get("entities", []) or []:
            try:
                st = await self._ha.get_state(entity_id)  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001 — skip an entity that won't read
                log.debug("screen entity %s read failed: %s", entity_id, exc)
                continue
            attrs = st.get("attributes") or {}
            name = attrs.get("friendly_name") or entity_id
            name = str(name)[:NAME_MAX]
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

    async def _set_text(self, entity_id: str, value: str) -> None:
        await self._ha.call_service(  # type: ignore[union-attr]
            "text", "set_value", {"entity_id": entity_id, "value": value}
        )
