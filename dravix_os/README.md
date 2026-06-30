# dravix-os — Home Assistant add-on

Run dravix-os **inside Home Assistant** (HAOS / Supervised), managed from the add-on store, with
options set in the HA UI and state persisted in `/data`. The robot's stock firmware is never
touched — dravix-os only talks to it over the MCP URL it already publishes.

## Install (one-click, via custom repository)

1. Home Assistant → **Settings → Add-ons → Add-on Store**.
2. Top-right **⋮ → Repositories**, paste:
   ```
   https://github.com/YossiKon/dravix-os
   ```
   **Add**, then close.
3. The **dravix-os** add-on appears in the store (under "dravix-os add-ons"). Open it → **Install**.
   The first build clones the repo + builds the dashboard, so it takes a few minutes.
4. **Configuration** tab — set at least:
   - `robot_mcp_url` → the MCP URL your robot publishes (leave blank to test with the mock driver)
   - `ha_token` → a HA long-lived access token (Profile → Long-Lived Access Tokens → Create)
   - `ha_url` defaults to `http://homeassistant:8123` (the supervisor network) — usually leave it.
5. **Start** the add-on, then **Open Web UI** (or `http://<ha-host>:8800`).

## Options

| Option | What |
|--------|------|
| `robot_mcp_url` | The MCP URL the robot publishes (blank → mock driver) |
| `robot_mcp_transport` | `auto` / `streamable_http` / `sse` |
| `ha_url` / `ha_token` | Reach Home Assistant (token = long-lived access token) |
| `ai_provider` | `ha_assist` (local pipeline) / `claude` / `openai` / `ollama` |
| `local_only` | Refuse cloud AI providers (default true) |
| `frigate_url` / `frigate_camera` | Optional Frigate integration |
| `log_level` | DEBUG / INFO / WARNING / ERROR |

When `robot_mcp_url` is set the add-on uses the real **mcp** robot driver; blank → the **mock**
driver (so you can try the dashboard before wiring the robot).

## Updating

Bump the add-on `version` (or push a new commit and re-check the store) → the add-on page shows an
**Update** button. Updating dravix-os has **zero** effect on the robot's stock features — those
update separately through M5Stack's app/OTA.

## Notes

- State (store, mood, schedule, reactions, personas, memory) persists in the add-on's `/data`.
- Prefer isolation from HA, or running HA as a VM? The dedicated **LXC + Docker Compose** path
  ([../deploy/README.md](../deploy/README.md), [../docs/proxmox-lxc-setup.md](../docs/proxmox-lxc-setup.md))
  is the alternative — same service, separate container.
