#!/usr/bin/env python3
"""
workflows/run_paths.py — Run Path A–G after route-map exists.

Also refreshes unit LESSON-PLAN plates after Path A.
See docs/PATHS.md for the A–G lens contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python3 workflows/run_paths.py` from repo root or workflows/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audit_lib import (
    doc_id_from_filename,
    load_manifest,
    log,
    project_dir,
    validate_slug_id,
)
from workflows.general import run_path_c_for_project
from workflows.lesson_plan import (
    run_path_a_for_project,
    write_unit_lesson_plans_from_path_a,
)
from workflows.quiz import run_path_b_for_project
from workflows.standards_pacing import run_path_f_for_project
from workflows.student_practice import run_path_e_for_project
from workflows.sylibuis import run_path_g_for_project
from workflows.teacher_support import run_path_d_for_project


def _title_map(project_id: str) -> dict[str, str]:
    root = project_dir(project_id)
    out: dict[str, str] = {}
    sources = root / "sources"
    if not sources.is_dir():
        return out
    for p in sources.rglob("doc_*.txt"):
        did = doc_id_from_filename(p.name)
        name = p.stem
        title = (
            name.split("_", 2)[-1].replace("_", " ")
            if name.startswith("doc_")
            else name
        )
        out[did] = title
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loom Path A–G review lenses")
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="Path A A6 uses code fallback only (no model place)",
    )
    args = parser.parse_args()
    validate_slug_id(args.project, "project id")
    root = project_dir(args.project)
    if not (root / "layer0" / "route-map.json").is_file():
        log("ERROR: missing layer0/route-map.json — run route.py first")
        return 1

    a = run_path_a_for_project(args.project, use_model=not args.no_model)
    b = run_path_b_for_project(args.project)
    c = run_path_c_for_project(args.project)
    d = run_path_d_for_project(args.project)
    e = run_path_e_for_project(args.project)
    f = run_path_f_for_project(args.project)
    g = run_path_g_for_project(args.project)

    # Handoff aggregate for place-into-units / UI
    handoff = {
        "project_id": args.project,
        "workflows": [
            {
                "doc_id": "*",
                "workflow_id": "lesson_plan",
                "path": "A",
                "lens": "Lesson",
                "status": a.get("status"),
                "findings_path": "path_a/findings.json",
                "emit_paths": a.get("emit_paths") or [],
                "summary": a.get("steps"),
            },
            {
                "doc_id": "*",
                "workflow_id": "quiz",
                "path": "B",
                "lens": "Assessment",
                "status": b.get("status"),
                "findings_path": "path_b/findings.json",
                "emit_paths": ["path_b/findings.json"],
                "summary": {"doc_count": len(b.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "general",
                "path": "C",
                "lens": "General feedback",
                "status": c.get("status"),
                "findings_path": "path_c/findings.json",
                "emit_paths": ["path_c/findings.json"],
                "summary": {"doc_count": len(c.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "teacher_support",
                "path": "D",
                "lens": "Teacher support",
                "status": d.get("status"),
                "findings_path": "path_d/findings.json",
                "emit_paths": ["path_d/findings.json"],
                "summary": {"doc_count": len(d.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "student_practice",
                "path": "E",
                "lens": "Student practice",
                "status": e.get("status"),
                "findings_path": "path_e/findings.json",
                "emit_paths": ["path_e/findings.json"],
                "summary": {"doc_count": len(e.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "standards_pacing",
                "path": "F",
                "lens": "Standards & pacing",
                "status": f.get("status"),
                "findings_path": "path_f/findings.json",
                "emit_paths": ["path_f/findings.json"],
                "summary": {"doc_count": len(f.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "sylibuis",
                "path": "G",
                "lens": "Sylibuis",
                "status": g.get("status"),
                "findings_path": "path_g/findings.json",
                "emit_paths": ["path_g/findings.json"],
                "summary": {"doc_count": len(g.get("doc_ids") or [])},
            },
        ],
    }
    dest = root / "layer0" / "workflow-handoff.json"
    dest.write_text(json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8")

    # Refresh unit LESSON-PLAN plates
    try:
        manifest = load_manifest(root / "manifest.yaml")
        write_unit_lesson_plans_from_path_a(
            args.project, manifest=manifest, title_map=_title_map(args.project)
        )
    except Exception as e:
        log(f"WARN: unit LESSON-PLAN refresh skipped: {e}")

    log("path workflows done (A–G)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
