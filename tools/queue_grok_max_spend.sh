#!/usr/bin/env bash
# Prioritized Grok max-spend queue (Dallas E2E → quality/Path-A → forensic → Bluebonnet).
#
# Educational note: serialize Grok-heavy stages so the Cursor bridge (:8788) and
# SDK Agent.prompt jobs do not thrash the same rate limit. Local/NIM graph queues
# may keep running in parallel — they do not use Grok.
#
# Monitor:
#   tail -f /tmp/loom-grok-max-spend.log
#   cat /tmp/loom-grok-max-spend.pid
# Morning review brief:
#   /tmp/loom-overnight/MORNING-REVIEW.md
#   /tmp/loom-MORNING-REVIEW.md  (symlink)
set -euo pipefail

REPO=/home/lenovo/g10-control-center-loom
cd "$REPO"

LOG=${LOG:-/tmp/loom-grok-max-spend.log}
E2E_PID_FILE=${E2E_PID_FILE:-/tmp/loom-e2e-queue/grok-4.5.pid}
LOOM_CONFIG=${LOOM_CONFIG:-/tmp/loom-e2e-configs/grok-4.5.yaml}
export LOOM_CONFIG
export LOOM_E2E_RUN=grok-4.5
export CURSOR_API_KEY="${CURSOR_API_KEY:?CURSOR_API_KEY required}"

# Prefer repo-local @cursor/sdk (npm install); fall back to pi agent install.
export NODE_PATH="${REPO}/node_modules${NODE_PATH:+:$NODE_PATH}"

ts() { date -Is; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

wait_pid_file() {
  local file=$1 label=$2
  if [[ ! -f "$file" ]]; then
    say "no pid file for $label ($file) — continuing"
    return 0
  fi
  local pid
  pid=$(cat "$file" || true)
  if [[ -z "${pid:-}" ]]; then
    say "empty pid for $label — continuing"
    return 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    say "$label pid $pid already exited"
    return 0
  fi
  say "waiting for $label pid=$pid …"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 30
  done
  say "$label finished"
}

say "=== grok max-spend queue start ==="
say "LOOM_CONFIG=$LOOM_CONFIG LOOM_E2E_RUN=$LOOM_E2E_RUN"

# 0) Let in-flight Dallas Grok E2E finish (Layer0→…→graph local).
wait_pid_file "$E2E_PID_FILE" "dallas-e2e-grok"

# 1) Path A depth + per-model quality A/B plates (huge Grok burn via bridge).
#    E2E already ran Path A; this regenerates rungs + quality + grounded review
#    into e2e/runs/grok-4.5/ so the UI model picker can swap the heatmap.
say "=== stage1: rungs + lesson-quality + curriculum-review (e2e/grok-4.5) ==="
for step in lesson_rung.py artifact_rung.py unit_rung.py lesson_quality.py curriculum_review.py; do
  if [[ -f "$step" ]]; then
    say "→ python3 $step --project dallas-career-2026"
    python3 -u "$step" --project dallas-career-2026 >>"$LOG" 2>&1 \
      || say "WARN: $step exited $?"
  else
    say "WARN: missing $step"
  fi
done
python3 tools/record_cursor_usage.py --project dallas-career-2026 --finalize-only >>"$LOG" 2>&1 || true
say "stage1 done — plates under projects/dallas-career-2026/e2e/runs/grok-4.5/output/"

# 2) Forensic repair: force re-graph units with skipped_no_evidence (Cursor Grok).
say "=== stage2: forensic graph force on soft-skip / empty-evidence units ==="
for unit in career-cluster information-technology; do
  say "→ graph-only force $unit (cursor grok-4.5)"
  python3 -u run_project.py --project dallas-career-2026 --graph-only --with-graph \
    --graph-backend cursor --graph-cursor-model grok-4.5 --graph-run grok-4.5 \
    --only "$unit" --force >>"$LOG" 2>&1 \
    || say "WARN: forensic $unit exited $?"
done
python3 tools/record_cursor_usage.py --project dallas-career-2026 --finalize-only >>"$LOG" 2>&1 || true
say "stage2 done"

# 3) Bluebonnet full re-run (--force) via Cursor SDK Agent.prompt (Grok).
#    Skip if a bluebonnet force job is already running (pid file).
say "=== stage3: Bluebonnet full Grok --force (19 units) ==="
BB_PID_FILE=/tmp/loom-bluebonnet-grok-force.pid
if [[ -f "$BB_PID_FILE" ]] && kill -0 "$(cat "$BB_PID_FILE")" 2>/dev/null; then
  say "bluebonnet force already running pid=$(cat "$BB_PID_FILE") — waiting"
  wait_pid_file "$BB_PID_FILE" "bluebonnet-force"
else
  say "→ node tools/run_full_bluebonnet_grok.mjs --force"
  node tools/run_full_bluebonnet_grok.mjs --force >>"$LOG" 2>&1 \
    || say "WARN: bluebonnet force exited $?"
fi
say "stage3 done"

say "=== grok max-spend queue COMPLETE ==="
