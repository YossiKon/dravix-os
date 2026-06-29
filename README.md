# dravix-os

A custom "OS layer" for the **M5Stack StackChan** desktop robot.

dravix-os does **not** replace the robot's original firmware. The stock firmware (app,
camera head-tracking, dance, security/guard, agent mode) stays **100% intact** and keeps
receiving M5Stack OTA updates. dravix-os is a **companion brain** that runs next to your
Home Assistant and drives the robot from the outside — adding custom *modes*, a *web
dashboard*, a pluggable *AI router*, and deep *smart-home* integration.

```
┌─────────────────────────┐        ┌──────────────────────────────────────────┐
│   Robot (CoreS3)         │        │     Proxmox host (always on)              │
│   stock firmware — kept! │        │  ┌─────────────┐   ┌────────────────────┐ │
│   face · servos · audio  │◄──────►│  │  HA (VM)    │◄─►│  dravix-os (LXC)   │ │
│   camera · touch · LEDs  │  MCP   │  │ Assist + MCP│   │  core + dashboard  │ │
└─────────────────────────┘        │  └─────────────┘   └────────────────────┘ │
        the body                    └──────────────────────────────────────────┘
                                            the brain + control panel
```

## Why a companion OS (and not a firmware fork)

The CoreS3 is an ESP32-S3 microcontroller — it physically cannot host an LLM, speech
recognition, or a real management UI. Even today, the robot's "intelligence" already runs
off-device (M5Stack cloud / phone app / Home Assistant). So dravix-os puts the custom brain
where it belongs — on an always-on host — and talks to the robot over the interfaces it
already exposes.

Concretely: the robot exposes an **MCP server at a URL**. Home Assistant connects to it as
an MCP client today. dravix-os connects to that **same MCP URL** to control the robot, to
**Home Assistant's MCP server** to control the smart home, and exposes **its own MCP
server** so any agent (e.g. Claude) can drive modes + robot + home.

## Core principles

1. **Layer, not fork.** We never edit the stock firmware. Upstream M5Stack updates flow to
   the robot untouched. `m5stack/StackChan` is tracked under `vendor/` for reference only.
2. **Everything is pluggable.** Robot drivers, AI providers, and modes are all swappable
   plugins behind clean interfaces (the [Device Abstraction Layer](docs/architecture.md)).
3. **Preserve + extend.** The dashboard manages both the original behaviors *and* the new
   ones, without harming the originals.

## Repository layout

| Path | What |
|------|------|
| `core/` | The dravix-os service (Python / FastAPI): DAL, mode engine, AI router, MCP client+server, REST API |
| `core/scripts/discover.py` | **Run this first** — probes your robot's MCP URL + HA and writes a capability report |
| `plugins/` | Drop-in modes/behaviors (example included) |
| `web/` | Management dashboard (React) — *Phase 2* |
| `deploy/` | Dockerfile, docker-compose, Proxmox LXC setup |
| `vendor/` | Upstream `m5stack/StackChan` tracking (reference only) |
| `docs/` | Architecture, setup guides, generated capability report |

## Quick start (dev)

```bash
cd core
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

cp ../.env.example ../.env                      # then fill in robot + HA details
python -m dravix                                # starts the service on :8800
```

Open http://localhost:8800 for the status page.

Before anything talks to the real robot, run discovery:

```bash
python scripts/discover.py        # writes docs/capability-report.md
```

## Modes (plugins)

Modes are drop-in plugins under `plugins/`. Shipping now:

| Mode | Kind | What it does |
|------|------|--------------|
| `focus` | foreground | Calm work companion — quiet face, dim LEDs |
| `pomodoro` | foreground | Work/break timer; announces phases, colors the LEDs |
| `companion` | foreground | Chatty buddy; greets via the AI router, emotes from the reply's tone |
| `guard` | foreground | Desk sentry; reacts to HA motion/presence events with an alert |
| `dnd` | foreground | Do Not Disturb / meeting mode — calm busy face, stays quiet |
| `dance` | foreground | A little head-bob + LED color cycle |
| `frigate_watch` | foreground | On a Frigate detection, shows that camera on the robot's screen |
| `ambient_idle` | ambient | Subtle glances/blinks so the robot never looks frozen |
| `daynight` | ambient | Sleepy face + warm dim LEDs at night, neutral by day |

