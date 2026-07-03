"""Tests for the xiaozhi bridge + the HA tools it exposes to the robot's AI (offline)."""
from __future__ import annotations

from dravix.integrations.xiaozhi_bridge import XiaoZhiBridge
from dravix.mcpserver.server import build_server


class _FakeHA:
    configured = True

    async def states(self):
        return [
            {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen"}},
            {"entity_id": "switch.fan", "state": "on", "attributes": {"friendly_name": "Fan"}},
        ]

    async def get_state(self, entity_id):
        return {"entity_id": entity_id, "state": "off"}

    async def call_service(self, domain, service, data=None):
        self.last = (domain, service, data)
        return {}


class _FakeController:
    async def say(self, *a, **k):
        pass


async def test_build_server_exposes_ha_tools_when_configured():
    mcp = build_server(
        _FakeController(), engine=None, ai=None, ha=_FakeHA(), expose_risky_tools=False
    )
    names = {t.name for t in await mcp.list_tools()}
    assert {"home_assistant_list_entities", "home_assistant_get_state",
            "home_assistant_assist", "home_assistant_toggle"} <= names
    # The risky tools stay hidden by default (DRAVIX_EXPOSE_RISKY_TOOLS=false).
    assert "home_assistant_call_service" not in names
    assert "home_assistant_lock" not in names


async def test_build_server_exposes_risky_tools_when_enabled():
    mcp = build_server(
        _FakeController(), engine=None, ai=None, ha=_FakeHA(), expose_risky_tools=True
    )
    names = {t.name for t in await mcp.list_tools()}
    assert {"home_assistant_call_service", "home_assistant_lock"} <= names


async def test_build_server_omits_ha_tools_without_ha():
    mcp = build_server(_FakeController(), engine=None, ai=None, ha=None)
    names = {t.name for t in await mcp.list_tools()}
    assert not any(n.startswith("home_assistant_") for n in names)


async def test_bridge_empty_url_is_noop():
    bridge = XiaoZhiBridge("", lambda: None)
    await bridge.start()
    assert bridge._task is None
    assert bridge.connected is False
    await bridge.stop()  # safe even when never started
