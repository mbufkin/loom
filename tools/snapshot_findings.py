#!/usr/bin/env python3
"""
snapshot_findings.py — golden-output regression harness for Layer 1 findings.

Why this exists (docs/roadmap.md, docs/BETS.md Bet 5/12): the owner's standing
worry is "every change we make, we can't see how it affects other entry data."
Until now there was no safety net — a prompt tweak or scoring change that improved
Dallas could silently move Region10 and nobody would notice until reading the
report by hand. This tool captures a deterministic snapshot of each project's
aggregate conformance findings and diffs the live output against a committed
baseline, so one command answers "did anything change, and where."

It deliberately reuses synthesize.aggregate_layer1() — the SAME deterministic
aggregation the report is built from — so the golden is exactly the signal a
director sees, not a parallel re-implementation that could drift from it.

Usage:
  python3 tools/snapshot_findings.py --check            # diff every project vs its golden (CI-style)
  python3 tools/snapshot_findings.py --check --project dallas-career-2026
  python3 tools/snapshot_findings.py --update           # (re)write goldens after an intended change
  python3 tools/snapshot_findings.py --update --project region10-career-college-2026

Exit code is non-zero when --check finds any drift, so it can gate a change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python3 tools/snapshot_findings.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_lib import BASE_DIR, atomic_write, load_yaml, log, project_dir  # noqa: E402
from synthesize import (  # noqa: E402
    aggregate_layer1,
    aggregate_layer2,
    build_doc_title_map,
    load_layer1_data,
    load_layer2_data,
)

# Keys of the aggregate that constitute the regression signal. Excludes nothing
# structural, but pins the fields a human would actually check: how many of each
# status, the missing-materials pattern, and the exact document-level attention
# list (title + where-filed + what-it-reads-as + agreement counts). The excerpt
# is kept — if extraction changes the quote, that IS a regression worth seeing.
SNAPSHOT_KEYS = (
    "documents_judged",
    "elements_judged",
    "status_counts",
    "finding_status_counts",
    "mismatch_element_count",
    "review_queue_pending_pairs",
    "systemic_missing",
    "mismatch_docs_high",
    "mismatch_docs_low",
    "unit_rollup",
)

# Same idea, one level down: Layer 2's completeness aggregate (see
# synthesize.aggregate_layer2). Nested under "layer2" in the snapshot so a
# project with no Layer 2 output yet (documents_judged=0) still snapshots
# cleanly rather than crashing the harness.
LAYER2_SNAPSHOT_KEYS = (
    "documents_judged",
    "complete_count",
    "incomplete_count",
    "incomplete_docs",
    "systemic_missing_components",
)


def compute_snapshot(project_id: str) -> dict:
    root = project_dir(project_id)
    manifest = load_yaml(root / "manifest.yaml")
    bucket_rows, findings = load_layer1_data(project_id)
    agg = aggregate_layer1(bucket_rows, findings, manifest)
    agg2 = aggregate_layer2(load_layer2_data(project_id), build_doc_title_map(manifest))
    snapshot = {k: agg[k] for k in SNAPSHOT_KEYS}
    snapshot["layer2"] = {k: agg2[k] for k in LAYER2_SNAPSHOT_KEYS}
    return snapshot


def golden_path(project_id: str) -> Path:
    return project_dir(project_id) / "layer1" / "GOLDEN.json"


def discover_projects() -> list[str]:
    """Every project that has Layer 1 output on disk (a bucket-ledger to snapshot)."""
    projects_root = BASE_DIR / "projects"
    return sorted(
        p.name
        for p in projects_root.iterdir()
        if p.is_dir() and (p / "layer1" / "bucket-ledger.json").is_file()
    )


def _canonical(obj: object) -> str:
    """Stable JSON text so diffs reflect real content changes, not key ordering."""
    return json.dumps(obj, indent=2, sort_keys=True)


def _diff_report(old: dict, new: dict) -> list[str]:
    """Human-readable list of what changed between two snapshots. Top-level scalar
    and dict fields are compared directly; the two document-level attention lists
    are compared by doc_id so a director sees 'this document newly flagged' rather
    than an opaque list-index diff."""
    out: list[str] = []

    for key in (
        "documents_judged",
        "elements_judged",
        "mismatch_element_count",
        "review_queue_pending_pairs",
    ):
        if old.get(key) != new.get(key):
            out.append(f"  {key}: {old.get(key)} -> {new.get(key)}")

    for key in ("status_counts", "finding_status_counts"):
        o, n = old.get(key, {}), new.get(key, {})
        for k in sorted(set(o) | set(n)):
            if o.get(k, 0) != n.get(k, 0):
                out.append(f"  {key}[{k}]: {o.get(k, 0)} -> {n.get(k, 0)}")

    def _by_doc(lst: list[dict]) -> dict[str, dict]:
        return {d["doc_id"]: d for d in lst}

    for level in ("mismatch_docs_high", "mismatch_docs_low"):
        o, n = _by_doc(old.get(level, [])), _by_doc(new.get(level, []))
        for doc_id in sorted(set(o) - set(n)):
            out.append(f"  {level}: no longer flagged: {o[doc_id]['title']} ({doc_id})")
        for doc_id in sorted(set(n) - set(o)):
            out.append(
                f"  {level}: newly flagged: {n[doc_id]['title']} ({doc_id}) -> {n[doc_id]['matched_title']}"
            )
        for doc_id in sorted(set(o) & set(n)):
            if _canonical(o[doc_id]) != _canonical(n[doc_id]):
                out.append(f"  {level}: changed: {n[doc_id]['title']} ({doc_id})")

    ol2, nl2 = old.get("layer2") or {}, new.get("layer2") or {}
    for key in ("documents_judged", "complete_count", "incomplete_count"):
        if ol2.get(key) != nl2.get(key):
            out.append(f"  layer2.{key}: {ol2.get(key)} -> {nl2.get(key)}")
    o2, n2 = _by_doc(ol2.get("incomplete_docs", [])), _by_doc(
        nl2.get("incomplete_docs", [])
    )
    for doc_id in sorted(set(o2) - set(n2)):
        out.append(
            f"  layer2.incomplete_docs: no longer incomplete: {o2[doc_id]['title']} ({doc_id})"
        )
    for doc_id in sorted(set(n2) - set(o2)):
        out.append(
            f"  layer2.incomplete_docs: newly incomplete: {n2[doc_id]['title']} ({doc_id}) "
            f"missing {', '.join(n2[doc_id]['components_missing'])}"
        )
    for doc_id in sorted(set(o2) & set(n2)):
        if _canonical(o2[doc_id]) != _canonical(n2[doc_id]):
            out.append(
                f"  layer2.incomplete_docs: changed: {n2[doc_id]['title']} ({doc_id})"
            )

    return out


def check_project(project_id: str) -> bool:
    """True if the live snapshot matches the committed golden. Prints drift if not."""
    gp = golden_path(project_id)
    if not gp.is_file():
        log(
            f"MISSING GOLDEN {project_id}: no baseline at {gp} — run with --update to create it"
        )
        return False
    live = compute_snapshot(project_id)
    golden = json.loads(gp.read_text())
    if _canonical(live) == _canonical(golden):
        log(f"OK   {project_id}: matches golden")
        return True
    log(f"DRIFT {project_id}:")
    for line in _diff_report(golden, live) or [
        "  (content changed; see full snapshot)"
    ]:
        log(line)
    return False


def update_project(project_id: str) -> None:
    atomic_write(golden_path(project_id), _canonical(compute_snapshot(project_id)))
    log(f"wrote golden {golden_path(project_id)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Golden-output regression harness for Layer 1 findings"
    )
    parser.add_argument(
        "--project", help="Single project id (default: all projects with layer1 output)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Diff live findings vs committed golden; non-zero exit on drift",
    )
    mode.add_argument(
        "--update",
        action="store_true",
        help="(Re)write goldens to match current output",
    )
    args = parser.parse_args()

    projects = [args.project] if args.project else discover_projects()
    if not projects:
        log("No projects with layer1/bucket-ledger.json found.")
        return 1

    if args.update:
        for pid in projects:
            update_project(pid)
        return 0

    all_ok = all(check_project(pid) for pid in projects)
    if not all_ok:
        log("")
        log(
            "Regression drift detected. If intended, re-run with --update to accept the new baseline."
        )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
