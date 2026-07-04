# Changelog

## 0.0.58

- **Volume control, both ends** (firmware v16): a real slider on the robot's
  swipe-down status bar (drag it — it also live-mirrors the actual speaker volume),
  and a matching 🔊 slider on the dashboard Home tab. Same speaker, always in sync.
- **It sneezes now** 🤧 (the beloved EMO bit): once in a while, among its little
  surprises — dizzy face, a shake, and an "Achoo!" that pops in its speech bubble.

## 0.0.57

- **Listening is a face, not a label** (firmware v15): when you talk to it, no more
  "Listening..." text — just the listening FACE (big curious eyes) and an attentive
  little perk-up, like it leans in.
- **A real comic speech bubble** 💬: the AI's words now appear in a bubble at the TOP
  of the screen with a tail pointing to the mouth — and the animated talking mouth
  stays fully visible while it speaks (the old bubble used to sit right on top of it).

## 0.0.56

- **Control Home Assistant FROM the robot's screen** (firmware v14): each of the 3
  cards now shows up to 4 finger-sized tappable rows — tap a row and it toggles
  lights/switches/fans/covers/locks, presses buttons, runs scripts & scenes, triggers
  automations, or flips the AC on/off. Sensors and other read-only entities just
  display. Pick what's on each card in the dashboard's Screens tab, as before.
- **Fixed: cards showed nothing.** The pusher used to trust a local "already wrote
  that" cache — but every robot reboot wipes the on-device text, so cards stayed
  blank. It now compares against the robot's REAL text and self-heals within
  seconds of any reboot (and re-discovers the slots each cycle, so device renames
  can't strand it either).
- **Dashboard language now reaches the robot**: switching English/עברית in the header
  also updates the server — wellness tips and greetings follow your language.

## 0.0.55

- **Wave at it 👋** (firmware v13): wave a hand at the robot's nose sensor (3 quick
  near/far swings) — it wakes, waves back with its head, happy face, warm flash.
- **Wellness tips follow YOU now**: they fire in *focus* too — that's exactly when
  you're at the desk (your work/gaming automations set it) — quietly (bubble only, no
  wiggle). And a new **Presence nearby** sensor (proximity) tells HA when someone is
  actually at the desk; tips are skipped when nobody's been there for 15 minutes.
  Sleep/night/quiet/away modes stay reminder-free.
- **Truly random idle motion**: it now skips beats (no fixed rhythm), varies how far
  it looks, mixes sideways glances with up/down tilts and diagonal looks, and drifts
  back near-centre instead of the exact same spot — no more "same move every time".

## 0.0.54

- **Asleep means completely still — sealed at every layer** (firmware v12). Beyond the
  firmware's own gesture gates, now: (1) the add-on drops ALL head commands (welcome
  celebrations, surprises, emotes, mood, follow…) while the robot reports
  sleep/screensaver; (2) the robot itself ignores any pitch command from any source
  while asleep. The only movements left in sleep are the intended droop when falling
  asleep and the rise when waking.

## 0.0.53

- **Status-bar polish** (firmware v11): the firmware-update indicator is now a proper
  amber **⬆ arrow icon** on the swipe-down status bar, and the battery line is clean —
  just "~2.3h left" (or "charging"); the raw W/mA readings stay available in Home
  Assistant as the INA226 sensors.

## 0.0.52

- **You now SEE firmware updates everywhere** (firmware v10):
  - **In Home Assistant**: a new `Firmware update available` sensor turns on the
    moment a newer firmware ships — build any automation/notification on it.
  - **On the robot**: an amber **FW+** badge appears on the swipe-down status bar.
  - **How it works**: the add-on writes the newest version into the robot's
    "Latest firmware" slot (every 6 h + whenever the Updates card opens); the robot
    compares it to what it's running. Fully local — works with isLocal on.
  - Updating is still one press: **Install** in ESPHome.

## 0.0.51

- **Asleep = truly still** (firmware v9): every gesture path (nudge / shake / nod) is
  now hard-blocked in sleep AND screensaver — no matter who commands it (a mood, an
  expression, a tip). Only waking itself moves the head back up.
- **Everything the robot knows is now in Home Assistant**: new diagnostic entities —
  WiFi signal (dBm), Uptime, IP address, Connected SSID, Chip temperature, Battery
  voltage — joining Battery level/charging, real power, reset reason, heap, loop time
  and the rest.

## 0.0.50

- **The every-few-minutes resets — root-caused and fixed** (firmware v8). Live
  diagnosis on the running robot: `Reset Reason = task watchdog`, average loop
  ~170 ms, every full-screen redraw 61 ms. The robot's main loop is legitimately
  heavy (animated face + on-device wake word + sensors + serial servos) — under a
  burst it starved the chip's IDLE task past the 5-second default and the watchdog
  rebooted a healthy robot. Fix: watchdog window 5s→15s, IDLE-task watching off
  (real hangs still reset via the loop's own watchdog), and quieter logging (INFO)
  to lighten every loop iteration. **Press Install in ESPHome to get firmware v8.**

## 0.0.49

Everything is now managed from the add-on dashboard in your browser:

- **🧩 Full Modes manager** (Settings): every plugin mode — follow, security, welcome,
  surprises, pomodoro, guard, dance, frigate-watch… — with run/stop, enable/disable,
  and an editor for each mode's settings (toggles for booleans, fields for
  numbers/text). Save applies live, no restart.
- **🎂 Birthday**: set your date (MM-DD) in Settings — once a year, that morning, the
  robot celebrates you: love-eyes, party lights and a spoken greeting.
- **🎁 NEW Surprises mode** (ambient): every hour or two, when awake and undisturbed,
  the robot does one small unprompted delight — a wiggle, a spin, a happy flash. The
  "it feels alive" secret of EMO/Vector, and you can tune or disable it in the Modes
  manager.
- **📝 Wellness tips editor** (Life tab): write your own reminder lines (one per
  line); empty restores the built-ins.

## 0.0.48

The "feels alive" release (firmware v7) — inspired by what people love most about
EMO, Vector, Cozmo and Eilik, plus the last gems from the original firmware:

- **It breathes.** The face rises and settles on a slow gentle sine while idle, and
  sways its head in tiny conversational moves while talking.
- **Hand-turn awareness**: twist its head by hand and it goes wide-eyed (x_x), then
  decides it liked it. And in the calm modes (night/focus/quiet) it now moves
  **zero** — body language fully off, not even slowly.
- **Boop!** Put a finger right up to its nose sensor → love-eyes + a happy nod.
- **It cares about games** (the Cozmo magic): gloats with a double-nod + green flash
  when it beats you at Rock-Paper-Scissors, huffs and turns away when it loses, and
  slumps sadly on a Simon/Flappy game-over.
- **Welcome home** 🏠 (better than Vector — HA knows you arrived): when a person
  entity flips to `home`, the robot perks toward the door, love-eyes, green LEDs and
  greets out loud. Per-person cool-down, silent in do-not-disturb modes.
- **Sleep breathing**: asleep on the charger, the LED bar breathes very dimly (EMO's
  beloved charger snooze). Wakes → instantly dark.
- **On-screen chat text**: whatever the robot says (dashboard chat / announcements)
  now also shows in its speech bubble — like the original app's text messages.

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
