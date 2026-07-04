# dravix-os

<p align="center">
  <img src="docs/dravix-robot.svg" alt="dravix-os — the StackChan pet face" width="680">
</p>

<p align="center">
  <b>A local-first companion layer for the M5Stack StackChan desk robot — delivered as a Home Assistant add-on.</b>
</p>

dravix-os turns the StackChan into a little desk creature you fully own. You re-flash the robot to
custom **dravix ESPHome firmware** — a drawn animated pet face, petting, voice, camera, LEDs, a
games arcade and a *real life* (needs it takes care of) — which exposes every part of the hardware
to Home Assistant as ordinary entities. The dravix add-on then drives it through those entities,
adding custom **modes**, a **mobile dashboard**, a persistent **personality**, a pluggable **AI
brain**, and deep **smart-home** integration. Everything runs on your own hardware; nothing phones
home.

```
┌──────────────────────────────┐   ESPHome   ┌──────────────────────────────────────────────┐
│  StackChan · M5 CoreS3        │   native    │       Home Assistant  (your always-on host)   │
│  ── custom dravix ESPHome ──  │   API       │  ┌────────────────┐   ┌────────────────────┐  │
│  drawn pet face · head servos │◄───────────►│  │    HA core     │◄─►│  dravix-os add-on  │  │
│  mic · speaker · touch        │             │  │  entities +    │   │  dashboard · modes │  │
│  camera · LEDs · battery      │             │  │  Assist        │   │  personality · AI  │  │
└──────────────────────────────┘             │  └────────────────┘   │  MCP server        │  │
            the body                          │                       └────────────────────┘  │
                                              └──────────────────────────────────────────────┘
                                                        the brain + control panel
```

The robot joins Home Assistant over the ESPHome native API; the dravix add-on runs inside HA and
talks to HA core over REST/WebSocket. There is no cloud in the loop.

## 🧭 Core principles

1. **Local-first.** dravix-os runs fully on your box. **Local-only (isLocal)** is *your* persisted
   choice — toggled from the robot's LOCAL button, the dashboard or HA, all synced; when on, cloud
   AI is refused and nothing leaves your LAN. See [docs/local-only.md](docs/local-only.md).
2. **Everything is pluggable.** Robot drivers, AI providers and modes are swappable behind clean
   interfaces (the [Device Abstraction Layer](docs/architecture.md)). Higher layers only ever see
   the `RobotController` facade, so *how* the robot is reached can change without touching modes,
   AI or the dashboard.
3. **Capability-guarded.** Modes check `robot.supports(...)` before acting, so behaviour degrades
   gracefully across backends.

## 🚀 From a stock robot to alive — the complete walkthrough

Every step, from a factory StackChan to a living desk creature. Nothing here requires prior
ESPHome experience.

**What you'll need**

| | Item | Notes |
|---|------|-------|
| 🤖 | M5Stack **StackChan (CoreS3)** | the robot |
| 🏠 | **Home Assistant** running on an always-on box | any install type with add-on support |
| 🧩 | The official **ESPHome Device Builder** add-on | Settings → Add-ons → Add-on Store → ESPHome |
| 🔌 | A **USB-C cable** | needed once, for the first flash; updates are OTA afterwards |

### Step 0 · 🛡️ Back up the original firmware (5 min, do NOT skip)

A byte-for-byte snapshot of the robot exactly as it left the factory — you can always go back.
Follow **Step 0 — Back up the original firmware** in
[docs/esphome-local-control.md](docs/esphome-local-control.md) (one `esptool read_flash` command).

### Step 1 · Create the robot's ESPHome config (the tiny git file)

1. Open the **ESPHome Device Builder** → **+ New Device** → give it a name (e.g. `stackchan`) →
   **Skip** the wizard's install step.
2. Click **Edit** on the new device and replace ALL of its YAML with the tiny (~60-line)
   [`deploy/esphome/stackchan-from-git.yaml`](deploy/esphome/stackchan-from-git.yaml).
