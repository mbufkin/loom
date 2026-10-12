#!/bin/sh
# Refuse to start unless the real data volume is mounted and the server is in
# hosted mode. Both failures are silent and bad otherwise: without the marker
# the curricula would land on the SD card; without the secret the server would
# answer anyone who finds the tunnel hostname.
set -eu

if [ ! -f "${LOOM_VOLUME_MARKER:?}" ]; then
  echo "[loom-app] refusing to start: ${LOOM_VOLUME_MARKER} missing (is the SSD mounted?)" >&2
  exit 78
fi
if [ -z "${LOOM_PROXY_SECRET:-}" ]; then
  echo "[loom-app] refusing to start: LOOM_PROXY_SECRET is not set" >&2
  exit 78
fi
if [ ! -f "${LOOM_CONFIG:?}" ]; then
  echo "[loom-app] refusing to start: pinned config ${LOOM_CONFIG} missing" >&2
  exit 78
fi

exec "$@"
