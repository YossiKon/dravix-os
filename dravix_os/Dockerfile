# The Dravix add-on image. GitHub Actions builds it from the repository root and pushes it to GHCR;
# Home Assistant pulls it (config.yaml: image). Python, aiohttp, PyYAML and one page.
FROM python:3.12-slim
ARG DRAVIX_VERSION=dev
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DRAVIX_VERSION=${DRAVIX_VERSION}
RUN pip install "aiohttp>=3.9,<4" "PyYAML>=6,<7"
WORKDIR /app
COPY dravix_os/app/ /app/
# the automations the page installs (the same files the README links to)
COPY docs/ha-voice.yaml /app/templates/voice.yaml
COPY docs/ha-automations.yaml /app/templates/photos.yaml
EXPOSE 8800
CMD ["python", "/app/server.py"]
