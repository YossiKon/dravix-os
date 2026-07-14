# CLAUDE.md — working notes for dravix-os

## What this is
A **companion OS** for the M5Stack StackChan robot. The robot is flashed with our own **dravix
ESPHome firmware** (`deploy/esphome/stackchan-dravix.yaml`), which exposes it as Home Assistant
entities; dravix-os is delivered as a **Home Assistant add-on** and drives the robot through those
HA entities (the `ha` driver). Ships next to Home Assistant, all local. (A Proxmox-LXC + Docker
Compose deployment is an alternative, but the HA add-on is the primary path.) See
[README.md](README.md) and [docs/architecture.md](docs/architecture.md).

## Golden rules
- **Don't fork/patch M5Stack's upstream firmware.** Our firmware is a fresh ESPHome config that
  layers on the M5Stack ESPHome **BSP** (pinned under `packages:`); upstream `m5stack/StackChan`
  is reference-only under `vendor/`. Never edit the BSP in place — extend beside it.
- **Discovery-first.** Don't hard-code HA entity ids. Auto-discovery (`core/dravix/discovery.py`,
  suffix-anchored) maps the robot's entities at startup; build against what's discovered. The
  legacy MCP driver + `core/scripts/discover.py` remain for non-HA backends.
- **Everything is pluggable** behind interfaces: robot drivers (`core/dravix/dal/`), AI
  providers (`core/dravix/ai/`), modes (`plugins/`). Higher layers depend only on the
  `RobotController` facade — never a driver directly.
- Robot actions in modes must be **capability-guarded** (`robot.supports(CAP_*)`) so they
  degrade gracefully across backends (mock / partial HA / full MCP).

## Layout
- `core/dravix/` — the service. `dal/` (drivers), `ai/`, `modes/` (engine), `integrations/`
  (MCP client, HA client), `mcpserver/` (our MCP server), `api/routes.py`, `app.py`.
- `core/scripts/discover.py` — capability discovery (run first).
- `plugins/<name>/` — modes (`plugin.yaml` + a `Mode` subclass).
- `web/` — React dashboard (Vite). `core/dravix/web/static/` — built-in fallback page.
- `deploy/` — Dockerfile, compose. `docs/proxmox-lxc-setup.md` — deployment.

## Commands (run from `core/`, venv at `core/.venv`)
```bash
pip install -e ".[dev]"          # install
python -m dravix                 # run service on :8800  (DRAVIX_* env / .env)
python scripts/discover.py       # probe robot MCP URL + HA -> docs/capability-report.md
python -m dravix.mcpserver       # run our MCP server over stdio (for Claude/agents)
python -m pytest -q              # tests (offline, mock driver)
python -m compileall -q dravix scripts tests   # quick syntax check
```
Top-level `make help` lists the same via the Makefile.

## Config
All via `DRAVIX_*` env vars / `.env` (see `.env.example`). Key ones:
`DRAVIX_ROBOT_DRIVER` (mcp|ha|mock), `DRAVIX_ROBOT_MCP_URL`, `DRAVIX_HA_URL`,
`DRAVIX_HA_TOKEN`, `DRAVIX_AI_PROVIDER` (ha_assist default).

## Conventions
- Python 3.11+, FastAPI, async throughout. Optional deps (`mcp`) are imported lazily so the
  mock path runs without them.
- Tests must stay offline (use `MockDriver`); never require a live robot or HA.
