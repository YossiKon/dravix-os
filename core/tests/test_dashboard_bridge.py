"""The dashboard-URL bridge: writes the screenshot URL into the firmware slot, diffed."""
from __future__ import annotations

import dravix.dashboard_bridge as db
from dravix.dashboard_bridge import push_url


class _HA:
    def __init__(self) -> None:
        self.calls: list = []

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))


def _reset() -> None:
    # the module keeps a process-wide diff cache; clear it so tests don't leak into each other
    db._last_pushed.clear()
    db._last_forced = 0.0


DISC = {"dash_url_text": "text.dravix_dashboard_url"}
URL = "http://homeassistant.local:10000/lovelace/0?viewport=320x240"


async def test_push_writes_then_diffs():
    _reset()
    ha = _HA()
    assert await push_url(ha, URL, DISC) is True
    assert ha.calls == [
        ("text", "set_value", {"entity_id": "text.dravix_dashboard_url", "value": URL})
    ]
    # same value again → no second write (the diff cache suppresses it), still reports "on robot"
    assert await push_url(ha, URL, DISC) is True
    assert len(ha.calls) == 1
    # a changed value writes
    await push_url(ha, "http://homeassistant.local:10000/other", DISC)
    assert len(ha.calls) == 2
    assert ha.calls[-1][2]["value"] == "http://homeassistant.local:10000/other"


async def test_force_rewrites_unchanged():
    _reset()
    ha = _HA()
    await push_url(ha, URL, DISC)
    await push_url(ha, URL, DISC, force=True)
    assert len(ha.calls) == 2  # force writes even when the value is unchanged (an explicit save)


async def test_empty_url_clears_the_slot():
    _reset()
    ha = _HA()
    await push_url(ha, "", DISC)
    assert ha.calls[-1][2]["value"] == ""


async def test_missing_entity_is_a_noop():
    _reset()
    ha = _HA()
    assert await push_url(ha, URL, {}) is False  # dash_url_text not discovered
    assert ha.calls == []


async def test_no_ha_does_not_raise():
    _reset()
    assert await push_url(None, URL, DISC) is False  # no HA configured → nothing delivered
