#!/usr/bin/env python3
"""workflows/sylibuis.py — Path G stub (Sylibuis)."""

from __future__ import annotations

import json

from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_g_for_project(project_id: str) -> dict:
    """Inventory docs routed to Path G (sylibuis).

    Educational note: keep Path G as a single lens; grow depth as G1–Gn
    checklists later rather than inventing Path H…Z for each filename.
    """
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="sylibuis")
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
                "G1": {
                    "status": "PRESENT",
                    "note": "routed to sylibuis",
                },
                "G2": {
                    "status": "STUB",
                    "note": "sylibuis quality checklist TBD",
                },
                "G3": {
                    "status": "STUB",
                    "note": "alignment / pairing rules TBD",
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "sylibuis",
        "path": "G",
        "lens": "Sylibuis",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_g" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path G stub → {len(doc_ids)} sylibuis doc(s)")
    return out