Add your own by creating `plugins/<name>/plugin.yaml` + a `Mode` subclass — full guide in
[docs/plugins.md](docs/plugins.md). Foreground modes are mutually exclusive; ambient modes run
alongside. Per-mode config, enable/disable, and the AI provider are editable at runtime via the
`/api/config/*` endpoints and persist to `data/store.json` (no redeploy).

## Drive it from an AI agent (MCP server)

dravix-os exposes its **own** MCP server so any MCP client (Claude Desktop/Code, etc.) can
control the robot + modes:

```bash
cd core && python -m dravix.mcpserver      # stdio MCP server
```

Tools: `robot_say`, `robot_set_face`, `robot_move_head`, `robot_set_leds`, `list_modes`,
`activate_mode`, `deactivate_mode`, `get_status`, and `chat` (when an AI provider is set).

## Personality (the "desk robot" bit)

Inspired by EMO / Vector. A persistent **mood** (valence/arousal/affection) drifts over time,
reacts to being talked to / petted / motion / night, and **shows on the robot's face when idle**
(a foreground mode keeps the face while active). It survives restarts. Plus a library of named
**emotes** (happy, love, fistbump, curious, yes/no…) and a no-code **reactions** engine (event →
action rules) and an **announce** endpoint. Full guide: [docs/personality.md](docs/personality.md).

```bash
curl localhost:8800/api/mood                                   # current mood
curl -X POST localhost:8800/api/robot/interact -d '{"kind":"pet"}'   # pet it
curl -X POST localhost:8800/api/robot/emote   -d '{"name":"fistbump"}'
curl -X POST localhost:8800/api/timer -d '{"seconds":300,"label":"tea"}'   # timers + daily schedule
```

## Local-first & cameras

dravix-os runs **fully local** — `DRAVIX_LOCAL_ONLY=true` (default) refuses cloud AI providers,
and nothing phones home (no M5Stack/other cloud). See [docs/local-only.md](docs/local-only.md).

It also integrates with **Frigate** both ways — show a Frigate camera on the robot's screen, and
re-serve the robot's own camera as an HTTP camera Frigate can detect on. See
[docs/frigate.md](docs/frigate.md).

**Easy Home Assistant integration** — copy-paste `rest_command`s + automations (announce, notify,
agenda, run a routine, show a camera) and the built-in HA event bridge. See
[docs/home-assistant.md](docs/home-assistant.md).

## Switch the AI brain

The AI router is pluggable. Default is **Home Assistant Assist** (your host already runs it).
Set `DRAVIX_AI_PROVIDER` to switch — `ha_assist | claude | openai | ollama` — and the
matching `DRAVIX_*_MODEL` (see `.env.example`). For a robot that chats a lot, `claude-haiku-4-5`
(fast/cheap) or `claude-sonnet-4-6` (balanced) are good Claude picks. Replies may start with an
emotion tag like `(happy)` — dravix parses it to drive the face automatically.

## Status

- **Phase 0–1 (foundation)** ✅ — runnable core, Device Abstraction Layer (MCP / HA / mock
  drivers), capability discovery, deploy scaffolding.
- **Phase 2–3** ✅ — mode engine with ambient + tick scheduling, 5 modes, live WebSocket event
  stream, persona/emotion parsing, and a React dashboard (`web/`).
- **Phase 4** ✅ — pluggable AI router (HA Assist + Claude + OpenAI + Ollama) and the dravix
  MCP server.
- **Phase 5** ◑ — Home Assistant **event bridge** (motion/presence/door → `guard` & reactions)
  built; rich automations next.
- **Phase 6** ◑ — extension SDK: persistent store, runtime config API, plugin docs, CI.
- **Next (needs hardware)** — point the `mcp` driver at the real robot: run discovery, then we
  finalize the mapping and prove face/head/speech on the physical StackChan.

**Backup / restore** all your config (personas, routines, memories, schedule, reactions, voices):
`GET /api/export` downloads it, `POST /api/import` restores it.

Everything above is verified end-to-end on the mock driver. See
[docs/architecture.md](docs/architecture.md) for the full roadmap.
