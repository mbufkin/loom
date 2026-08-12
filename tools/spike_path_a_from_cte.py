#!/usr/bin/env python3
"""SPIKE — Path A review using CTE spike kinds (no re-type / no route.py cascade).

Educational note
----------------
CTE Pass 1 already decided artifact_kind. Docs with lesson_plan → Path A.
This runner writes a thin route-map from those kinds, then calls mainline
``run_path_a_for_project`` + LESSON-PLAN plate refresh so we can inspect
Path A output without redoing graph sort.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_lib import load_config, load_manifest, log, project_dir  # noqa: E402
from schema_validate import raise_on_errors, validate_route_map  # noqa: E402
from workflows.lesson_plan import (  # noqa: E402
    run_path_a_for_project,
    write_unit_lesson_plans_from_path_a,
)

LAB_ID = "lab-graph-cte-cattle"
PATH_BY_KIND = {
    "lesson_plan": "A",
    "assessment": "B",
    "student_practice": "E",
    "teacher_support": "D",
    "standards_pacing": "F",
    "other": "C",
}
WORKFLOW_BY_PATH = {
    "A": "lesson_plan",
    "B": "quiz",
    "C": "general",
    "D": "teacher_support",
    "E": "student_practice",
    "F": "standards_pacing",
}
LENS_LABEL = {
    "lesson_plan": "Lesson",
    "quiz": "Assessment",
    "general": "General feedback",
    "teacher_support": "Teacher support",
    "student_practice": "Student practice",
    "standards_pacing": "Standards & pacing",
    "syllabus": "Syllabus",
    "exit_ticket": "Exit ticket",
}


def lab_root() -> Path:
    return project_dir(LAB_ID)


def load_cte_lesson_plan_docs(lab: Path) -> list[dict]:
    """Return [{source_file, doc_id, unit_id, kind}] for CTE lesson_plan docs."""
    latest = (lab / "graph" / "LATEST").read_text(encoding="utf-8").strip()
    units_dir = lab / "graph" / latest / "units"
    if not units_dir.is_dir():
        raise SystemExit(f"missing CTE units under {units_dir}")

    ledger = json.loads((lab / "layer0" / "ledger.json").read_text(encoding="utf-8"))
    el_counts: Counter[str] = Counter()
    doc_ids: dict[str, str] = {}
    for e in ledger:
        sf = e.get("source_file")
        if not sf:
            continue
        el_counts[sf] += 1
        doc_ids.setdefault(sf, e.get("doc_id") or sf)

    out: list[dict] = []
    for udir in sorted(units_dir.iterdir()):
        if not udir.is_dir():
            continue
        kinds = json.loads((udir / "kinds.json").read_text(encoding="utf-8"))
        for sf, row in sorted(kinds.items()):
            kind = (row or {}).get("artifact_kind")
            if kind != "lesson_plan":
                continue
            out.append(
                {
                    "source_file": sf,
                    "doc_id": doc_ids.get(sf) or sf,
                    "unit_id": udir.name,
                    "kind": kind,
                    "element_count": el_counts.get(sf, 0),
                }
            )
    if not out:
        raise SystemExit(f"no lesson_plan docs in CTE run {latest}")
    return out


def write_thin_route_map(lab: Path, docs: list[dict]) -> Path:
    """Python kind→Path handoff — only Path A docs for this spike."""
    routes = []
    for d in docs:
        path = PATH_BY_KIND[d["kind"]]
        wf = WORKFLOW_BY_PATH[path]
        routes.append(
            {
                "doc_id": d["doc_id"],
                "doc_type": "lesson_plan",
                "workflow_id": wf,
                "path": path,
                "lens": LENS_LABEL[wf],
                "reason": "cte-spike artifact_kind=lesson_plan → Path A (thin table)",
                "feedback": False,
                "confidence": 1.0,
                "source_file": d["source_file"],
                "element_count": d["element_count"],
                "graph_role": None,
                "unit_id": d["unit_id"],
            }
        )
    out = {
        "project_id": LAB_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lenses": LENS_LABEL,
        "counts": {"lesson_plan": len(routes)},
        "unrouted_ledger_doc_ids": [],
        "feedback_path": None,
        "graph_hints": 0,
        "routes": routes,
        "method": "spike-path-a-from-cte",
    }
    raise_on_errors(validate_route_map(out), f"route map {LAB_ID}")
    dest = lab / "layer0" / "route-map.json"
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return dest


def title_map_from_sources(lab: Path) -> dict[str, str]:
    """Map doc_id → short title for plate writer (HTML sources, not doc_*.txt)."""
    out: dict[str, str] = {}
    sources = lab / "sources"
    if not sources.is_dir():
        return out
    for p in sources.iterdir():
        if not p.is_file() and not p.is_symlink():
            continue
        # ledger doc_id for these files is the full basename including .html
        did = p.name
        stem = p.stem
        if "__" in stem:
            label = stem.split("__", 1)[1].replace("-", " ")
        else:
            label = stem.replace("-", " ")
        out[did] = label.title()
    return out


def write_spike_result(
    lab: Path,
    *,
    docs: list[dict],
    findings: dict,
    plate_paths: list[Path],
    model_cfg_ok: bool,
) -> Path:
    steps = findings.get("steps") or {}
    a5 = steps.get("A5") or {}
    a6 = findings.get("a6_fields") or {}
    a2 = steps.get("A2") or {}
    lines = [
        "# Path A spike — RESULT (from CTE kinds)",
        "",
        f"**Lab:** `{LAB_ID}`",
        f"**CTE LATEST:** `{(lab / 'graph' / 'LATEST').read_text().strip()}`",
        f"**Model A6:** {'attempted (LOOM_CONFIG)' if model_cfg_ok else 'unavailable → code fallback'}",
        "",
        "## Docs on Path A (from CTE lesson_plan)",
        "",
    ]
    for d in docs:
        lines.append(
            f"- `{d['source_file']}` (unit `{d['unit_id']}`, "
            f"{d['element_count']} ledger elements)"
        )

    lines += [
        "",
        "## Path A outputs to review",
        "",
        f"- Findings: `{lab / 'path_a' / 'findings.json'}`",
        f"- Status: `{findings.get('status')}`",
        f"- A1 element_count: `{(steps.get('A1') or {}).get('element_count')}`",
        f"- A2 standards: `{a2.get('status') or a2}`",
        f"- A5 Hunter: `{json.dumps(a5, ensure_ascii=False)[:240]}…`"
        if a5
        else "- A5 Hunter: _(empty)_",
        f"- A6 fields placed: `{len(a6)}` keys",
        "",
        "### Plates",
        "",
    ]
    if plate_paths:
        for p in plate_paths:
            lines.append(f"- `{p}`")
    else:
        lines.append("- _(none written)_")

    lines += [
        "",
        "## How to read",
        "",
        "Compare against `docs/PATH-A-LESSON-PLAN.md` (A1–A8).",
        "Ask: are Hunter / standards / A6 placements useful for CTE multi-class LPs?",
        "",
    ]
    dest = lab / "path_a" / "SPIKE-RESULT.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="SPIKE Path A from CTE lesson_plan docs")
    ap.add_argument(
        "--no-model",
        action="store_true",
        help="A6 code fallback only",
    )
    args = ap.parse_args()

    lab = lab_root()
    if not (lab / "layer0" / "ledger.json").is_file():
        log(f"ERROR missing {lab / 'layer0' / 'ledger.json'}")
        return 2

    docs = load_cte_lesson_plan_docs(lab)
    log(f"CTE → Path A docs: {len(docs)}")
    for d in docs:
        log(f"  {d['source_file']} ({d['element_count']} els)")

    route_path = write_thin_route_map(lab, docs)
    log(f"wrote thin route-map → {route_path}")

    use_model = not args.no_model
    model_cfg_ok = False
    if use_model:
        try:
            load_config()
            model_cfg_ok = True
        except Exception as exc:
            log(f"WARN config unavailable ({exc}); A6 may fall back")

    findings = run_path_a_for_project(LAB_ID, use_model=use_model)
    log(f"Path A status={findings.get('status')} emit={findings.get('emit_paths')}")

    manifest = load_manifest(lab / "manifest.yaml")
    titles = title_map_from_sources(lab)
    plates = write_unit_lesson_plans_from_path_a(
        LAB_ID, manifest=manifest, title_map=titles
    )
    log(f"plates written: {len(plates)}")

    result = write_spike_result(
        lab,
        docs=docs,
        findings=findings,
        plate_paths=plates,
        model_cfg_ok=model_cfg_ok and use_model,
    )
    log(f"DONE Path A spike → {result}")
    return 0 if findings.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
