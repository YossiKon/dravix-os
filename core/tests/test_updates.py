"""The firmware-update indicator reads the bundled fw_version from the firmware YAML."""
from __future__ import annotations

import pytest

from dravix import updates
from dravix.updates import bundled_fw_version, update_report


def test_bundled_fw_version_is_readable():
    """Guards against the firmware YAML moving/renaming or the fw_version line becoming
    unparseable — either makes bundled_fw_version() return None, which silently disables the
    whole "firmware update available" nudge. (Note: this passes in CI where deploy/ is present;
    the add-on IMAGE must also COPY the YAML — see deploy/addon.Dockerfile.)"""
    v = bundled_fw_version()
    assert v, "bundled_fw_version() is None/empty — is deploy/esphome/stackchan-dravix.yaml present with a fw_version?"


class _FakeHA:
    def __init__(self, robot_fw: str):
        self._robot_fw = robot_fw

    async def states(self):
        return [{"entity_id": "sensor.dravix_firmware_version", "state": self._robot_fw}]


@pytest.mark.parametrize(
    ("bundled", "robot", "fw_update", "addon_fw_stale"),
    [
        ("60", "55", True, False),   # the robot is behind → press Install
        ("55", "60", False, True),   # the robot is AHEAD of this add-on — not an update
        ("60", "60", False, False),
        ("10", "9", True, False),    # numeric, not string order
    ],
)
async def test_firmware_update_means_newer_not_different(monkeypatch, bundled, robot, fw_update, addon_fw_stale):
    """An add-on built from an older copy of the firmware YAML used to flag ANY mismatch as
    "new firmware available" — a robot running newer firmware got nagged forever."""
    monkeypatch.setattr(updates, "bundled_fw_version", lambda: bundled)
    report = await update_report(_FakeHA(robot), allow_network=False)
    assert report["fw_update"] is fw_update
    assert report["addon_fw_stale"] is addon_fw_stale
