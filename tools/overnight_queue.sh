#!/usr/bin/env bash
# overnight_queue.sh — unattended back-to-back Crystallize runs (Bet 6).
#
# Designed to run for hours with no interaction: model health-check, full Dallas
# re-extract under the citation-quality gate, then refresh goldens for both
# corpora that have Layer 1 output. Logs + a STATUS file so you can check in
# the morning without reading the whole log.
#
# Usage (from repo root, or via absolute path):
#   nohup tools/overnight_queue.sh > projects/dallas-career-2026/runs/overnight-$(date -u +%Y%m%d-%H%M%S).log 2>&1 &
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
RUN_DIR="$DIR/projects/dallas-career-2026/runs"
mkdir -p "$RUN_DIR"
STATUS="$RUN_DIR/OVERNIGHT-STATUS.txt"
LOG="$RUN_DIR/overnight-${STAMP}.log"

# Mirror everything to the dated log as well as whatever nohup already captures.
exec > >(tee -a "$LOG") 2>&1

status() {
  local msg="$1"
  local line="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $msg"
  echo "$line"
  {
    echo "# Crystallize overnight queue"
    echo "updated_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "log: $LOG"
    echo "state: $msg"
  } > "$STATUS"
}

fail() {
  status "FAILED: $*"
  exit 1
}

status "START — health-check models"
curl -sf --max-time 10 http://127.0.0.1:30000/health >/dev/null \
  || fail "Nemotron (:30000) not healthy — start serve-cuda before overnight runs"

# ---------------------------------------------------------------------------
# Job 1 (long): full Dallas re-run with Layer 0 forced fresh.
# This is the corpus that still has the pre-fix ~55% uncited ledger.
# Region10 already completed cleanly earlier today — do not redo it here.
# ---------------------------------------------------------------------------
status "RUNNING dallas-career-2026 (layer0-no-resume → 0-B → 1 → 2 → synthesize)"
python3 "$DIR/run_project.py" \
  --project dallas-career-2026 \
  --layer0-no-resume \
  || fail "dallas-career-2026 pipeline exited non-zero"

# ---------------------------------------------------------------------------
# Job 2 (seconds): refresh golden snapshots so morning --check matches reality.
# ---------------------------------------------------------------------------
status "UPDATING goldens (dallas + any other project with layer1 output)"
python3 "$DIR/tools/snapshot_findings.py" --update \
  || fail "snapshot_findings --update failed"

status "DONE — Dallas re-run + goldens updated. Check GLOBAL-AUDIT-REPORT.pdf and OVERNIGHT-STATUS.txt"
echo ""
echo "Artifacts:"
echo "  $DIR/projects/dallas-career-2026/output/GLOBAL-AUDIT-REPORT.pdf"
echo "  $DIR/projects/dallas-career-2026/output/GLOBAL-AUDIT.md"
echo "  $DIR/projects/dallas-career-2026/layer2/REPORT.md"
echo "  $STATUS"
echo "  $LOG"
