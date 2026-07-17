#!/usr/bin/env python3
"""workflows/quiz.py — Path B stub (B1–B3)."""

from __future__ import annotations

import json
from pathlib import Path

from audit_lib import atomic_write, classify_doc_type, doc_id_from_filename, log, project_dir
from route import routed_doc_ids


def run_path_b_for_project(project_id: str) -> dict:
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="quiz")
    sources = root / "sources"
    inventory = []
    for did in sorted(doc_ids):
        # Find source file
        matches = list(sources.glob(f"doc_{did}_*")) if sources.is_dir() else []
        fname = matches[0].name if matches else did
        dtype = classify_doc_type(fname)
        text = ""
        if matches:
            text = matches[0].read_text(encoding="utf-8", errors="replace")[:4000]
        low = text.lower()
        has_key = "answer" in low or dtype == "answer_key"
        has_items = "?" in text or "question" in low
        inventory.append(
            {
                "doc_id": did,
                "doc_type": dtype,
                "B1": {
                    "has_items": has_items,
                    "has_answer_key_signal": has_key,
                    "status": "PRESENT" if (has_items or has_key) else "MISSING",
                },
                "B2": {
                    "status": "PRESENT" if ("teks" in low or "§" in text) else "MISSING",
                    "note": "stub — TEKS string presence only",
                },
                "B3": {"status": "STUB", "note": "formative vs summative TBD"},
            }
        )
    out = {
        "project_id": project_id,
        "workflow_id": "quiz",
        "path": "B",
        "status": "stub" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "inventory": inventory,
    }
    dest = root / "path_b" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path B stub → {len(doc_ids)} quiz/assessment doc(s)")
    return out
