#!/usr/bin/env python3
"""
workflows/quiz.py — Path B: assessment artifact review (quizzes, exit tickets,
answer keys).

No longer a stub. It now runs the SAME curriculum-agnostic artifact engine as the
artifact rung (artifact_rung.score_artifacts) over just the docs the router placed
on Path B, so the review is real (element-based presence gate + evidence-cited
detail) and identical in shape to Path C and the rung. The findings.json is a
SUPERSET of the old stub output — the legacy B1/B2/B3 keys are still emitted (derived
from the real presence result) so nothing downstream breaks, plus a `documents`
block with the full per-doc records and a pointer to ARTIFACT-RUNG.json.
"""

from __future__ import annotations

import json

from artifact_rung import score_artifacts
from audit_lib import atomic_write, log, project_dir
from route import routed_doc_ids

WORKFLOW_ID = "quiz"
PATH_LABEL = "B"


def _legacy_view(rec: dict) -> dict:
    """Re-express one artifact record in the old stub's B1/B2/B3 shape (backward
    compatibility) alongside the real presence/alignment detail."""
    pres = rec["presence"]
    align = rec.get("alignment") or {}
    return {
        "doc_id": rec["doc_id"],
        "doc_type": rec["doc_type"],
        "role": rec["role"],
        "unit_id": rec["unit_id"],
        "title": rec["title"],
        # Real, element-based results (the actual review).
        "presence": pres,
        "alignment": align or None,
        # Legacy keys (now backed by the deterministic presence gate, not a string scan).
        "B1": {
            "has_items": pres["gate_pass"],
            "status": "PRESENT" if pres["gate_pass"] else "PARTIAL_OR_MISSING",
            "missing_required": pres.get("missing_required", []),
        },
        "B2": {
            "status": "ADVISORY" if align else "NOT_RUN",
            "cannot_assess": align.get("cannot_assess", False),
            "mean_band": align.get("mean_band"),
            "note": "objective/TEKS alignment (model, advisory)",
        },
        "B3": {"status": "OK", "note": "auditor-only — correctness never asserted"},
    }


def run_path_b_for_project(project_id: str, with_model: bool = False) -> dict:
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id=WORKFLOW_ID)
    try:
        records = score_artifacts(project_id, doc_ids=doc_ids, with_model=with_model)
    except FileNotFoundError as e:
        # No Layer 0 ledger yet — degrade honestly rather than crash the path run.
        log(f"path B skipped: {e}")
        records = []
    by_id = {r["doc_id"]: r for r in records}

    inventory = []
    for did in sorted(doc_ids):
        rec = by_id.get(did)
        if rec is None:
            # Routed to Path B but not yet decomposed into Layer 0 elements — honest
            # placeholder rather than a fabricated review (never silently dropped).
            inventory.append(
                {
                    "doc_id": did,
                    "status": "NOT_DECOMPOSED",
                    "note": "routed to Path B but has no Layer 0 elements yet",
                }
            )
            continue
        inventory.append(_legacy_view(rec))

    gate_pass = sum(1 for r in records if r["presence"]["gate_pass"])
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
        },
        "inventory": inventory,
        "artifact_rung": "layer_artifact/ARTIFACT-RUNG.json",
    }
    dest = root / "path_b" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(
        f"path B → {len(records)}/{len(doc_ids)} assessment doc(s) reviewed "
        f"({gate_pass} passed presence gate)"
    )
    return out
