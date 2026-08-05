#!/usr/bin/env python3
"""workflows/exit_ticket.py — Path H stub (Exit ticket / formative check).

Educational note: Exit tickets are short end-of-lesson formative checks.
They are *not* quiz↔key pairs (Path B). Review them alone: prompt clarity,
target alignment, and whether the teacher can act on the signal tomorrow.
"""

from __future__ import annotations

import json

from audit_lib import atomic_write, classify_doc_type, log, project_dir
from route import load_route_map, routed_doc_ids


def run_path_h_for_project(project_id: str) -> dict:
    """Inventory exit-ticket docs routed to Path H (H1–H3 stub)."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="exit_ticket")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    sources = root / "sources"
    inventory = []
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        matches = list(sources.glob(f"doc_{did}_*")) if sources.is_dir() else []
        fname = matches[0].name if matches else (r.get("source_file") or did)
        dtype = r.get("doc_type") or classify_doc_type(fname)
        text = ""
        if matches:
            text = matches[0].read_text(encoding="utf-8", errors="replace")[:4000]
        low = text.lower()
        has_prompt = "?" in text or "exit" in low or bool(text.strip())
        inventory.append(
            {
                "doc_id": did,
                "doc_type": dtype,
                "graph_role": r.get("graph_role"),
                "H1": {
                    "status": "PRESENT" if has_prompt else "MISSING",
                    "note": "formative prompt / stem presence (stub)",
                },
                "H2": {
                    "status": "PRESENT"
                    if ("teks" in low or "objective" in low or "§" in text)
                    else "MISSING",
                    "note": "stub — learning-target / TEKS string presence only",
                },
                "H3": {
                    "status": "STUB",
                    "note": "actionable next-day signal TBD (not quiz↔key)",
                },
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "exit_ticket",
        "path": "H",
        "lens": "Exit ticket",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_h" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path H stub → {len(doc_ids)} exit_ticket doc(s)")
    return out
