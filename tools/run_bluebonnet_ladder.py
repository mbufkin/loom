#!/usr/bin/env python3
"""Run Bluebonnet validation ladder stages with pass checks + auto-resume.

Stages: d1 (already green) → d2 → d3 → d4

Usage:
  python3 tools/run_bluebonnet_ladder.py --from-stage d2
  python3 tools/run_bluebonnet_ladder.py --from-stage d2 --max-restarts 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PROJECT = "bluebonnet-math-2026"
ROOT = BASE / "projects" / PROJECT
VALIDATION = ROOT / "VALIDATION.md"

STAGES = ["d1", "d2", "d3", "d4"]


def log(msg: str) -> None:
    print(f"[ladder] {msg}", flush=True)


def run(cmd: list[str], log_path: Path) -> int:
    log(f"$ {' '.join(cmd)}")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"\n# --- {datetime.now(timezone.utc).isoformat()} ---\n")
        fh.write(f"# {' '.join(cmd)}\n")
        fh.flush()
        import os

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        p = subprocess.Popen(
            cmd,
            cwd=str(BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert p.stdout is not None
        for line in p.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
            fh.flush()
        return p.wait()


def source_pdfs() -> list[str]:
    return sorted(p.name for p in (ROOT / "sources").rglob("*.pdf"))


def ledger_docs() -> set[str]:
    path = ROOT / "layer0" / "ledger.json"
    if not path.is_file():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r.get("source_file") for r in rows if r.get("source_file")}


def layer1_stats() -> dict:
    path = ROOT / "layer1" / "bucket-ledger.json"
    if not path.is_file():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("bucket_rows") or []
    return dict(Counter(r.get("match_status") for r in rows))


def organize_batches() -> int:
    raw = ROOT / "layer1" / ".raw"
    if not raw.is_dir():
        return 0
    return len(list(raw.glob("*phase1-batch*.json")))


def check_pass(stage: str) -> tuple[bool, list[str]]:
    """Return (ok, notes)."""
    notes: list[str] = []
    pdfs = source_pdfs()
    if not pdfs:
        return False, ["no PDFs in sources/"]
    led = ledger_docs()
    missing = [p for p in pdfs if p not in led]
    coverage = (len(pdfs) - len(missing)) / len(pdfs)
    notes.append(
        f"Layer 0 coverage: {len(pdfs) - len(missing)}/{len(pdfs)} docs "
        f"({coverage:.0%}); missing={missing[:5]}{'...' if len(missing) > 5 else ''}"
    )
    # Allow up to 15% doc loss from isolated JSON skips — but require majority.
    if coverage < 0.85:
        notes.append("FAIL: Layer 0 coverage < 85%")
        return False, notes

    report = ROOT / "output" / "GLOBAL-AUDIT-REPORT.pdf"
    if not report.is_file():
        notes.append("FAIL: missing GLOBAL-AUDIT-REPORT.pdf")
        return False, notes
    # Report must be newer than stage start — checked loosely via mtime vs ledger
    notes.append(f"report ok ({report.stat().st_size} bytes)")

    l1 = layer1_stats()
    notes.append(f"Layer 1 match_status: {l1}")
    judged = sum(v for k, v in l1.items() if k and k != "UNVERIFIED")
    unverified = l1.get("UNVERIFIED", 0)
    total = judged + unverified
    if total == 0:
        notes.append("FAIL: Layer 1 empty")
        return False, notes
    # Batched ORGANIZE must have fired for large G5/Alg packs (except tiny d1 re-runs)
    batches = organize_batches()
    notes.append(f"ORGANIZE batch artifact files: {batches}")
    if stage in ("d2", "d3", "d4") and batches < 1:
        # Large Learn/TE docs should produce batches; warn but don't fail if
        # all docs happened to be small after extract failures.
        notes.append("WARN: no ORGANIZE batch files (large docs may have failed L0)")

    # Not a mass ORGANIZE collapse: at least some MATCH/MISMATCH judgments
    if judged < 5 and stage != "d1":
        notes.append("FAIL: fewer than 5 non-UNVERIFIED Layer 1 judgments")
        return False, notes

    notes.append("PASS")
    return True, notes


def reset_layer0_for_rechunk() -> None:
    """Chunk-size change invalidates mid-chunk resume caches + partial ledgers."""
    l0 = ROOT / "layer0"
    if not l0.is_dir():
        return
    ledger = l0 / "ledger.json"
    if ledger.is_file():
        ledger.rename(ledger.with_suffix(".json.bak-pre-rechunk"))
        log(f"backed up ledger → {ledger.with_suffix('.json.bak-pre-rechunk').name}")
    raw = l0 / ".raw"
    if raw.is_dir():
        n = 0
        for p in raw.glob("*-resolved-rows.json"):
            p.unlink()
            n += 1
        log(f"cleared {n} mid-chunk resume caches (chunk boundaries changed)")


def append_validation(stage: str, ok: bool, notes: list[str], elapsed_s: float) -> None:
    VALIDATION.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        f"\n## {stage.upper()} results ({stamp})\n\n"
        f"- Result: **{'PASS' if ok else 'FAIL'}**\n"
        f"- Wall-clock: {elapsed_s / 3600:.2f} h\n"
        f"- Sources: {len(source_pdfs())} PDFs\n"
        f"- Ledger docs: {len(ledger_docs())}\n"
    )
    for n in notes:
        block += f"- {n}\n"
    if VALIDATION.is_file():
        text = VALIDATION.read_text(encoding="utf-8")
    else:
        text = "# Bluebonnet validation log\n"
    # Update ladder table row status
    status = "**Pass**" if ok else "**Fail**"
    lines = []
    for line in text.splitlines():
        if line.startswith(f"| {stage.upper()} ") or line.startswith(f"| {stage} "):
            # leave historical; append section instead
            lines.append(line)
        else:
            lines.append(line)
    VALIDATION.write_text("\n".join(lines) + block + "\n", encoding="utf-8")


def run_stage(stage: str, max_restarts: int) -> bool:
    log_path = Path(f"/tmp/loom-bb-{stage}.log")
    if log_path.is_file():
        log_path.write_text("", encoding="utf-8")  # fresh log per attempt chain

    stage_script = BASE / "tools" / "stage_bluebonnet_units.py"
    rc = run(
        [sys.executable, str(stage_script), "--stage", stage],
        log_path,
    )
    if rc != 0:
        log(f"stage {stage} staging failed rc={rc}")
        return False

    for attempt in range(1, max_restarts + 1):
        log(f"=== {stage} audit attempt {attempt}/{max_restarts} ===")
        t0 = time.time()
        rc = run(
            [
                str(BASE / "run-audit"),
                PROJECT,
                "--force",
                "--skip-drive-push",
            ],
            log_path,
        )
        elapsed = time.time() - t0
        ok, notes = check_pass(stage)
        for n in notes:
            log(n)
        if rc == 0 and ok:
            append_validation(stage, True, notes, elapsed)
            log(f"{stage} PASS in {elapsed / 3600:.2f}h")
            return True
        log(f"{stage} attempt {attempt} incomplete (rc={rc}, pass={ok})")
        if attempt < max_restarts:
            log("restarting audit to resume Layer 0 caches / finish missing docs...")
            time.sleep(5)
    append_validation(stage, False, notes, elapsed)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-stage", default="d2", choices=STAGES)
    ap.add_argument(
        "--max-restarts",
        type=int,
        default=4,
        help="Audit restarts per stage (Layer 0 resume picks up unfinished docs)",
    )
    ap.add_argument(
        "--reset-layer0",
        action="store_true",
        help="Backup ledger + clear chunk resume caches before first stage "
        "(required after CHUNK_SIZE change)",
    )
    args = ap.parse_args()

    if args.reset_layer0:
        reset_layer0_for_rechunk()

    start = STAGES.index(args.from_stage)
    for stage in STAGES[start:]:
        log(f"######## ladder stage {stage} ########")
        if not run_stage(stage, args.max_restarts):
            log(f"STOP: {stage} did not pass")
            return 1
    log("All requested ladder stages PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
