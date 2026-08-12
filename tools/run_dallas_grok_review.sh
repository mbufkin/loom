#!/usr/bin/env bash
# One supported path for the Dallas review website surface.
#
# Writes under:
#   projects/dallas-career-2026/e2e/runs/grok-dallas-YYYYMMDD/
# On success, run_project publishes REVIEW-READY.json and the UI lists only that run.
#
# Usage (from repo root):
#   ./tools/run_dallas_grok_review.sh
#   ./tools/run_dallas_grok_review.sh --force   # extra run_project flags after --
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

RUN_ID="${LOOM_DALLAS_GROK_RUN_ID:-grok-dallas-$(date -u +%Y%m%d)}"
export LOOM_CONFIG="${LOOM_CONFIG:-$DIR/config.grok.yaml}"
# Line-buffer child Python so operators can follow e2e/*.log in real time.
export PYTHONUNBUFFERED=1

echo "[dallas-grok] LOOM_CONFIG=$LOOM_CONFIG"
echo "[dallas-grok] run_id=$RUN_ID"
echo "[dallas-grok] → e2e/runs/$RUN_ID/"

exec ./run-audit dallas-career-2026 \
  --with-graph \
  --graph-backend cursor \
  --graph-cursor-model grok-4.5 \
  --graph-run "$RUN_ID" \
  "$@"
