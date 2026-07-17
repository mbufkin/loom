#!/usr/bin/env bash
# One-time Google Drive setup for rclone on G10 (headless).
# Run the Mac step first, then paste the token here.
set -euo pipefail

RCLONE="${RCLONE:-$HOME/.local/bin/rclone}"
REMOTE_NAME="${REMOTE_NAME:-gdrive}"

if [[ ! -x "$RCLONE" ]]; then
  echo "rclone not found at $RCLONE"
  exit 1
fi

if "$RCLONE" listremotes 2>/dev/null | grep -q "^${REMOTE_NAME}:$"; then
  echo "Remote '${REMOTE_NAME}' already configured."
  "$RCLONE" about "${REMOTE_NAME}:"
  exit 0
fi

cat <<'EOF'

=== Google Drive setup (one time) ===

STEP 1 — On your Mac (local Terminal, not SSH):
  brew install rclone          # if needed
  rclone authorize "drive"

  Copy the entire JSON blob it prints (starts with { "access_token": ... ).

STEP 2 — Back on G10, run:
  bash setup-gdrive-rclone.sh '<paste-json-here>'

Or paste interactively when prompted below.

EOF

if [[ "${1:-}" == "" ]]; then
  read -r -p "Paste rclone token JSON: " TOKEN
else
  TOKEN="$1"
fi

if [[ -z "$TOKEN" ]]; then
  echo "No token provided."
  exit 1
fi

"$RCLONE" config create "$REMOTE_NAME" drive token "$TOKEN" scope drive
echo
echo "Success. Testing connection..."
"$RCLONE" about "${REMOTE_NAME}:"
echo
echo "Next: bash upload-to-gdrive.sh"
