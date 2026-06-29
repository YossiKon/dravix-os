# dravix-os — Architecture

## 1. The big picture

dravix-os is a **companion service** for the M5Stack StackChan robot. The robot keeps its
original firmware; dravix-os runs on the always-on Proxmox host (in its own LXC, next to the
Home Assistant VM) and controls the robot from the outside.

Three MCP relationships sit at the center of the design:

- **dravix-os → robot MCP server.** The robot exposes an MCP endpoint at a URL. dravix-os is
  a client of it (move head, set face, say, LEDs, take photo, listen, …). This is the
  primary robot control path.
- **dravix-os → Home Assistant MCP server.** HA exposes its entities/services as MCP tools.
  dravix-os uses this for smart-home control and context.
- **agents → dravix-os MCP server.** dravix-os exposes its *own* MCP server so an external
  agent (Claude, etc.) can drive modes, the robot, and the home through one surface.

> The exact tool names/transports the robot exposes are discovered at runtime — see
> [§6 Discovery](#6-discovery-phase-0). Nothing is hard-coded against unverified assumptions.

## 2. Layers

```
                         ┌──────────────────────────────────────────────┐
                         │                 Web dashboard                 │  (Phase 2, React)
                         └───────────────┬──────────────────────────────┘
                                         │ REST + WebSocket
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  dravix-os core (FastAPI)                                  │
│                                                                                          │
│   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌──────────────┐  │
│   │ Mode engine│   │  Persona   │   │ AI router  │   │ Event bus  │   │  dravix MCP  │  │
│   │ + plugins  │   │  engine    │   │ (pluggable)│   │            │   │   server     │  │
│   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └──────────────┘  │
│         └────────────────┴────────────────┴────────────────┘                            │
│                                   │                                                       │
│                    ┌──────────────▼───────────────┐                                      │
│                    │   Device Abstraction Layer    │   one interface for "the robot"     │
│                    │   RobotController + drivers    │                                      │
│                    └──────┬───────────┬─────────────┘                                     │
│                  ┌────────▼──┐  ┌──────▼─────┐  ┌──────────┐                              │
│                  │ MCP driver│  │ HA driver  │  │ Mock     │   swappable backends         │
│                  └─────┬─────┘  └─────┬──────┘  └──────────┘                              │
└────────────────────────┼─────────────┼──────────────────────────────────────────────────┘
                          │             │
                   robot MCP URL    Home Assistant (REST/WS/MCP)
```

## 3. Device Abstraction Layer (DAL)

The single most important abstraction. Everything above the DAL talks to **one** interface
(`RobotController`) with verbs like `set_face`, `move_head`, `say`, `set_leds`,
`take_photo`, `listen`, `get_status`. Concrete **drivers** implement that interface:

- `mcp_driver` — talks to the robot's MCP server (primary).
- `ha_driver` — drives the robot through Home Assistant entities/services (fallback / when
  the robot is exposed to HA as ESPHome entities).
- `mock_driver` — logs calls only; for offline development and tests.

Because all higher layers depend only on `RobotController`, we can change *how* the robot is
reached without touching modes, AI, or the dashboard. The driver is chosen by config
(`DRAVIX_ROBOT_DRIVER`).

The DAL exposes a **capability set** (which verbs the active backend actually supports),
populated from discovery, so the UI can gray out what a given firmware can't do.

## 4. Mode engine + plugins

A *mode* is the unit of "cool behavior." Modes are plugins discovered from `plugins/` (and
built-ins). Each mode declares metadata (`plugin.yaml`) and a class implementing the `Mode`
interface: `on_enter`, `on_exit`, `on_event`, and optional `tick`. The engine runs one
*foreground* mode at a time plus any number of *ambient* background behaviors, and routes
events from the event bus to them.

Planned flagship modes: Work/Focus, Pomodoro, Companion-chat, Ambient (idle cuteness),
Guard, Dance, Meeting, Sleep.

## 5. AI router

Pluggable `AIProvider` interface (`converse`, `stream`, tool-use). Default provider =
**Home Assistant Assist** (HA already owns STT/LLM/TTS on your host). Adapters for Claude,
OpenAI, and local/Ollama can be added without touching callers. The persona engine supplies
the system prompt + voice + expression mapping.

## 6. Discovery (Phase 0)

`core/scripts/discover.py` connects to the robot MCP URL and to Home Assistant, lists the
available tools/entities, and writes `docs/capability-report.md`. This is the contract that
drives driver implementation — we build against what the robot *actually* exposes, not
against guesses.

## 7. Upstream tracking ("always be able to update")

`m5stack/StackChan` is added as a git submodule under `vendor/upstream/` (reference only —
we read assets/protocols, we never modify it). `make update-upstream` pulls the latest.
Because dravix-os layers *beside* the firmware rather than patching it, upstream changes
never conflict with our code, and the robot itself updates through M5Stack's normal OTA/app.

## 8. Deployment

- Target: a dedicated **Debian 12 LXC** on Proxmox, next to the HA VM.
- Packaged as a Docker Compose stack (`deploy/`) for portability + easy updates.
- Config via `.env` (robot MCP URL + token, HA URL + token, driver/provider selection).
- Proxmox snapshots provide backup/rollback. See
  [docs/proxmox-lxc-setup.md](proxmox-lxc-setup.md).

## 9. Roadmap

| Phase | Deliverable | State |
|-------|-------------|-------|
| **0** | Repo skeleton, runnable core, **discovery**, deploy scaffolding | ✅ done |
| **1** | DAL + working MCP driver proven against the real robot | ⏳ awaits robot connect |
| **2** | Core kernel hardening (ambient + tick + WebSocket) + React dashboard | ✅ built (mock-verified) |
| **3** | Mode engine + first flagship modes (focus/pomodoro/companion/guard/ambient) | ✅ built (mock-verified) |
| **4** | AI router (HA Assist + Claude + OpenAI + Ollama) + persona + dravix MCP server | ✅ built (mock-verified) |
| **5** | HA event bridge + reactions engine + announce + Frigate (both ways) | ✅ built (mock-verified) |
| **6** | Extension SDK (store, runtime config API, [plugins.md](plugins.md)) + CI + upstream sync | ◑ in progress |
| **+** | Personality: mood engine + emotes + interactions ([personality.md](personality.md)) | ✅ built (mock-verified) |
