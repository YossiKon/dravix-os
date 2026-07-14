# dravix-os — Home Assistant add-on

Run dravix-os **inside Home Assistant** (HAOS / Supervised), managed from the add-on store, with
options set in the HA UI and state persisted in `/data`. dravix-os drives the StackChan robot
through **Home Assistant entities** exposed by the custom **dravix ESPHome firmware** you flash to
the robot (see [../docs/esphome-local-control.md](../docs/esphome-local-control.md)). Everything is
local — the add-on talks only to your Home Assistant.

## Install (via custom repository)

1. Home Assistant → **Settings → Add-ons → Add-on Store**.
2. Top-right **⋮ → Repositories**, paste:
   ```
   https://github.com/YossiKon/dravix-os
   ```
   **Add**, then close.
3. The **dravix-os** add-on appears in the store. Open it → **Install** (a prebuilt image is
   pulled from GHCR — no long build on your box).
4. **Start** the add-on. It's **zero-config**: with `homeassistant_api` on, the add-on reaches HA
   with the Supervisor's own token and **auto-discovers** the robot's entities by name — you don't
   need to create a token or map anything. Open the **Dravix** panel in the HA sidebar (ingress),
   the add-on's **Open Web UI**, or `http://<ha-host>:8800`.

> First, flash the robot with the dravix ESPHome firmware (once) — see the main
> [README](../README.md) walkthrough. Without it there are no entities to discover and the add-on
> falls back to a mock robot.

## Options

All optional — the defaults work for a standard install.

| Option | What |
|--------|------|
| `robot_driver` | `ha` (the supported driver; drives the robot through HA entities) |
| `robot_entity_*` | Optional manual overrides (face / head_yaw / head_pitch / media_player / tts / light / camera). **Leave blank for auto-discovery.** |
| `ha_url` / `ha_token` | Leave **both blank** for zero-config (Supervisor proxy + token). Fill only for a non-standard setup. |
| `ai_provider` | `ha_assist` (local HA Assist pipeline, default) / `claude` / `openai` / `ollama` |
| `language` | `en` / `he` — language for server-generated speech (the dashboard has its own live toggle) |
| `robot_rtl_fix` | Reorder Hebrew to visual order for the robot's screen (it has no BIDI). Leave on. |
| `idle_motion` | dravix's own idle head glances. **Off by default** — the firmware already glances on its own. |
| `local_only` | Seeds the dashboard's **isLocal** toggle on the first run only (then the toggle is your explicit choice). ON = nothing leaves your LAN. |
| `frigate_url` / `frigate_camera` | Optional Frigate integration (person detection → the robot glances / shows a snapshot; face-recognition greetings). |
| `log_level` | DEBUG / INFO / WARNING / ERROR |

## Updating

- **The add-on**: bump the `version` in `config.yaml` (or take a released update) → the add-on page
  shows an **Update** button. HA pulls the new GHCR image.
- **The robot firmware** is separate: it updates through the **ESPHome** add-on's **Install** on the
  robot's config (the dashboard's *Updates* card tells you when a newer firmware ships with the
  add-on). Updating the add-on never reflashes the robot.

## Notes

- State (store, mood, schedule, reactions, personas, memory, people) persists in the add-on's
  `/data` and survives restarts/updates.
- Prefer isolation from HA, or running HA as a VM? The dedicated **LXC + Docker Compose** path
  ([../deploy/README.md](../deploy/README.md), [../docs/proxmox-lxc-setup.md](../docs/proxmox-lxc-setup.md))
  runs the same service in a separate container (also against the `ha` driver).
