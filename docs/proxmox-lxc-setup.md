# Running dravix-os on Proxmox (next to Home Assistant)

Your Home Assistant runs as a VM on Proxmox. dravix-os should live in its own **LXC
container** on the same Proxmox host: isolated, lightweight, always-on, and snapshot-backed.

## 1. Create a Debian 12 LXC

In the Proxmox web UI → **Create CT**:

- Template: `debian-12-standard`
- Disk: 8 GB · CPU: 2 cores · RAM: 1024 MB (plenty for the service)
- Network: bridged (`vmbr0`), same LAN as the HA VM and the robot
- Unprivileged container: **yes**
- Enable nesting (needed for Docker): **Options → Features → Nesting = 1**

Start the container and open its console (or SSH in).

## 2. Install Docker

```bash
apt update && apt install -y curl git
curl -fsSL https://get.docker.com | sh
```

## 3. Deploy dravix-os

```bash
git clone <your dravix-os repo> /opt/dravix-os
cd /opt/dravix-os
cp .env.example .env
nano .env          # set DRAVIX_ROBOT_MCP_URL, DRAVIX_HA_URL, DRAVIX_HA_TOKEN, ...
docker compose -f deploy/docker-compose.yml up -d --build
```

Browse to `http://<lxc-ip>:8800`.

## 4. First run: discover capabilities

```bash
docker compose -f deploy/docker-compose.yml exec dravix-os python scripts/discover.py
```

This writes `docs/capability-report.md` (persisted to the host via the compose volume). Use
it to set `DRAVIX_ROBOT_DRIVER=mcp` and confirm the verb→tool mapping, then restart.

## 5. Networking notes

- The LXC reaches **Home Assistant** at its VM IP (`http://<ha-ip>:8123`) and the **robot's
  MCP URL** over the LAN — the same URL you already point HA at.
- Get a HA **long-lived access token**: HA → your profile → *Long-Lived Access Tokens*.
- If you enabled HA's **MCP Server** integration, set `DRAVIX_HA_MCP_URL` to
  `http://<ha-ip>:8123/mcp_server/sse` so dravix-os can also drive the smart home over MCP.

## 6. Backups

Snapshot the LXC from Proxmox before upgrades. The container is stateless apart from `.env`
and `docs/` — both live on the host, so rollbacks are trivial.
