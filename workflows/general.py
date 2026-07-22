#!/usr/bin/env python3
"""
workflows/general.py — Path C: general artifact review (worksheets, rubrics,
projects, presentations, and unknown/`other` types).

No longer a stub. It runs the SAME curriculum-agnostic artifact engine as Path B and
the artifact rung (artifact_rung.score_artifacts) over the docs the router placed on
Path C. Known roles get their per-type spec; unknown/`other` types get the generic
fallback and are logged to the feedback nursery (_loom_feedback.yaml) so a dedicated
Path can be grown later — the "graceful degradation" tier, now with a real presence
review instead of a placeholder. findings.json is a SUPERSET of the old stub output
(legacy C1/C2/C3 keys preserved).
"""

from __future__ import annotations

import json

from artifact_rung import score_artifacts
from audit_lib import atomic_write, log, project_dir
from route import load_route_map, routed_doc_ids

WORKFLOW_ID = "general"
PATH_LABEL = "C"


def _legacy_view(rec: dict, feedback: bool) -> dict:
    pres = rec["presence"]
    align = rec.get("alignment") or {}
    return {
        "doc_id": rec["doc_id"],
        "doc_type": rec["doc_type"],
        "role": rec["role"],
        "unit_id": rec["unit_id"],
        "title": rec["title"],
        "presence": pres,
        "alignment": align or None,
        "is_fallback": rec.get("is_fallback", False),
        # Legacy keys, now backed by the real presence gate.
        "C1": {
            "status": "PRESENT" if pres["gate_pass"] else "PARTIAL_OR_MISSING",
            "missing_required": pres.get("missing_required", []),
        },
        "C2": {
            "status": "ADVISORY" if align else "NOT_RUN",
            "cannot_assess": align.get("cannot_assess", False),
            "mean_band": align.get("mean_band"),
        },
        "C3": {
            "status": "LOGGED" if (feedback or rec.get("nursery")) else "OK",
            "feedback": bool(feedback or rec.get("nursery")),
            "note": "unknown type -> feedback nursery" if rec.get("nursery") else "",
        },
    }


def run_path_c_for_project(project_id: str, with_model: bool = False) -> dict:
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id=WORKFLOW_ID)
    route = load_route_map(project_id)
    fb_by_id = {r["doc_id"]: bool(r.get("feedback")) for r in route.get("routes") or []}
    try:
        records = score_artifacts(project_id, doc_ids=doc_ids, with_model=with_model)
    except FileNotFoundError as e:
        log(f"path C skipped: {e}")
        records = []
    by_id = {r["doc_id"]: r for r in records}

    inventory = []
    for did in sorted(doc_ids):
        rec = by_id.get(did)
        if rec is None:
            inventory.append(
                {
                    "doc_id": did,
                    "status": "NOT_DECOMPOSED",
                    "note": "routed to Path C but has no Layer 0 elements yet",
                }
            )
            continue
        inventory.append(_legacy_view(rec, fb_by_id.get(did, False)))

    gate_pass = sum(1 for r in records if r["presence"]["gate_pass"])
    nursery = sum(1 for r in records if r.get("nursery"))
    out = {
        "project_id": project_id,
        "workflow_id": WORKFLOW_ID,
        "path": PATH_LABEL,
        "status": "reviewed" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "summary": {
            "doc_count": len(doc_ids),
            "reviewed": len(records),
            "gate_pass": gate_pass,
            "nursery": nursery,
        },
        "inventory": inventory,
        "feedback_file": "_loom_feedback.yaml",
        "artifact_rung": "layer_artifact/ARTIFACT-RUNG.json",
    }
    dest = root / "path_c" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(
        f"path C → {len(records)}/{len(doc_ids)} general doc(s) reviewed "
        f"({gate_pass} passed presence gate, {nursery} nursery)"
    )
    return out
