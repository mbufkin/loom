#!/usr/bin/env bash
# Upload flow diagram SVG + PNG exports to Google Drive.
set -euo pipefail

RCLONE="${RCLONE:-$HOME/.local/bin/rclone}"
REMOTE="${REMOTE:-gdrive}"
FOLDER="${FOLDER:-CTAT-2026/flow-diagrams}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$RCLONE" ]]; then
  echo "rclone not found. Install: curl arm64 zip from rclone.org → ~/.local/bin/"
  exit 1
fi

if ! "$RCLONE" listremotes 2>/dev/null | grep -q "^${REMOTE}:$"; then
  echo "Google Drive not configured yet."
  echo "Run: bash $SCRIPT_DIR/setup-gdrive-rclone.sh"
  exit 1
fi

DEST="${REMOTE}:${FOLDER}"
echo "Uploading to ${DEST}"

# Ensure destination folder exists
"$RCLONE" mkdir "$DEST" 2>/dev/null || true

"$RCLONE" copy "$SCRIPT_DIR"/*.svg "$DEST/" -v
"$RCLONE" copy "$SCRIPT_DIR/png" "$DEST/png/" -v

echo
echo "Done. Files on Drive:"
"$RCLONE" ls "$DEST"
"$RCLONE" ls "$DEST/png"

echo
echo "Drive link (open in browser while logged in):"
echo "  https://drive.google.com/drive/search?q=CTAT-2026"
