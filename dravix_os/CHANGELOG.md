# Changelog

## 0.0.39

- **Zero-config install**: the add-on now uses the Supervisor's own HA token when no
  long-lived token is pasted (leave `ha_token`/`ha_url` blank).
- **Raspberry Pi support**: aarch64 image is now built alongside amd64.
- **Works for any robot name**: the dashboard finds the robot's behaviour switches by
  suffix (no longer assumes a `dravix_*` entity prefix), and the firmware's HA entity
  prefix is now a single `substitutions:` value.
- **Dashboard**: connectivity is re-checked continuously (the online dot is live);
  offline states are shown honestly (no more frozen "Speaking…"/0% vitals); fonts are
  self-hosted (works on an internet-free LAN); chat input survives a failed send;
  climate no longer clamps to 16–30° when HA reports no limits.
- **Service hardening**: optional API token (`DRAVIX_API_TOKEN`), validated
  config import, SSRF guards on image/camera endpoints, the reaction engine survives
  bad rules, startup falls back to the mock driver instead of crashing, head control
  recovers automatically after the robot was offline.
- Wellness nudges are now bilingual (`DRAVIX_LANG`, default `en`, or the dashboard
  language) and configurable via the `wellness_tips` store key.

## 0.0.38 and earlier

See the git history.
