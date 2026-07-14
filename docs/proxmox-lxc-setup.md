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
nano .env          # set DRAVIX_ROBOT_DRIVER=ha, DRAVIX_HA_URL, DRAVIX_HA_TOKEN
docker compose -f deploy/docker-compose.yml up -d --build
```

Browse to `http://<lxc-ip>:8800`.

## 4. First run: entity discovery

With `DRAVIX_ROBOT_DRIVER=ha`, dravix-os **auto-discovers** the robot's HA entities (exposed by
the dravix ESPHome firmware) at startup — nothing to map by hand. The service logs the discovered
entity set on boot. (The legacy `scripts/discover.py` probe is only for the non-HA `mcp` driver.)

## 5. Networking notes

- The LXC reaches **Home Assistant** at its VM IP (`http://<ha-ip>:8123`); the robot itself is
  driven **through HA** (the ESPHome firmware exposes it as HA entities), so there's no separate
  robot URL to configure.
- Get a HA **long-lived access token**: HA → your profile → *Long-Lived Access Tokens*.

## 6. Backups

Snapshot the LXC from Proxmox before upgrades. The container is stateless apart from `.env`
and `docs/` — both live on the host, so rollbacks are trivial.
