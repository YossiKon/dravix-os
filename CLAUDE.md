# CLAUDE.md — working notes for dravix-os

## What this is
**Dravix** is ESPHome firmware that turns the M5Stack **StackChan** (CoreS3) into a cute desk
assistant for **Home Assistant**: an Assist voice satellite with an on-device wake word, an
Emo-like animated face, two screens of the owner's HA controls plus an air-conditioner screen,
reactions (touch, shake, lift, people, light) and games. **The firmware is the product**: no
server, no cloud. Users keep one small device file in the ESPHome add-on that pulls the firmware
from this repo; updating = pressing Install. An optional HA add-on (`dravix_os/`, slug kept from
v1 so old installs just Update) is one ingress page that sets the robot up through HA's API. See [README.md](README.md) and
[docs/firmware.md](docs/firmware.md).

**History:** until 2026-11-27 this repo was the dravix-os add-on (Python service, React
dashboard, MCP server, plugins) with firmware v1 ("fw61"). All of it lives on the `v1` branch
(tag `v0.1.18`); main has none of it. Don't bring it back unless the owner asks.

## Layout
- `deploy/esphome/stackchan.yaml` — the template device file (Wi-Fi + one `packages:` block).
- `deploy/esphome/stackchan-dravix.yaml` — the entry every device file pulls (`ref: main`); it
  `!include`s the modules. **Never move or rename it**: every robot points at this exact path.
- `deploy/esphome/v2/` — the modules: `hardware` (vendored BSP), `components` (driver sources),
  `base` (voice, audio, diagnostics), `face` + `face_tick` (face state machine, 30 fps render,
  LED effect), `behavior` (pads, IMU, proximity, light, night), `screens` (tiles + AC),
  `games` (Games screen, camera games), `modes` (Normal / Busy / Sleep, the menu, the clock, the
  status bar, private mode, the battery). `img/` holds the PNG assets (`make_images.py` draws them).
- `components/` — ESPHome components, served to builds through git **tags** (`components-v3`).
- `docs/` — `index.html` (the GitHub Pages site), `img/` (README and site pictures),
  `firmware.md` (internals), `ha-automations.yaml` + `ha-voice.yaml` (HA automations).
- `dravix_os/` — the add-on: `app/server.py` (aiohttp; finds the robot through the entity
  registry by the ESPHome entity names; `DRAVIX_DEMO=1` serves fake data for working on the page),
  `app/static/index.html` (the page), `Dockerfile`, `config.yaml` (bump `version` for every
  change, or HA never pulls it). `.github/workflows/addon-image.yml` builds and pushes the GHCR
  image on main and `dev-*` (build the image on a dev branch before main announces a version).

## Golden rules
- **Don't fork/patch M5Stack's upstream firmware**; extend beside it. Upstream `m5stack/StackChan`
  is reference-only (`vendor/`). Recorded exceptions, each with a measured defect or a hard
  break, no config-level workaround, every changed line marked `dravix:`, and a README with the
  upstream commit + re-sync steps:
  - `components/ftservo` + `components/scs9009` — the BSP servo driver slept in ESPHome's main
    loop for every head move (`delay(200)` + `delay(travel)`, a 500 ms-per-byte serial
    busy-wait): 1.2 s nods, speaker buffer overflows, dropped microphone audio.
  - `deploy/esphome/v2/hardware.yaml` — the BSP file itself (commit 238ba98): ESPHome 2026.11
    rejects M5Stack's `github://…/components` package source form at load time.
  - `components/m5ioe1` — the addressable-light API changed in ESPHome 2026.11; version-gated patch.
  To take a BSP update: copy upstream over the file/folder, re-apply the `dravix:` lines, tag.
- **One owner per thing.** The face: `g_face` / `face_set` / the render tick — nothing else
  touches the face widgets. Sound: everything goes through `play_sfx` (mic and speaker share one
  I2S bus and the wake word holds it 24/7; never `rtttl.play` directly).
- **No servo writes while it listens or speaks** (servo traffic starved the mic and overflowed the
  speaker buffer — measured with the old blocking driver). The one move in a voice turn is the
  Normal-mode perk-up at the wake word, before the session opens (it overlaps the chime).
- **Modes** live in `modes.yaml`: `mode_set` is the only writer of `g_mode` (0 Normal, 1 Busy,
  2 Sleep = the clock page); `head_to` moves only in Normal (or via `head_home`). Anything HA asks
  for during a voice turn waits in `g_pend_*` and runs from `voice_done` (`pending_run`).
- **Private mode** = `g_private` (restored global): the camera is marked failed at boot (priority
  600, before its setup), every microphone start checks it, toggling restarts the robot. Its
  switch keeps `restore_mode: DISABLED` (a restoring template switch replays its action at boot).
- **English only** on the robot and in the README, site and docs (the owner chats in Hebrew;
  answer in Hebrew).
- **Assets are pinned by tag:** images come from `img-vN` (`img_base` in `base.yaml`),
  components from `components-vN` (`components.yaml`). Changing either = a new tag + bump.
- **Render budget:** no full-screen gradients, watch the widget count (CoreS3 LVGL starves).

## Checks
- `esphome config` validates YAML only; C++ lambdas fail at compile time. CI
  (`.github/workflows/firmware.yml`) compiles main on ESPHome 2026.8.2 and the latest release.
  Job logs need a login, so errors are surfaced as annotations
  (`/repos/YossiKon/dravix-os/check-runs/<job>/annotations`).
- Local validation: a device file with dummy Wi-Fi whose `packages:` `!include`s
  `deploy/esphome/stackchan-dravix.yaml`. A local compile needs PowerShell (ESP-IDF rejects
  MSYS) and lots of RAM: prefer CI.
- Never flash the robot from a dev PC: the real Wi-Fi secrets live in the owner's ESPHome add-on.
