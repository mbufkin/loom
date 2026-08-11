#!/usr/bin/env bash
# Serve the Path A Docs-style review HTML so Cursor can open it over HTTP (SSH-friendly).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8765}"
python3 "$ROOT/tools/build_path_a_review_html.py"
cd "$ROOT/docs"
echo "Serving Path A review at http://127.0.0.1:${PORT}/PATH-A-CATTLE-LP-REVIEW.html"
# Bind all interfaces so Cursor Simple Browser / Glass can reach it over SSH.
exec python3 -m http.server "$PORT" --bind 0.0.0.0
