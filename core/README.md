# dravix-os — the service

The Python half of [dravix-os](https://github.com/YossiKon/dravix-os): a FastAPI service that
drives an M5Stack StackChan robot through the Home Assistant entities the dravix ESPHome
firmware publishes, and serves the dashboard that controls it.

It ships as a Home Assistant add-on; this package is what runs inside it.

```bash
pip install -e ".[dev]"     # install (Python 3.11+)
python -m dravix            # run the service on :8800  (configure with DRAVIX_* env vars)
python -m dravix.mcpserver  # expose dravix's tools to an MCP client over stdio
python -m pytest -q         # tests — fully offline, no robot and no Home Assistant needed
```

Layout: `dravix/dal/` robot drivers · `dravix/ai/` AI providers · `dravix/modes/` the mode
engine (modes themselves live in the repository's top-level `plugins/`) · `dravix/integrations/`
Home Assistant and Frigate clients · `dravix/mcpserver/` dravix's own MCP server ·
`dravix/api/routes.py` the REST + WebSocket API.

See the [main README](https://github.com/YossiKon/dravix-os#readme) for what the robot actually
does, and `docs/architecture.md` for how the pieces fit together.
