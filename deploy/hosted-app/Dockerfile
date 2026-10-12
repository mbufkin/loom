# Hosted Loom app server: ui/server.py on the Pi, reached only through the
# Vercel forwarder (shared secret) via a Cloudflare tunnel.
# Build/run from this folder:  docker compose up -d --build   (see RUNBOOK.md)
#
# Inside: the program (pipeline scripts, workflows, ui/server.py). NOT inside:
# curricula, the Next app, secrets — see Dockerfile.dockerignore. Curricula
# live on the SSD bind mount at /data; secrets arrive via env_file.
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
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Program files are root-owned and read-only to the service: only /data is
# writable, so a bug in an upload path cannot rewrite the code it runs.
COPY . .

# LOOM_HOME pins curricula, logs and config.yaml to the mounted volume.
# LOOM_CONFIG points the pipeline at the same pinned file explicitly.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOOM_HOME=/data \
    LOOM_CONFIG=/data/config.yaml \
    LOOM_VOLUME_MARKER=/data/.loom-app-volume \
    XDG_CACHE_HOME=/tmp/.cache
# (The root filesystem is mounted read-only by compose; fontconfig and pip-free
# caches go to the /tmp tmpfs instead.)

USER loom
EXPOSE 8770
ENTRYPOINT ["/usr/bin/tini", "--", "/app/deploy/hosted-app/entrypoint.sh"]
CMD ["python", "ui/server.py", "--host", "0.0.0.0", "--port", "8770"]
