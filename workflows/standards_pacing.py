#!/usr/bin/env python3
"""workflows/standards_pacing.py — Path F stub (Standards & pacing)."""

from __future__ import annotations

import json

from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_f_for_project(project_id: str) -> dict:
    """Inventory scope/sequence / pacing / standards overview docs on Path F."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="standards_pacing")
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
                "F1": {
                    "status": "PRESENT",
                    "note": "routed to standards_pacing",
                },
                "F2": {
                    "status": "STUB",
                    "note": "standards coverage vs unit lessons TBD",
                },
                "F3": {
                    "status": "STUB",
                    "note": "pacing ↔ calendar coherence TBD",
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "standards_pacing",
        "path": "F",
        "lens": "Standards & pacing",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_f" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path F stub → {len(doc_ids)} standards_pacing doc(s)")
    return out
