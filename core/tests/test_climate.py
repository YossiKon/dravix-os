"""Climate endpoints: the set-service call shape + state read, using a fake HA + request."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from dravix.api.routes import (
    ClimateSetBody,
    get_climate_state,
    set_climate,
)


class _FakeHA:
    def __init__(self, state=None) -> None:
        self.calls: list = []
        self._state = state or {}

    async def call_service(self, domain, service, data=None):
        self.calls.append((domain, service, data))

    async def get_state(self, entity_id):
        return self._state


def _request(ha):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(ha=ha)))


async def test_climate_set_temperature_and_mode():
    ha = _FakeHA()
    body = ClimateSetBody(entity_id="climate.ac", temperature=22.5, hvac_mode="cool")
    assert await set_climate(body, _request(ha)) == {"ok": True}
    assert ha.calls == [
        ("climate", "set_temperature", {"entity_id": "climate.ac", "temperature": 22.5}),
        ("climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "cool"}),
    ]


async def test_climate_set_temperature_only():
    ha = _FakeHA()
    body = ClimateSetBody(entity_id="climate.ac", temperature=20)
    await set_climate(body, _request(ha))
    assert ha.calls == [
        ("climate", "set_temperature", {"entity_id": "climate.ac", "temperature": 20}),
    ]


async def test_climate_set_without_ha_is_503():
    from fastapi import HTTPException

    body = ClimateSetBody(entity_id="climate.ac", temperature=20)
    with pytest.raises(HTTPException) as exc:
        await set_climate(body, _request(None))
    assert exc.value.status_code == 503


async def test_climate_state_reads_attributes():
    ha = _FakeHA(
        state={
            "state": "cool",
            "attributes": {
                "current_temperature": 24,
                "temperature": 21,
                "hvac_modes": ["off", "cool", "heat"],
                "min_temp": 16,
                "max_temp": 30,
                "target_temp_step": 0.5,
            },
        }
    )
    out = await get_climate_state(_request(ha), entity_id="climate.ac")
    assert out["state"] == "cool"
    assert out["hvac_mode"] == "cool"
    assert out["current_temperature"] == 24
    assert out["temperature"] == 21
    assert out["hvac_modes"] == ["off", "cool", "heat"]
    assert out["min_temp"] == 16 and out["max_temp"] == 30
    assert out["target_temp_step"] == 0.5
