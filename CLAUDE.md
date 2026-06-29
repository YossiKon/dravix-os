# CLAUDE.md — working notes for dravix-os

## What this is
A **companion OS layer** for the M5Stack StackChan robot. It does **not** replace the robot's
stock firmware — it runs next to Home Assistant (on the user's Proxmox host, in its own LXC)
and controls the robot from outside. See [README.md](README.md) and
[docs/architecture.md](docs/architecture.md).

## Golden rules
- **Never fork/patch the robot firmware.** dravix-os layers *beside* it. Upstream
  `m5stack/StackChan` is reference-only under `vendor/`.
- **Discovery-first.** Don't hard-code robot MCP tool names or HA entity ids. Run
  `core/scripts/discover.py`, read `docs/capability-report.md`, build against what's real.
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
