"""The firmware-update indicator reads the bundled fw_version from the firmware YAML."""
from __future__ import annotations

from dravix.updates import bundled_fw_version


def test_bundled_fw_version_is_readable():
    """Guards against the firmware YAML moving/renaming or the fw_version line becoming
    unparseable — either makes bundled_fw_version() return None, which silently disables the
    whole "firmware update available" nudge. (Note: this passes in CI where deploy/ is present;
    the add-on IMAGE must also COPY the YAML — see deploy/addon.Dockerfile.)"""
    v = bundled_fw_version()
    assert v, "bundled_fw_version() is None/empty — is deploy/esphome/stackchan-dravix.yaml present with a fw_version?"
