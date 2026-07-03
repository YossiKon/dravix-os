# Changelog

## 0.0.47

Mined the original StackChan firmware + the M5Stack BSP for unused hardware — and
wired all of it in (firmware v6):

- **The robot is an IR blaster**: the BSP ships an infrared transmitter + a ready
  "Default AC" climate entity + an IR proxy for Home Assistant — pick
  `climate.*_default_ac` in the dashboard's Climate tab and the ROBOT controls your AC.
  And with the IR **receiver**, the robot now notices when anyone uses a TV/AC remote
  in the room and glances over, curious (throttled, never in calm modes).
- **Two new expressions** (ported from the original avatar's decorators): **in love**
  (pink eyes + blush + adoring nod) and **dizzy** (x_x eyes + a shake) — plus real
  **angry eyebrows** and a **sweat drop** while busy.
- **Real LED animations**: Party now runs the light bar's built-in rainbow effect, and
  the dashboard's LED section gained effect buttons — Rainbow / Twinkle / Random / Stop.
- **Graceful motion**: calm modes (night/quiet/focus) slow the head servos to gentle,
  quiet moves; normal speed everywhere else.

## 0.0.46

- **The battery number is now the REAL one** (firmware v5): read straight from the
  AXP2101 power chip's own fuel gauge — the exact same source the original StackChan
  firmware uses — plus a true hardware charging flag (no more guessing from current
  direction). The load-compensated LiPo model from 0.0.45 stays as the automatic
  fallback. New HA entities: `Battery level` and `Battery charging`.
- **NEW Security mode** 🛡: arm it from the dashboard (Home → Security) and the robot
  becomes a guard camera — saves a snapshot every few seconds to the add-on's storage
  (browse via `/api/security/photos`), patrols with its head every few minutes, and
  stays fully steerable with live view from the dashboard — including remotely through
  Home Assistant's remote access. Day-folders auto-prune (default 7 days); everything
  stays on your box.

## 0.0.45

- **An honest battery gauge** (firmware v4). The % now comes from a real battery model,
  not a straight line: load-sag compensation using the INA226's live current (a servo
  move no longer "drops" the battery), exponential smoothing, the true 1S-LiPo discharge
  curve (that long flat 3.8V plateau), and charging detection. While charging the status
  bar shows `%+` in cyan and says "charging" instead of a made-up time-left; low battery
  turns the label red.
- The good estimate is now a proper HA sensor (`Battery`, device-class battery) — visible
  in HA, auto-discovered by dravix, and shown as a 🔋 chip on the dashboard Home tab
  (red under 20%).

## 0.0.44

- **Everything personal is now a local knob** (firmware v3): device name (run several
  robots!), wake-word model, entity prefix, battery, and room thresholds are all
  substitutions — the git-stub lists the complete set, documented; Wi-Fi stays in your
  local secrets. The repo firmware contains nothing person-specific.

## 0.0.43

- **isLocal is a pure user choice**: on or off, set by you, persisted, and never flipped
  automatically (the add-on option only seeds the very first run). ON now means
  *everything stays inside your home network* — cloud AI blocked, cloud bridge
  disconnected, LAN-only images, and no update checks leave the house.
- **Choose it on the robot too**: firmware v2 adds a "Local only" switch and a LOCAL
  button on the robot's swipe-down status bar (teal when on). The robot, Home Assistant,
  and the dashboard all stay in sync automatically.

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