3. Edit the two **Wi-Fi lines** at the top (`ssid:` / `password:` — your home network).
   That tiny file is the only thing that ever lives in your ESPHome: it pulls the real firmware
   from this repo on every build, so **firmware updates = press Install again**. All personal
   tuning (device name, wake word, room thresholds) is right there as commented lines.

### Step 2 · First flash (USB, once)

Plug the robot into the computer with USB-C → in the device's ⋮ menu pick **Install → Plug into
this computer** → choose the serial port. The first build takes a while (it compiles a wake-word
model); after it finishes the robot boots with the dravix pet face and joins your Wi-Fi. Every
future update is wireless (**Install → Wirelessly**).

### Step 3 · Adopt it in Home Assistant

HA discovers the new ESPHome device automatically (**Settings → Devices & Services** → the
discovered `stackchan` → **Configure**). Then one recommended tweak: **rename the device to
`Dravix`** (open the device page → ✏️ → rename → let HA update the entity ids). That matches the
firmware's default entity prefix. Prefer keeping the name `stackchan`? Then set
`ha_prefix: "stackchan"` in the tiny file instead.

### Step 4 · Install the dravix-os add-on

**Settings → Add-ons → Add-on Store → ⋮ → Repositories** → add
`https://github.com/YossiKon/dravix-os` → install **dravix-os** → **Start**. That's the whole
configuration: it authenticates to HA by itself (Supervisor token) and **auto-discovers every
robot entity** — face, head servos, mode, speaker, LEDs, camera, sensors. Nothing to map.

### Step 5 · Open the dashboard and say hi

Click **Open Web UI** on the add-on page (or `http://<home-assistant>:8800`). You'll see the live
face, the language toggle (English default, עברית built-in), and in **Settings** — the
auto-detected wiring (read-only), your robot's name, and the master **Local-only** switch.
Pet the robot's head. It will like that.

### Updating & rolling back

