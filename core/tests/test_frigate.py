"""Tests for the Frigate integration, the show_image capability, and local-only enforcement."""
from __future__ import annotations

import httpx
import pytest

from dravix.ai import build_provider
from dravix.config import Settings
from dravix.dal.base import CAP_DISPLAY, RobotController
from dravix.dal.mock_driver import MockDriver
from dravix.events import EventBus
from dravix.integrations.frigate import Frigate
from dravix.state import RobotState


class _FakeHA:
    async def states(self):
        return [
            {"entity_id": "camera.front"},
            {"entity_id": "camera.yard"},
            {"entity_id": "light.kitchen"},
        ]

    async def camera_snapshot(self, entity_id):
        return b"JPEG:" + entity_id.encode()


async def test_frigate_cameras_and_ha_snapshot():
    f = Frigate(_FakeHA())
    assert await f.cameras() == ["camera.front", "camera.yard"]
    assert await f.snapshot("camera.front") == b"JPEG:camera.front"


async def test_frigate_direct_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/yard/latest.jpg"
        return httpx.Response(200, content=b"DIRECT")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    f = Frigate(None, base_url="http://frigate:5000", client=client)
    assert await f.snapshot("yard") == b"DIRECT"
    await client.aclose()


async def test_controller_show_image_on_mock():
    c = RobotController(MockDriver(), EventBus(), RobotState())
    await c.connect()
    assert c.supports(CAP_DISPLAY)
    await c.show_image(b"\xff\xd8\xff")  # must not raise
    await c.close()


def test_local_only_blocks_cloud_allows_local():
    with pytest.raises(ValueError):
        build_provider(
            Settings(_env_file=None, ai_provider="claude", local_only=True, anthropic_api_key="x"),
            ha=None,
        )
    p = build_provider(Settings(_env_file=None, ai_provider="ollama", local_only=True), ha=None)
    assert p.name == "ollama"
