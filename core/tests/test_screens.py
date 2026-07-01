"""Tests for the ScreenPusher: configured cards push formatted title+body via text.set_value."""
from __future__ import annotations

import asyncio

from dravix.screens import ScreenPusher


class _FakeHA:
    """Minimal HA stub: records service calls, returns canned states."""

    def __init__(self) -> None:
        self.calls: list = []
        self.states = {
            "sensor.temp": {"state": "21", "attributes": {"friendly_name": "Living Room Temperature"}},
            "light.lamp": {"state": "on", "attributes": {"friendly_name": "Lamp"}},
        }

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))

    async def get_state(self, entity_id):
        return self.states.get(entity_id, {"state": "unknown", "attributes": {}})


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

    assert ("text", "set_value", {"entity_id": "text.dravix_card1_title", "value": "Home"}) in ha.calls
    body = _value(ha.calls, "text.dravix_card1_body")
    # friendly name truncated to ~14 chars, "Name  State" per line, newline-joined.
    assert body == "Living Room Te  21\nLamp  on"

    # Cards beyond what's configured get empty title + body.
    assert _value(ha.calls, "text.dravix_card2_title") == ""
    assert _value(ha.calls, "text.dravix_card2_body") == ""


async def test_pusher_noop_without_ha():
    store = _StoreStub([{"title": "X", "entities": ["sensor.temp"]}])
    pusher = ScreenPusher(None, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.03)
    await pusher.stop()  # should not raise — nothing to push without HA


async def test_bad_entity_does_not_kill_the_task():
    class _FlakyHA(_FakeHA):
        async def get_state(self, entity_id):
            if entity_id == "sensor.boom":
                raise RuntimeError("entity gone")
            return await super().get_state(entity_id)

    ha = _FlakyHA()
    store = _StoreStub([{"title": "Mix", "entities": ["sensor.boom", "light.lamp"]}])
    pusher = ScreenPusher(ha, store, interval=0.01)
    await pusher.start()
    await asyncio.sleep(0.05)
    await pusher.stop()

    # The bad entity is skipped; the good one still renders.
    assert _value(ha.calls, "text.dravix_card1_body") == "Lamp  on"