| | How |
|---|-----|
| **Update the firmware** | ESPHome → **Install** (the tiny file pulls the latest from the repo) |
| **Update the add-on** | HA shows the update automatically (Settings → Add-ons) — with a changelog |
| **Know something's new** | Dashboard → Settings → **Updates** card compares versions for both |
| **Roll back firmware** | In the tiny file set `ref: v0.0.43` (any tag from [Releases](https://github.com/YossiKon/dravix-os/releases)) → Install |
| **Roll back the add-on** | Every version's image is kept — revert the version in `dravix_os/config.yaml` |
| **Go back to factory** | Re-flash your Step-0 backup (or stock firmware via M5Burner) |

> No robot yet? You can still run and explore everything against the built-in **mock** driver —
> see the **Development** section below.

## 🎮 Everyday use — the cheat sheet

Everything is done by touching the robot, talking to it, or from the dashboard:

| You do | The robot does |
|--------|----------------|
| Say **"Okay, Nabu"** | Wakes and listens (big eyes, yellow LEDs) → answers via HA Assist, reply shown in its speech bubble |
| **Tap the face** | Starts a voice conversation (tap again to stop) |
| **Long-press the face** (1.2 s) | Goes to sleep instantly |
| **Pet the head** (front / middle zones) | Pink LEDs, nuzzles up into your hand, happy wiggle |
| **Tickle the back of the head** | Green flash + giggly double-wiggle |
| **Walk up close** | Notices you and greets — perks up and nods hello |
| **Wave 👋** at its nose (3 quick near/far swings) | Wakes, waves back with its head, happy face, warm flash |
| **Boop 👉** (a finger right up to the nose sensor) | Love-eyes + a happy nod |
| **Turn its head by hand** | Startled wide eyes (x_x)… then it decides it liked it |
| **Plug in the charger** (while awake) | "Nom, electricity!" — happy face + a green flash |
| Room goes **dark / bright** | Falls asleep / wakes up (toggleable) |
| **Swipe ⬇** | Status bar: clock · date · Wi-Fi bars · battery % + time-left · **volume slider** · **LOCAL** button · amber ⬆ arrow when a firmware update is available |
| **Swipe ⬅ / ➡** | Cycles: face → card 1 → card 2 → card 3 → **GAMES** → **VITALS** |
| **Tap a row on a card** | Controls that HA entity right from the robot — toggles lights/switches, presses buttons, runs scripts & scenes (up to 4 rows per card) |
| **Swipe ⬆** | Back to the face |
| **LOCAL** button (on the status bar) | Toggles local-only mode — nothing in or out of your LAN |
| The **official ESP-NOW remote** | Joystick steers the head; button **B** = talk (set the remote's channel to your router's Wi-Fi channel) |

## ✨ What's inside — feature map

**On the robot** (the dravix ESPHome firmware):

| Feature | What it is | How to use / turn on |
|---------|-----------|----------------------|
| 🐣 Pet face | Drawn animated eyes/cheeks/mouth — blinks, looks around, squints when happy | Always on; expressions via HA `select` / dashboard / the AI's emotion tags |
| 🎭 7 modes | `awake · morning · focus · quiet · night · busy · sleep` — each changes face, LEDs, volume, behaviour | Mode chips on the dashboard Home tab, or the `Mode` select in HA |
| 🗣️ Voice + speech bubble | On-device wake word → HA Assist (STT/LLM/TTS); listening is a **face** (big curious eyes, no label), replies pop in a **comic bubble** at the top with a tail to the mouth | "Okay, Nabu" or tap the face; swap the wake word in the tiny file |
| 🌬 Breathing + body language | The face rises/settles on a slow sine while idle, sways in tiny moves while talking; truly random idle glances | Always on; fully still in calm modes (Body language toggle) |
| 👋 Wave & 👉 boop gestures | Wave at the nose sensor → it waves back; a finger right at the sensor → love-eyes + a nod | Just do it (proximity sensor) |
| 🫨 Hand-turn reaction | Physically turn its head → startled wide eyes, then it warms up to it | Just do it |
| 🕹️ Games arcade | **Catch Me · Reaction · Simon · Rock-Paper-Scissors · Flappy · Party** | Swipe to **GAMES**, tap a game (Party also has an HA button) |
| 💗 Vitals screen | The robot's live needs as bars (energy/food/fun/calm) | Swipe to **VITALS**; care actions on the dashboard **Life** tab |
| 🗂 3 interactive cards | Any HA entities you pick — and up to 4 **tappable rows** per card: tap to toggle/press/run scripts, scenes, automations, the AC | Dashboard → **Screens**: pick entities per card; tap rows on the robot |
| 🔊 Volume slider | A real slider on the status bar — drag it; it live-mirrors the actual speaker volume | Swipe ⬇ (matching slider on the dashboard Home tab) |
| 🔒 Privacy mode | Mic dead on-device + camera endpoints blocked; red PRIVACY badge | Toggle on the dashboard Home tab or the HA switch |
| 🏠 Local-only (isLocal) | *Your* master choice: everything stays inside the home network | **LOCAL** button on the robot, dashboard Settings, or the HA switch — all synced |
| 🔋 Real battery gauge | Level + charging straight from the **AXP2101** fuel gauge (hardware charging flag), time-left estimate, sleep-breathing LEDs on the charger; raw W/mA from the INA226 live in HA | Swipe ⬇ — % + bar + time-left on the status bar |
| 📡 IR blaster + receiver | The robot controls your AC (a ready `Default AC` climate entity) and glances over, curious, when anyone uses a TV/AC remote | Pick `climate.*_default_ac` in the dashboard Climate tab |
| 🧍 Presence nearby | A proximity-based "someone is at the desk" sensor for HA (gates wellness tips too) | Automatic — a `binary_sensor` in HA |
| 🎮 Official remote | The M5Stack StackChan ESP-NOW joystick remote | Just use it (match its channel to your router's) |
| 🖼 Alert images | Any camera/Frigate snapshot full-screen on the robot | Set the `Show image URL` text entity (automations) or dashboard camera actions |
| 💡 LED effects | Rainbow / Twinkle / Random on the light bar (Party runs the rainbow) | Dashboard → Home → LED effect buttons, or HA |
| 🧭 Behaviour toggles | Greet-on-approach, sleep-when-dark, blink, idle glances, mood LEDs, tap-to-talk… | Dashboard → Settings → **Robot behaviour** |
| 🆔 Identify / Party / Reboot | Find-my-robot flash · desk disco · restart | HA buttons (also exposed on the dashboard) |
| ⬆️ Update awareness | The robot reports its firmware and shows an amber ⬆ arrow on the status bar when a newer one ships; HA gets a `Firmware update available` sensor | Automatic — updating is still one press: **Install** in ESPHome |

**In the add-on** (the dravix service + dashboard):

| Feature | What it is | Where |
|---------|-----------|-------|
| 🪞 Live face mirror | The robot's face, state and speech mirrored in the browser | **Home** |
| 💬 Chat with memory | Talk to the robot by text; it remembers facts you tell it | **Home** |
| 🕹 Joystick + faces + LEDs | Manual head control, expression picker, LED colours + effects | **Home** |
| 🔊 Volume slider | The speaker volume — always in sync with the robot's own slider | **Home** |
| 📸 Camera view + photo ritual | The robot's camera (blocked while privacy is on); a 📸 button makes it smile for the shot — photos land in the gallery | **Home** |
| 🛡 Security guard mode | Arm it and the robot becomes a guard camera: snapshots every few seconds, a slow head patrol, live remote view/steering, a browsable gallery (day-folders auto-prune) | **Home** → Security |
| ⏲ Kitchen timers | Quick 5/10/25/50-min chips, custom label, live countdown — the robot announces when one fires | **Home** |
| 🗂 Cards editor | Choose the HA entities for the robot's 3 interactive screens | **Screens** |
| 💗 Life system | Needs bars, feed/rest/play/calm actions, wellness-nudge toggle + a tips editor (write your own lines) | **Life** |
| ❄ Climate | Control your AC from the same app (including via the robot's own IR) | **Climate** |
| 🧩 Modes manager | Every plugin mode — run/stop, enable/disable, edit each mode's settings live | **Settings** |
| 🏠 Welcome home + 🎁 surprises | Celebration when a person arrives (HA person entity) · spontaneous little delights — wiggles, spins, sneezes (extra sniffly when it's cold outside), a morning stretch | **Settings** → Modes (tune or disable) |
| 🕐 Day schedule | Preset hours → modes (e.g. 07:30 → morning, 23:00 → sleep), optional spoken line per entry | **Settings** |
| 🎂 Birthday | Set MM-DD — once a year it celebrates you: love-eyes, party lights, a greeting | **Settings** |
| 🎭 Personas · 🗣 voice · 🧠 memories | Pick/add/delete personas, TTS voice picker, view/add/delete memories | **Settings** |
| 🤖 Robot name | Name it anything — the AI answers to that name | **Settings** |
| 🏠 Local-only master switch | The isLocal choice with a plain-language explanation | **Settings** |
| 🔌 Auto-wired entities | What discovery found, read-only — nothing to fill in | **Settings** |
| 🎚 Calibration + timers + brightness | Per-axis head invert/centre, screensaver/sleep minutes, screen-brightness slider | **Settings** |
| 🧠 AI provider | HA Assist (default) / Claude / OpenAI / Ollama | **Settings** |
| ⬆️ Updates card | Add-on + firmware versions vs latest, with rollback recipe | **Settings** |
| 💾 Backup & restore | Download / upload all your config as one JSON | **Settings** |
| 🌐 Language | English default, Hebrew built-in, one-file recipe for more (the choice reaches the robot too) | header toggle |

## 🤖 What the robot does (custom firmware)

Re-flashing to the dravix ESPHome firmware makes the StackChan act alive while staying fully
controllable from Home Assistant:

- **A drawn animated pet face** — two big eyes that blink, look around, squint when happy and widen
  when listening, pink cheeks and an animated mouth (a desk creature, not a text face). Every
  expression carries its own mood-LED colour and head pose — sad droops, doubt tilts, angry shakes,
  happy nods.
- **Petting** — touch the head and the sensors fire → pink LEDs, a nuzzle-up and a happy wiggle.
  This also feeds dravix's mood and its **fun/calm** needs.
- **7 on-device modes** — `awake · morning · focus · quiet · night · busy · sleep`, each changing
  the face, LEDs, volume and autonomous behaviour (set from HA or the dashboard). `morning` plays a
  little sunrise scene; `quiet` lowers the speaker; `night` dims everything.
- **Voice** — an on-device wake word, **"Okay, Nabu"**, hands off to HA Assist for STT/LLM/TTS; the
  face follows along (listening → speaking) and the live state, last-heard and last-reply text
  stream to the dashboard.
- **Speech bubble** — a comic bubble at the top of the screen, with a tail pointing to the mouth,
  shows the AI's reply (Hebrew or English) while the animated talking mouth stays fully visible.
  Listening is a **face**, not a label — big curious eyes and an attentive little perk-up.
- **A games arcade** — a **Games** menu on the robot's screen: **Catch Me** (tap the runaway dot),
  **Reaction** (a reflex speed test in milliseconds), **Simon** (the growing colour-sequence memory
  game), **Rock-Paper-Scissors** (it nods when it wins), **Flappy** (slip through the pipes) and
  **Party** (a desk disco).
- **A swipe UI** — swipe **down** for a slim status-bar overlay (clock · date · Wi-Fi bars ·
  battery % + time-left · a draggable **volume slider** · the **LOCAL** button · an amber ⬆ arrow
  when a firmware update is available), and **left/right** through 3 **interactive cards** (you
  choose the HA entities on each from the dashboard; tap a row to toggle/press/run it), the
  **Games** arcade and the **Vitals** page — plus a full-screen alert-image page for Frigate /
  doorbell snapshots.
- **Privacy mode** — kills the microphone on-device (wake word + voice pipeline stopped) and shows a
  red **PRIVACY** badge; dravix additionally blocks the camera stream/snapshot.
- **Head calibration** — the head servos are driven and calibrated per-axis from the dashboard.
- **Battery** — the real level + charging flag straight from the AXP2101 fuel gauge (the same
  source the original firmware uses), with an estimated time-left on the status bar — and dim
  sleep-breathing LEDs while it snoozes on the charger.

## 💗 A robot with a life

dravix gives the StackChan real **needs**, like a little Tamagotchi — **⚡ energy · 🍎 food ·
😄 fun · 🧘 calm**, each 0–100, shown as live bars both on the robot's own **VITALS** screen and on
the dashboard. They drift down over time and you top them up — **feed · rest · play · calm** — with
real feedback (it "eats", yawns, wiggles, LEDs). Petting and talking to it feed the needs too.

- **It looks after itself.** When a need bottoms out, the robot acts on its own — goes to sleep
  until it's rested and wakes back up, feeds itself, cheers itself up.
- **Wellness nudges for you.** While you work next to it, the robot reminds *you* to take care of
  yourself — eye breaks (the **20-20-20** rule), stand up and move (~every 30 min), hydrate,
  posture — appearing on its screen with a little wiggle so you notice. Toggle them from the
  dashboard.
- **A hard do-not-disturb rule.** In `focus`, `quiet`, `night`, `busy` and `sleep`, the life system
  and the nudges go **completely silent** — no autonomy, no reminders, nothing on-screen. Needs
  still tick down quietly in the background, but the robot does nothing on its own until it's back
  to `awake`.

## 📱 Web dashboard

The add-on ships a **bilingual (English default · עברית RTL built-in), mobile-friendly** dashboard: a live mirror of the robot's
face, chat with memory, mode switching, games & emotes, a head joystick, volume, the privacy
toggle, a camera view + security guard + photo gallery, kitchen timers, the cards editor, the
**Life** page (feed · rest · play · calm + the wellness tips), climate control, and Settings —
modes manager, personas/voice/memories, day schedule, birthday, auto-wired entities (read-only),
per-axis head calibration, brightness, updates and backup/restore.

|  Home  |  Screens  |  Settings  |
|:------:|:---------:|:----------:|
| ![Home dashboard](dravix-home.png) | ![Screens editor](dravix-screens.png) | ![Settings](dravix-settings.png) |
| Face, modes, chat, games | Choose each card's entities | Auto-wired entities & calibration |

## 🧩 Modes (plugins)

Beyond the on-device firmware modes above, dravix runs **plugin modes** — orchestration behaviours
that combine the robot, the AI router and Home Assistant. Foreground modes are mutually exclusive;
ambient modes run alongside them.

| Mode | Kind | What it does |
|------|------|--------------|
| `focus` | foreground | Calm work companion — quiet face, dim LEDs, gentle reactions while you work. |
| `pomodoro` | foreground | Work/break timer; announces phase changes and shows time on the face & LEDs. |
| `companion` | foreground | Chatty desk buddy; greets via the AI router and emotes from the reply's tone. |
| `guard` | foreground | Desk sentry; reacts to Home Assistant motion/presence/door events with an alert. |
| `dnd` | foreground | Do Not Disturb / meeting mode — calm "busy" face, dim LEDs, stays quiet. |
| `dance` | foreground | A little dance — bobs the head through a sequence and cycles the LED colours. |
| `frigate_watch` | foreground | On a Frigate detection, shows that camera on the robot's screen. |
| `follow` | foreground | Head tracks a person in real time from Frigate detections — off-device, no load on the robot. See [docs/frigate.md](docs/frigate.md). |
| `security` | foreground | Guard camera — periodic snapshots to a browsable gallery, a slow head patrol, live remote view/steering from the dashboard. |
| `welcome` | ambient | Welcome-home celebration — an HA person arrives → perks toward the door, love-eyes, green LEDs, greets out loud. |
| `surprises` | ambient | Spontaneous little delights every hour or two — wiggles, spins, sneezes (frequent when it's cold outside), a morning stretch, "nom, electricity!" on plug-in. |
| `ambient_idle` | ambient | Subtle glances and blinks so the robot never looks frozen. |
| `daynight` | ambient | Sleepy face + warm dim LEDs at night, neutral by day. |

Add your own by dropping a `plugins/<name>/plugin.yaml` + a `Mode` subclass — full guide in
[docs/plugins.md](docs/plugins.md). Every mode is managed live from the dashboard's **Modes
manager** (Settings): run/stop, enable/disable and per-mode settings — or via the
`/api/config/*` endpoints; everything persists across restarts (no redeploy).

## 🎭 Personality (the "desk robot" bit)

Inspired by EMO / Vector. A persistent **mood** (valence / arousal / affection) drifts over time,
reacts to being talked to, petted, motion and night, and shows on the robot's face. It survives
restarts. Plus a library of named **emotes** (happy, love, fistbump, curious, eat, yawn, calm, yes/
no…), a no-code **reactions** engine (event → action rules) and an **announce** endpoint. Full
guide: [docs/personality.md](docs/personality.md).

```bash
curl localhost:8800/api/vitals                                       # energy/food/fun/calm
curl -X POST localhost:8800/api/vitals/action -d '{"action":"feed"}' # feed it
curl -X POST localhost:8800/api/robot/interact -d '{"kind":"pet"}'   # pet it
curl -X POST localhost:8800/api/robot/emote    -d '{"name":"fistbump"}'
curl -X POST localhost:8800/api/timer -d '{"seconds":300,"label":"tea"}'   # timers + daily schedule
```

## 🧠 Switch the AI brain

The AI router is pluggable. The default provider is **Home Assistant Assist** (your host already
runs STT/LLM/TTS). Set the add-on's `ai_provider` (or `DRAVIX_AI_PROVIDER`) to switch —
`ha_assist | claude | openai | ollama` — with the matching `DRAVIX_*_MODEL` (see `.env.example`).
Replies may start with an emotion tag like `(happy)`, which dravix parses to drive the face
automatically.

## 🔌 Drive it from an AI agent (MCP server)

dravix-os exposes its **own** MCP server, so any MCP client (Claude Desktop / Code, etc.) can drive
the robot, modes and your home through one surface:

```bash
cd core && python -m dravix.mcpserver      # stdio MCP server
```

Tools include robot control (`robot_say`, `robot_set_face`, `robot_move_head`, `robot_set_leds`),
mode control (`list_modes`, `activate_mode`, `deactivate_mode`, `get_status`), AI `chat`, and a full
Home Assistant control suite (entities, services, scenes, lights, climate, media, locks, covers,
fans, alarm, vacuum) plus weather / agenda / memory helpers.

## 📷 Cameras & Frigate

dravix-os integrates with **Frigate** both ways, all on your LAN:

- **Show a Frigate camera on the robot's screen** — on a person/motion/door detection, the robot
  displays that camera and looks alert (the `frigate_watch` mode).
- **Feed the robot's own camera into Frigate** — dravix re-serves it as a standard HTTP camera that
  Frigate can run detection on.
- **Follow mode** — with the robot's camera tracked in Frigate, the `follow` mode makes the head
  track a person in real time, entirely off-device.

See [docs/frigate.md](docs/frigate.md). For copy-paste Home Assistant `rest_command`s and
automations, see [docs/home-assistant.md](docs/home-assistant.md).

## 🤖 Robot as a status lamp for an AI agent

Run an AI coding agent on your PC (**Claude Code**, Cursor, a CI job…) and the StackChan
shows you what it's doing at a glance — **working** 🔵, **waiting for your approval** 🟠
(it says so out loud), **has a question** 🟣, **done** 🟢, **error** 🔴. It's one POST to
`/api/agent/status`; ready-made Claude Code hooks + a fail-quiet bridge live in
`deploy/agent-bridge/`. LAN-only, so it respects isLocal. Guide:
[docs/agent-bridge.md](docs/agent-bridge.md).

## 🛠 Development

No robot or Home Assistant required — the **mock** driver logs calls instead of moving real
hardware, so you can develop the dashboard, modes and AI fully offline. It's the default driver.

```bash
cd core
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m dravix                # runs on :8800 with the mock driver — no robot/HA needed
python -m pytest -q             # offline test suite
```

Configure the real driver + entities via `.env` (see `.env.example`) for local runs, or via the
add-on **Configuration** when deployed. The React dashboard lives in `web/` (`npm run dev`, proxies
the API to the Python core on :8800).

**Backup / restore** all your config (personas, routines, memories, schedule, reactions, voices):
`GET /api/export` downloads it, `POST /api/import` restores it.

## 🗂 Repository layout

| Path | What |
|------|------|
| `core/` | The dravix service (Python / FastAPI): DAL + drivers, mode engine, AI router, personality, vitals, MCP client + server, REST/WebSocket API |
| `plugins/` | Drop-in modes — each a `plugin.yaml` + a `Mode` subclass |
| `web/` | The React / Vite dashboard (Hebrew RTL), built into the add-on image |
| `deploy/esphome/stackchan-dravix.yaml` | The custom StackChan **ESPHome firmware** |
| `deploy/` | Dockerfile + packaging for the add-on image |
| `dravix_os/` | The Home Assistant **add-on** wrapper (`config.yaml`, `run.sh`) |
| `docs/` | Setup guides, architecture, ESPHome flashing, Frigate |
| `vendor/` | Upstream `m5stack/StackChan` — reference only, never patched |

See [docs/architecture.md](docs/architecture.md) for the layered design and Device Abstraction
Layer in detail.
