#!/bin/sh
# Refuse to start unless the real data volume is mounted and the Cloudflare
# Access settings are present. Both failures are silent and bad otherwise:
# without the marker the curricula would land on the SD card; without the
# Access settings the server would have nothing to check tokens against.
# (ui/server.py checks the Access settings again itself — fail closed twice.)
set -eu

if [ ! -f "${LOOM_VOLUME_MARKER:?}" ]; then
  echo "[loom-app] refusing to start: ${LOOM_VOLUME_MARKER} missing (is the SSD mounted?)" >&2
  exit 78
fi
if [ "${LOOM_HOSTED:-}" = "1" ]; then
  if [ -z "${LOOM_ACCESS_TEAM_DOMAIN:-}" ] || [ -z "${LOOM_ACCESS_AUD:-}" ]; then
    echo "[loom-app] refusing to start: LOOM_ACCESS_TEAM_DOMAIN and LOOM_ACCESS_AUD are required" >&2
    exit 78
  fi
fi
if [ ! -f "${LOOM_CONFIG:?}" ]; then
  echo "[loom-app] refusing to start: pinned config ${LOOM_CONFIG} missing" >&2
  exit 78
fi

exec "$@"
