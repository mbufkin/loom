#!/usr/bin/env python3
"""workflows/student_practice.py — Path E stub (Student practice)."""

from __future__ import annotations

import json

from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_e_for_project(project_id: str) -> dict:
    """Inventory learn/practice/succeed/worksheet docs on Path E."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="student_practice")
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
                "E1": {
                    "status": "PRESENT",
                    "note": "routed to student_practice",
                },
                "E2": {
                    "status": "STUB",
                    "note": "practice ↔ lesson objective alignment TBD",
                },
                "E3": {
                    "status": "STUB",
                    "note": "answer key / succeed pairing TBD",
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "student_practice",
        "path": "E",
        "lens": "Student practice",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_e" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path E stub → {len(doc_ids)} student_practice doc(s)")
    return out
