# dravix-os — Home Assistant add-on

Install dravix-os from Home Assistant's **add-on store** (for HAOS / supervised installs), with
options configured from the HA UI and state persisted in `/data`.

> **Your setup runs HA as a VM on Proxmox.** The recommended deployment there is the dedicated
> **LXC + Docker Compose** path ([../README.md](../README.md), [../../docs/proxmox-lxc-setup.md](../../docs/proxmox-lxc-setup.md))
> — it keeps dravix-os isolated from HA and is easy to update. Use this add-on instead if you'd
> rather manage it from the HA add-on store.

## Install as a local add-on

1. Edit `build.yaml` (and the `ARG` defaults in `Dockerfile`) to point `DRAVIX_REPO` /
   `DRAVIX_REF` at your dravix-os git repo + branch. The image clones the repo at build time, so
   plugins and the dashboard are included — no special build context needed.
2. Copy this `ha-addon/` folder into your HA `/addons/dravix_os/` directory (Samba/SSH add-on),
   renaming it `dravix_os`.
3. Home Assistant → **Settings → Add-ons → Add-on Store → ⋮ → Check for updates**. "dravix-os"
   appears under *Local add-ons*. Install it.

## Configure

In the add-on **Configuration** tab:

| Option | What |
|--------|------|
| `robot_mcp_url` | The MCP URL the robot publishes (blank → mock driver) |
| `ha_url` / `ha_token` | Reach Home Assistant (a long-lived token) |
| `ai_provider` | `ha_assist` (local pipeline) / `claude` / `openai` / `ollama` |
| `local_only` | Refuse cloud AI providers (default true) |
| `frigate_url` / `frigate_camera` | Optional Frigate integration |
| `log_level` | DEBUG / INFO / WARNING / ERROR |

Start the add-on, then open the dashboard at `http://<ha-host>:8800` (or **Open Web UI**).

## Notes

- State (store, mood, schedule, reactions, personas) persists in the add-on's `/data`.
- To pull updates, bump `DRAVIX_REF` / rebuild the add-on (your robot's stock firmware updates
  separately — dravix-os never touches it).
