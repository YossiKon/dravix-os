"""Tests for the ScreenPusher: configured cards push formatted title+body via text.set_value."""
from __future__ import annotations

import asyncio

from dravix.screens import ScreenPusher


# The card slots carry whatever device prefix HA gave them (this one was renamed) —
# the pusher must DISCOVER them by suffix, not assume "text.dravix_...".
PREFIX = "text.study_room_dravix"


class _FakeHA:
    """Minimal HA stub: one state dump feeds both rendering and slot freshness, and
    text.set_value updates the slot state (like a real optimistic text entity)."""

    def __init__(self) -> None:
        self.calls: list = []
        # the robot's text slots, as optimistic entities (fresh boot = "unknown")
        self.slots = {
            f"{PREFIX}_card{n}_{kind}": "unknown" for n in (1, 2, 3) for kind in ("title", "body")
        }
        self._states = {
            "sensor.temp": {"state": "21", "attributes": {"friendly_name": "Living Room Temperature"}},
            "light.lamp": {"state": "on", "attributes": {"friendly_name": "Lamp"}},
            "climate.ac": {
                "state": "cool",
                "attributes": {
                    "friendly_name": "AC",
                    "current_temperature": 24.4,
                    "temperature": 21.0,
                },
            },
            "climate.bare": {"state": "heat", "attributes": {"friendly_name": "Bare AC"}},
        }

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))
        if domain == "text" and service == "set_value":
            self.slots[data["entity_id"]] = data["value"]

    async def states(self):
        out = [{"entity_id": eid, "state": st} for eid, st in self.slots.items()]
        out.extend({"entity_id": eid, **st} for eid, st in self._states.items())
        out.append({"entity_id": "text.something_else", "state": "x"})
        return out


class _StoreStub:
    def __init__(self, screens):
        self._screens = screens

    def screens(self):
        return self._screens


def _value(calls, entity_id):
    """Return the last value written to a given text entity, or None."""
    for domain, service, data in reversed(calls):
        if domain == "text" and service == "set_value" and data.get("entity_id") == entity_id:
            return data.get("value")
    return None


async def test_configured_screen_pushes_title_and_body():
    ha = _FakeHA()
    store = _StoreStub([
        {"title": "Home", "entities": ["sensor.temp", "light.lamp"]},
    ])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)  # let at least one push happen
    await pusher.stop()

    assert ("text", "set_value", {"entity_id": f"{PREFIX}_card1_title", "value": "Home"}) in ha.calls
    body = _value(ha.calls, f"{PREFIX}_card1_body")
    # friendly name truncated to ~14 chars, "Name  State" per line, newline-joined.
    assert body == "Living Room Te  21\nLamp  on"

    # Cards beyond what's configured stay blank (no write needed — already "unknown"→"").
    assert ha.slots[f"{PREFIX}_card2_title"] in ("unknown", "")
    assert _value(ha.calls, f"{PREFIX}_card2_body") is None


async def test_climate_card_formats_mode_and_temps():
    ha = _FakeHA()
    store = _StoreStub([{"title": "Air", "entities": ["climate.ac"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    await pusher.stop()

    # "Name  <mode> <current>><target>" — temps rounded to whole degrees.
    assert _value(ha.calls, f"{PREFIX}_card1_body") == "AC  cool 24>21"


async def test_climate_card_without_temps_falls_back_to_plain_line():
    ha = _FakeHA()
    store = _StoreStub([{"title": "Air", "entities": ["climate.bare"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    await pusher.stop()

    # No current/target attributes → the plain "Name  State" line.
    assert _value(ha.calls, f"{PREFIX}_card1_body") == "Bare AC  heat"


async def test_pusher_noop_without_ha():
    store = _StoreStub([{"title": "X", "entities": ["sensor.temp"]}])
    pusher = ScreenPusher(None, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.03)
    await pusher.stop()  # should not raise — nothing to push without HA


async def test_unknown_entity_is_skipped_not_fatal():
    ha = _FakeHA()
    store = _StoreStub([{"title": "Mix", "entities": ["sensor.boom", "light.lamp"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    await pusher.stop()

    # The missing entity is skipped; the good one still renders.
    assert _value(ha.calls, f"{PREFIX}_card1_body") == "Lamp  on"


async def test_unchanged_values_written_only_once():
    """Repeated polls must not re-write identical text (no device spam every cycle)."""
    ha = _FakeHA()
    store = _StoreStub([{"title": "Home", "entities": ["light.lamp"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.08)  # several polls
    await pusher.stop()

    title_writes = [
        c for c in ha.calls
        if c[0] == "text" and c[2].get("entity_id") == f"{PREFIX}_card1_title"
    ]
    assert len(title_writes) == 1


async def test_robot_reboot_wipes_slots_and_pusher_self_heals():
    """THE bug that blanked the user's cards: the robot reboots, its optimistic text
    slots reset to "unknown", and a local last-written cache believed the text was
    still there. Freshness is now judged against the ACTUAL slot state — the pusher
    must rewrite within one cycle of a reboot."""
    ha = _FakeHA()
    store = _StoreStub([{"title": "Home", "entities": ["light.lamp"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    assert ha.slots[f"{PREFIX}_card1_title"] == "Home"

    # 🤖💥 reboot: every slot back to "unknown"
    for k in ha.slots:
        ha.slots[k] = "unknown"
    await asyncio.sleep(0.05)
    await pusher.stop()
    assert ha.slots[f"{PREFIX}_card1_title"] == "Home"      # rewritten
    assert ha.slots[f"{PREFIX}_card1_body"] == "Lamp  on"   # rewritten


async def test_more_than_four_entities_are_capped_per_card():
    ha = _FakeHA()
    many = ["light.lamp", "sensor.temp", "climate.ac", "climate.bare", "light.lamp", "sensor.temp"]
    store = _StoreStub([{"title": "Busy", "entities": many}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    await pusher.stop()

    body = _value(ha.calls, f"{PREFIX}_card1_body")
    assert body is not None and len(body.split("\n")) == 4  # ROW_COUNT rows max
