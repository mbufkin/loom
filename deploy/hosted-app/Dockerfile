# Hosted Loom app: ui/server.py serves the built React UI and /api from one
# origin, behind a Cloudflare tunnel with Cloudflare Access in front.
# Build/run from this folder:  docker compose up -d --build   (see RUNBOOK.md)
#
# Inside: the program (pipeline scripts, workflows, ui/server.py, ui/dist).
# NOT inside: curricula, the Next app, secrets — see Dockerfile.dockerignore.
# Curricula live on the SSD bind mount at /data; secrets arrive via env_file.

# --- 1. The React UI, built in hosted mode -----------------------------------
# VITE_HOSTED=1 hides the model picker, key entry and installer. No
# VITE_API_BASE: the UI calls /api on the same origin, as on the desktop.
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
# --include=dev: TypeScript and Vite are devDependencies and must be the
# locally pinned ones (never an npx download).
RUN npm ci --include=dev --no-audit --no-fund
COPY ui/ ./
# GOMAXPROCS caps esbuild at 2 cores: an all-core build spike has browned out
# the Pi (it has an under-voltage history) and rebooted it mid-build.
RUN GOMAXPROCS=2 VITE_HOSTED=1 npm run build

# --- 2. The server -------------------------------------------------------------
FROM python:3.12-slim-bookworm

# poppler-utils: pdftotext (doc_extract's preferred PDF path) · antiword: .doc
# pango/harfbuzz + fonts: WeasyPrint report PDFs · tini: PID 1 that forwards
# SIGTERM and reaps the ingest/audit child processes the server spawns.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      poppler-utils antiword \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      fonts-dejavu-core fonts-liberation \
      tini \
 && rm -rf /var/lib/apt/lists/*

# Same uid/gid as `mbufkin` on the Pi so files on the SSD stay owned by that user.
RUN groupadd --gid 1000 loom && useradd --uid 1000 --gid 1000 --create-home loom

WORKDIR /app
COPY requirements.txt requirements-hosted.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-hosted.txt

# Program files are root-owned and read-only to the service: only /data is
# writable, so a bug in an upload path cannot rewrite the code it runs.
COPY . .
COPY --from=ui /ui/dist /app/ui/dist

# LOOM_HOSTED=1 turns on the Cloudflare Access check (ui/hosted_guard.py);
# the server refuses to start without LOOM_ACCESS_TEAM_DOMAIN + LOOM_ACCESS_AUD.
# LOOM_HOME pins curricula, logs and config.yaml to the mounted volume.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOOM_HOSTED=1 \
    LOOM_HOME=/data \
    LOOM_CONFIG=/data/config.yaml \
    LOOM_VOLUME_MARKER=/data/.loom-app-volume \
    XDG_CACHE_HOME=/tmp/.cache
# (The root filesystem is mounted read-only by compose; fontconfig caches go
# to the /tmp tmpfs instead.)

USER loom
EXPOSE 8770
ENTRYPOINT ["/usr/bin/tini", "--", "/app/deploy/hosted-app/entrypoint.sh"]
CMD ["python", "ui/server.py", "--host", "0.0.0.0", "--port", "8770"]
