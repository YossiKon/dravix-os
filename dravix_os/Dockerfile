# Home Assistant add-on image for dravix-os.
# Self-contained: clones the repo (so plugins/ + web are present), builds the dashboard,
# installs the core package, and runs via run.sh (which reads HA add-on options from /data).
#
# IMPORTANT: the `git clone` layers are cache-busted by BUILD_VERSION (passed by the HA
# supervisor = the add-on version). Without this, Docker reuses the FIRST build's cached
# clone on every "update", so the version label advances but the code never changes.

ARG DRAVIX_REPO="https://github.com/YossiKon/dravix-os"
ARG DRAVIX_REF="main"

# ── stage 1: build the React dashboard ───────────────────────────────────────
FROM node:20-slim AS web
ARG DRAVIX_REPO
ARG DRAVIX_REF
ARG BUILD_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN echo "dravix ${BUILD_VERSION:-dev} @ ${DRAVIX_REF}" \
    && git clone --depth 1 --branch "$DRAVIX_REF" "$DRAVIX_REPO" /src
WORKDIR /src/web
RUN npm install && npm run build

# ── stage 2: the Python service ──────────────────────────────────────────────
FROM python:3.12-slim
ARG DRAVIX_REPO
ARG DRAVIX_REF
ARG BUILD_VERSION
ENV PYTHONUNBUFFERED=1 DRAVIX_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN echo "dravix ${BUILD_VERSION:-dev} @ ${DRAVIX_REF}" \
    && git clone --depth 1 --branch "$DRAVIX_REF" "$DRAVIX_REPO" /app
# Editable so REPO_ROOT-relative paths (plugins/, web/dist) resolve under /app.
RUN pip install --no-cache-dir -e /app/core
COPY --from=web /src/web/dist /app/web/dist
COPY run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /app/core
EXPOSE 8800
CMD ["/run.sh"]
