# Image for the Home Assistant add-on — built in CI (GitHub Actions) and pushed to
# GHCR, so Home Assistant PULLS a ready image instead of building on the user's box.
# Built from the repo ROOT context (so core/, plugins/, web/ are present), and run via
# run.sh (which maps HA add-on options from /data/options.json to DRAVIX_* env).

# ── Stage 1: build the React dashboard ───────────────────────────────────────
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# ── Stage 2: the Python service ──────────────────────────────────────────────
FROM python:3.12-slim
ARG DRAVIX_VERSION=dev
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DRAVIX_DATA_DIR=/data \
    DRAVIX_VERSION=${DRAVIX_VERSION}
WORKDIR /app
# ffmpeg powers the security-gallery "timelapse video" feature (an MP4 built from a day's
# snapshots). Small; optional at runtime — the endpoint 501s gracefully if it's absent.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY README.md /app/README.md
COPY core /app/core
COPY plugins /app/plugins
COPY docs /app/docs
# The firmware YAML — updates.py reads its `fw_version` to tell the robot when a new firmware
# ships (the "firmware update available" nudge). Without it, bundled_fw_version() returns None
# and the whole update indicator silently no-ops. Only this one file is needed at runtime.
COPY deploy/esphome/stackchan-dravix.yaml /app/deploy/esphome/stackchan-dravix.yaml
RUN pip install -e /app/core
COPY --from=web /web/dist /app/web/dist
COPY dravix_os/run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /app/core
EXPOSE 8800
CMD ["/run.sh"]
