#!/usr/bin/env python3
"""workflows/teacher_support.py — Path D stub (Teacher support / TE)."""

from __future__ import annotations

import json

from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_d_for_project(project_id: str) -> dict:
    """Inventory TE / educator-guide docs routed to Path D.

    Educational note: deep TE review (lesson facilitation, anticipated
    misconceptions) grows as D1–Dn checklists later — not as new path letters.
    """
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="teacher_support")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    inventory = []
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        inventory.append(
            {
                "doc_id": did,
                "doc_type": r.get("doc_type"),
                "graph_role": r.get("graph_role"),
                "D1": {
                    "status": "PRESENT",
                    "note": "routed to teacher_support (TE / educator guide)",
                },
                "D2": {
                    "status": "STUB",
                    "note": "facilitation / misconception supports TBD",
                },
                "D3": {
                    "status": "STUB",
                    "note": "alignment to graph Lesson nodes TBD",
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "teacher_support",
        "path": "D",
        "lens": "Teacher support",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_d" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path D stub → {len(doc_ids)} teacher_support doc(s)")
    return out
