# dravix-os — multi-stage build (React dashboard + Python service)

# ── Stage 1: build the React dashboard ───────────────────────────────────────
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build      # -> /web/dist

# ── Stage 2: the Python service ──────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DRAVIX_DATA_DIR=/app/data

WORKDIR /app

# Editable install keeps the package at /app/core so REPO_ROOT-relative paths
# (plugins/, web/dist, data/) resolve under /app. README is referenced by pyproject.
COPY README.md /app/README.md
COPY core /app/core
COPY plugins /app/plugins
COPY docs /app/docs
RUN pip install -e /app/core

# The built dashboard from stage 1 (served by FastAPI at /).
COPY --from=web /web/dist /app/web/dist

WORKDIR /app/core
EXPOSE 8800

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8800/api/health').status==200 else 1)"

CMD ["python", "-m", "dravix"]
