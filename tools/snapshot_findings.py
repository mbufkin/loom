#!/usr/bin/env python3
"""
snapshot_findings.py — golden-output regression harness for Layer 1 and Paths.

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

Path findings extend the same idea one layer earlier: a keyword change in
workflows/checklists/*.yaml should produce a reviewable "23 documents moved
from MISSING to PARTIAL" diff, not an invisible shift. The path golden pins a
status matrix (doc × step), not the full findings JSON, so the product of a
failed --check is human-readable.

Usage:
  python3 tools/snapshot_findings.py --check            # Layer 1 + paths
  python3 tools/snapshot_findings.py --check --layer1   # Layer 1 only
  python3 tools/snapshot_findings.py --check --paths    # path findings only
  python3 tools/snapshot_findings.py --check --project dallas-career-2026
  python3 tools/snapshot_findings.py --update           # (re)write goldens

Exit code is non-zero when --check finds any drift, so it can gate a change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
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

PATH_LETTERS = ("A", "B", "C", "D", "E", "F", "G", "H")
_STEP_RE = re.compile(r"^[A-H]\d+$")


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


def paths_golden_path(project_id: str) -> Path:
    return project_dir(project_id) / "paths" / "GOLDEN.json"


def discover_layer1_projects() -> list[str]:
    """Every project that has Layer 1 output on disk (a bucket-ledger to snapshot)."""
    projects_root = BASE_DIR / "projects"
    return sorted(
        p.name
        for p in projects_root.iterdir()
        if p.is_dir() and (p / "layer1" / "bucket-ledger.json").is_file()
    )


def discover_path_projects() -> list[str]:
    """Projects whose path findings are regenerable and CI-checkable.

    Requires a route-map (so `run_paths.py` can refresh findings) and at least
    one path_*/findings.json. Trees that only carry a stale Path A emit from
    before the router existed are skipped — pinning them would freeze an
    unreproducible snapshot.
    """
    projects_root = BASE_DIR / "projects"
    out: list[str] = []
    for p in projects_root.iterdir():
        if not p.is_dir():
            continue
        if not (p / "layer0" / "route-map.json").is_file():
            continue
        if any(
            (p / f"path_{letter.lower()}" / "findings.json").is_file()
            for letter in PATH_LETTERS
        ):
            out.append(p.name)
    return sorted(out)


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


def _load_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, (dict, list)) else None


def _inventory_cells(inventory: list) -> dict[str, str]:
    """doc_id:step_id → status for the presence cells a human actually tunes."""
    cells: dict[str, str] = {}
    for row in inventory:
        if not isinstance(row, dict):
            continue
        did = row.get("doc_id")
        if not did:
            continue
        for key, val in row.items():
            if not _STEP_RE.match(str(key)) or not isinstance(val, dict):
                continue
            st = val.get("status")
            if st is not None:
                cells[f"{did}:{key}"] = str(st)
    return cells


def _field_cells(steps_by_doc: dict) -> dict[str, str]:
    """doc_id:step_id.field_id → status, one level below the step rollup.

    Educational note: step status alone is too coarse to review a keyword
    change. Correcting Path G turned two false PRESENTs into MISSING and one
    false MISSING into PRESENT, and because the step rolled up to PARTIAL
    either way, the pin showed almost nothing. Tuning happens at the field, so
    the pin has to record the field.
    """
    cells: dict[str, str] = {}
    if not isinstance(steps_by_doc, dict):
        return cells
    for doc_id, steps in steps_by_doc.items():
        if not isinstance(steps, dict):
            continue
        for step_id, step in steps.items():
            if not isinstance(step, dict):
                continue
            for field in step.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                fid, status = field.get("id"), field.get("status")
                if fid and status is not None:
                    cells[f"{doc_id}:{step_id}.{fid}"] = str(status)
    return cells


def compute_paths_snapshot(project_id: str) -> dict:
    """Distilled path + route-map snapshot. generated_at is dropped so two
    consecutive route.py runs do not defeat the diff; everything else the
    router emits that affects routing is kept."""
    root = project_dir(project_id)
    route_map = _load_json(root / "layer0" / "route-map.json") or {}
    routes_slim = []
    for r in route_map.get("routes") or []:
        if not isinstance(r, dict):
            continue
        routes_slim.append(
            {
                "doc_id": r.get("doc_id"),
                "doc_type": r.get("doc_type"),
                "workflow_id": r.get("workflow_id"),
                "path": r.get("path"),
                "reason": r.get("reason"),
            }
        )
    paths: dict[str, dict] = {}
    for letter in PATH_LETTERS:
        findings = _load_json(root / f"path_{letter.lower()}" / "findings.json")
        if not isinstance(findings, dict):
            continue
        cells = _inventory_cells(findings.get("inventory") or [])
        cells.update(_field_cells(findings.get("steps_by_doc") or {}))
        # Path A has no per-doc checklist cells; pin the aggregate step statuses
        # that curriculum-tier and LESSON-PLAN fill depend on, so a silent A3/A5
        # regression still shows up in --check.
        if letter == "A":
            steps = findings.get("steps") or {}
            for step_id, payload in steps.items():
                if not isinstance(payload, dict):
                    continue
                if "status" in payload:
                    cells[f"*:{step_id}"] = str(payload.get("status"))
                for nested_key in ("teks", "objective", "formative", "summative", "elps", "accommodations"):
                    nested = payload.get(nested_key)
                    if isinstance(nested, dict) and "status" in nested:
                        cells[f"*:{step_id}.{nested_key}"] = str(nested.get("status"))
            a5 = steps.get("A5") or {}
            if "hunter_core_present" in a5:
                cells["*:A5.hunter_core_present"] = str(a5.get("hunter_core_present"))
                cells["*:A5.hunter_core_total"] = str(a5.get("hunter_core_total"))
        status_counts = Counter(cells.values())
        paths[letter] = {
            "status": findings.get("status"),
            "lens": findings.get("lens"),
            "workflow_id": findings.get("workflow_id"),
            "checklist": findings.get("checklist"),
            "n_docs": len(findings.get("doc_ids") or []),
            "doc_ids": sorted(findings.get("doc_ids") or []),
            "status_counts": dict(sorted(status_counts.items())),
            "cells": dict(sorted(cells.items())),
        }
    return {
        "project_id": project_id,
        "route_map": {
            "counts": route_map.get("counts") or {},
            "unrouted_ledger_doc_ids": route_map.get("unrouted_ledger_doc_ids") or [],
            "routes": routes_slim,
        },
        "paths": paths,
    }


def _paths_diff_report(old: dict, new: dict) -> list[str]:
    """Human-readable path drift: status-count rollups, then per-cell moves."""
    out: list[str] = []
    o_rm, n_rm = old.get("route_map") or {}, new.get("route_map") or {}
    if _canonical(o_rm.get("counts")) != _canonical(n_rm.get("counts")):
        out.append(f"  route_map.counts: {o_rm.get('counts')} -> {n_rm.get('counts')}")
    if o_rm.get("unrouted_ledger_doc_ids") != n_rm.get("unrouted_ledger_doc_ids"):
        out.append("  route_map.unrouted_ledger_doc_ids changed")
    o_routes = {(r.get("doc_id"), r.get("path")) for r in (o_rm.get("routes") or [])}
    n_routes = {(r.get("doc_id"), r.get("path")) for r in (n_rm.get("routes") or [])}
    if o_routes != n_routes:
        added = sorted(n_routes - o_routes)
        removed = sorted(o_routes - n_routes)
        if added[:5]:
            out.append(f"  route_map routes added (sample): {added[:5]}")
        if removed[:5]:
            out.append(f"  route_map routes removed (sample): {removed[:5]}")
        out.append(
            f"  route_map route pairs: {len(o_routes)} -> {len(n_routes)} "
            f"(+{len(added)} / -{len(removed)})"
        )

    o_paths, n_paths = old.get("paths") or {}, new.get("paths") or {}
    for letter in PATH_LETTERS:
        o, n = o_paths.get(letter), n_paths.get(letter)
        if o is None and n is None:
            continue
        if o is None:
            out.append(f"  path {letter}: newly present ({n.get('n_docs')} docs)")
            continue
        if n is None:
            out.append(f"  path {letter}: no longer present")
            continue
        prefix = f"  path {letter}"
        for key in ("status", "lens", "workflow_id", "checklist", "n_docs"):
            if o.get(key) != n.get(key):
                out.append(f"{prefix}.{key}: {o.get(key)!r} -> {n.get(key)!r}")
        if o.get("doc_ids") != n.get("doc_ids"):
            o_ids, n_ids = set(o.get("doc_ids") or []), set(n.get("doc_ids") or [])
            out.append(
                f"{prefix}.doc_ids: +{sorted(n_ids - o_ids)[:5]} "
                f"-{sorted(o_ids - n_ids)[:5]}"
            )

        # Group cell transitions: "B3: 23 documents MISSING -> PARTIAL"
        o_cells, n_cells = o.get("cells") or {}, n.get("cells") or {}
        transitions: Counter[str] = Counter()
        for cell_id in sorted(set(o_cells) | set(n_cells)):
            old_st, new_st = o_cells.get(cell_id), n_cells.get(cell_id)
            if old_st == new_st:
                continue
            # cell_id is "doc:STEP" or "*:A5.hunter_core_present"
            step = cell_id.split(":", 1)[-1]
            if old_st is None:
                transitions[f"{step}: (new) -> {new_st}"] += 1
            elif new_st is None:
                transitions[f"{step}: {old_st} -> (gone)"] += 1
            else:
                transitions[f"{step}: {old_st} -> {new_st}"] += 1
        for label, count in sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0])):
            noun = "document" if count == 1 else "documents"
            # Path A aggregate cells are project-grain, not per-document.
            if label.startswith("A") or label.startswith("*"):
                out.append(f"{prefix}: {count} cell(s) {label}")
            else:
                out.append(f"{prefix}: {count} {noun} {label}")

        o_counts, n_counts = o.get("status_counts") or {}, n.get("status_counts") or {}
        for st in sorted(set(o_counts) | set(n_counts)):
            if o_counts.get(st, 0) != n_counts.get(st, 0):
                out.append(
                    f"{prefix}.status_counts[{st}]: "
                    f"{o_counts.get(st, 0)} -> {n_counts.get(st, 0)}"
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


def check_paths_project(project_id: str) -> bool:
    gp = paths_golden_path(project_id)
    if not gp.is_file():
        log(
            f"MISSING PATHS GOLDEN {project_id}: no baseline at {gp} — "
            "run with --update --paths to create it"
        )
        return False
    live = compute_paths_snapshot(project_id)
    golden = json.loads(gp.read_text(encoding="utf-8"))
    if _canonical(live) == _canonical(golden):
        log(f"OK   {project_id} paths: matches golden")
        return True
    log(f"DRIFT {project_id} paths:")
    for line in _paths_diff_report(golden, live) or [
        "  (content changed; see full snapshot)"
    ]:
        log(line)
    return False


def update_project(project_id: str) -> None:
    atomic_write(golden_path(project_id), _canonical(compute_snapshot(project_id)))
    log(f"wrote golden {golden_path(project_id)}")


def update_paths_project(project_id: str) -> None:
    dest = paths_golden_path(project_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, _canonical(compute_paths_snapshot(project_id)))
    log(f"wrote paths golden {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Golden-output regression harness for Layer 1 and path findings"
    )
    parser.add_argument(
        "--project", help="Single project id (default: all projects with matching output)"
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
    parser.add_argument(
        "--layer1",
        action="store_true",
        help="Include Layer 1 goldens (default when neither --layer1 nor --paths is set)",
    )
    parser.add_argument(
        "--paths",
        action="store_true",
        help="Include path findings goldens (default when neither flag is set)",
    )
    args = parser.parse_args()

    # Default: both scopes. Explicit flags narrow to the named scope(s).
    do_layer1 = args.layer1 or not args.paths
    do_paths = args.paths or not args.layer1
    if args.layer1 and args.paths:
        do_layer1 = do_paths = True
    if not args.layer1 and not args.paths:
        do_layer1 = do_paths = True

    all_ok = True

    if do_layer1:
        projects = [args.project] if args.project else discover_layer1_projects()
        if not projects:
            log("No projects with layer1/bucket-ledger.json found.")
            if not do_paths:
                return 1
        elif args.update:
            for pid in projects:
                update_project(pid)
        else:
            all_ok = all(check_project(pid) for pid in projects) and all_ok

    if do_paths:
        projects = [args.project] if args.project else discover_path_projects()
        if not projects:
            log("No projects with path_*/findings.json found.")
            if not do_layer1:
                return 1
        elif args.update:
            for pid in projects:
                update_paths_project(pid)
        else:
            all_ok = all(check_paths_project(pid) for pid in projects) and all_ok

    if args.check and not all_ok:
        log("")
        log(
            "Regression drift detected. If intended, re-run with --update to accept the new baseline."
        )
    return 0 if (args.update or all_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
