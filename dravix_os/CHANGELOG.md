# Changelog

## 0.0.42

- **Releases + rollback**: every version now gets a git tag (`v0.0.42`) and a GitHub
  Release automatically. Firmware rollback = point the ESPHome stub's `ref:` at an older
  tag and press Install; add-on rollback = revert the version (all images stay on GHCR).
- **Update visibility**: the firmware now publishes its version to HA, and Settings shows
  an **Updates** card — add-on version vs the newest release, robot firmware vs the
  firmware this release ships — with plain instructions (and no internet calls while
  isLocal is on).
- **i18n built to grow**: languages live in one registry; adding a language is one
  dictionary file (`web/src/locales/TEMPLATE.example.ts`) + one registry line — the
  header button cycles through all of them. Core tips likewise take new languages with
  a single dict entry.

## 0.0.41

- **English is now the default everywhere** (open-source ready): the dashboard opens in
  English (Hebrew auto-selected for Hebrew browsers, and the header toggle switches live),
  wellness tips default to English, and the add-on has a `language: en|he` option.
- **The robot's default name is "Dravix"** — shown in the header and known to the AI;
  rename it any time in Settings. An explicit name overrides a persona's, the default
  doesn't.

## 0.0.40

- **isLocal — master local-only switch** (Settings): when ON, only local things run —
  cloud AI providers are blocked, the cloud MCP bridge disconnects, and robot images
  load only from LAN addresses. When OFF everything behaves normally. Applied live,
  no restart, and it overrides the add-on's `local_only` option both ways.
- **Zero-setup entity wiring**: the robot's Home Assistant entities (face, head, mode,
  privacy, speaker, camera, sensors, timers…) are now AUTO-DISCOVERED by suffix — the
  Settings page shows what was found, read-only. Nothing to fill in, works with any
  device name or a renamed device.

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
