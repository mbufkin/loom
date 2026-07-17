#!/usr/bin/env python3
"""
workflows/run_paths.py — Run Path A/B/C after route-map exists.

Also refreshes unit LESSON-PLAN plates after Path A.
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


def _title_map(project_id: str) -> dict[str, str]:
    root = project_dir(project_id)
    out: dict[str, str] = {}
    sources = root / "sources"
    if not sources.is_dir():
        return out
    for p in sources.glob("doc_*.txt"):
        did = doc_id_from_filename(p.name)
        name = p.stem
        title = name.split("_", 2)[-1].replace("_", " ") if name.startswith("doc_") else name
        out[did] = title
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loom Path A/B/C workflows")
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

    # Handoff aggregate for place-into-units
    handoff = {
        "project_id": args.project,
        "workflows": [
            {
                "doc_id": "*",
                "workflow_id": "lesson_plan",
                "path": "A",
                "status": a.get("status"),
                "findings_path": "path_a/findings.json",
                "emit_paths": a.get("emit_paths") or [],
                "summary": a.get("steps"),
            },
            {
                "doc_id": "*",
                "workflow_id": "quiz",
                "path": "B",
                "status": b.get("status"),
                "findings_path": "path_b/findings.json",
                "emit_paths": ["path_b/findings.json"],
                "summary": {"doc_count": len(b.get("doc_ids") or [])},
            },
            {
                "doc_id": "*",
                "workflow_id": "general",
                "path": "C",
                "status": c.get("status"),
                "findings_path": "path_c/findings.json",
                "emit_paths": ["path_c/findings.json"],
                "summary": {"doc_count": len(c.get("doc_ids") or [])},
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

    log("path workflows done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
