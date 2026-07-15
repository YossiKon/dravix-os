# Capability report

> **Mostly legacy / optional.** With the supported **`ha` driver**, dravix-os **auto-discovers**
> the robot's Home Assistant entities at startup (`core/dravix/discovery.py`, suffix-anchored) and
> logs them on boot — there's nothing to generate or map by hand. This report + `discover.py` are
> only relevant for the legacy `mcp` (non-HA) driver.

To (optionally) probe an MCP robot's tools + the relevant HA entities:

```bash
cd core && python scripts/discover.py
```

For the `ha` path, just start the add-on and read the boot log's "auto-discovered N robot
entities" line, or **Settings → Robot connection** in the dashboard (the found entities are shown
read-only).
