# Deploying dravix-os

dravix-os runs as a small always-on service. The recommended home is a dedicated **LXC
container on your Proxmox host**, right next to the Home Assistant VM — see
[../docs/proxmox-lxc-setup.md](../docs/proxmox-lxc-setup.md).

## Option A — Docker Compose (recommended)

Inside the LXC (with Docker installed):

```bash
git clone <your dravix-os repo> dravix-os
cd dravix-os
cp .env.example .env      # fill in robot MCP URL + HA URL/token
docker compose -f deploy/docker-compose.yml up -d --build
```

Open `http://<lxc-ip>:8800`. Logs: `docker compose -f deploy/docker-compose.yml logs -f`.

## Option B — bare service (systemd)

```bash
cd core
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
# create /etc/systemd/system/dravix-os.service running:  .venv/bin/python -m dravix
```

## Updating

```bash
git pull
make update-upstream          # optional: refresh vendor/ reference
docker compose -f deploy/docker-compose.yml up -d --build
```

Because dravix-os never touches the robot's firmware, updating the service has zero effect on
the robot's stock features — those update separately through M5Stack's app/OTA.
