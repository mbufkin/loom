#!/usr/bin/env python3
"""workflows/general.py — Path C stub (C1–C3) + feedback already logged by route.py."""

from __future__ import annotations

import json

from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_c_for_project(project_id: str) -> dict:
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="general")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    inventory = []
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        inventory.append(
            {
                "doc_id": did,
                "doc_type": r.get("doc_type"),
                "C1": {"status": "PRESENT", "note": "routed to general"},
                "C2": {"status": "STUB", "note": "generic checks TBD"},
                "C3": {
                    "status": "LOGGED" if r.get("feedback") else "OK",
                    "feedback": bool(r.get("feedback")),
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "general",
        "path": "C",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
        "feedback_file": "_loom_feedback.yaml",
    }
    dest = root / "path_c" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path C stub → {len(doc_ids)} general doc(s)")
    return out
