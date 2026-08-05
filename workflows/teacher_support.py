#!/usr/bin/env python3
"""workflows/teacher_support.py — Path D (Teacher support) D1–D5 presence.

Educational note: Path D reviews teacher editions / educator guides /
implementation guides — adult-facing facilitation support, not student
practice (Path E) and not the YAG/pacing spine (Path F). Presence-first
(D1–D4): scan Layer 0 excerpts with the teacher_support checklist; fall
back to source text when the ledger is empty so labs still smoke.
Auditor-only — never invent facilitation scripts. D5 stays stubbed
(one-pager). Graph↔Lesson alignment stays out of presence depth.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_lib import (
    atomic_write,
    classify_doc_type,
    load_yaml,
    log,
    project_dir,
)
from route import load_route_map, routed_doc_ids
from unit_plan_fill import _trunc

CHECKLIST_PATH = (
    Path(__file__).resolve().parent / "checklists" / "teacher_support.yaml"
)


def load_teacher_support_checklist() -> dict:
    """Load Path D checklist; empty dict if missing (tests can inject)."""
    if not CHECKLIST_PATH.is_file():
        return {}
    data = load_yaml(CHECKLIST_PATH)
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.suffix == ".json" else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _elements_for_doc(ledger: list, doc_id: str) -> list[dict]:
    return [e for e in ledger if e.get("doc_id") == doc_id]


def _by_type(elements: list[dict]) -> dict[str, list[dict]]:
    out: defaultdict[str, list[dict]] = defaultdict(list)
    for e in elements:
        et = e.get("element_type") or "unclear"
        for token in str(et).split("|"):
            token = token.strip()
            if token:
                out[token].append(e)
    return out


def _field_hits(elements: list[dict], field: dict) -> list[dict]:
    keywords = [str(k) for k in (field.get("keywords") or [])]
    hits: list[dict] = []
    seen: set[str] = set()
    for e in elements:
        ex = e.get("excerpt") or ""
        low = ex.lower()
        if keywords and not any(k.lower() in low for k in keywords):
            continue
        if not keywords:
            continue
        eid = str(e.get("element_id") or id(e))
        if eid in seen:
            continue
        seen.add(eid)
        hits.append(e)
    return hits


def _fields_for_step(checklist: dict, step: str) -> list[dict]:
    out: list[dict] = []
    for section_id, section in (checklist.get("sections") or {}).items():
        if section.get("step") != step:
            continue
        for field in section.get("fields") or []:
            out.append(
                {
                    **field,
                    "section_id": section_id,
                    "section_label": section.get("label") or section_id,
                }
            )
    return out


def d1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "D1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 / source excerpt inventory for this TE / guide doc",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def d_presence_for_step(
    elements: list[dict], checklist: dict, step: str
) -> dict:
    """Run one D2–D4 step: PRESENT/PARTIAL/MISSING (+ optional soft-miss)."""
    fields_out = []
    present = 0
    required = 0
    for field in _fields_for_step(checklist, step):
        hits = _field_hits(elements, field)
        optional = bool(field.get("optional"))
        if hits:
            status = "PRESENT"
            present += 1
            required += 1
            note = ""
        elif optional:
            status = "MISSING"
            note = "optional spine cue not found"
        else:
            status = "MISSING"
            required += 1
            note = "not found in excerpts"
        fields_out.append(
            {
                "id": field.get("id"),
                "label": field.get("label") or field.get("id"),
                "status": status,
                "count": len(hits),
                "cites": [_trunc(h.get("excerpt") or "") for h in hits[:3]],
                "note": note,
                "optional": optional,
            }
        )
    if required == 0:
        # All optional (D4): PRESENT if any optional hit, else MISSING.
        opt_hits = sum(1 for f in fields_out if f["status"] == "PRESENT")
        rollup = "PRESENT" if opt_hits else "MISSING"
    elif present == required:
        rollup = "PRESENT"
    elif present == 0:
        rollup = "MISSING"
    else:
        rollup = "PARTIAL"
    return {
        "step": step,
        "status": rollup,
        "present": present,
        "required": required,
        "fields": fields_out,
    }


def _source_text_elements(root: Path, doc_id: str, source_file: str) -> list[dict]:
    """Build synthetic elements from source text when ledger is empty."""
    sources = root / "sources"
    candidates: list[Path] = []
    if source_file:
        candidates.append(sources / Path(source_file).name)
    candidates.extend(sources.glob(f"doc_{doc_id}_*"))
    candidates.extend(sources.glob(f"*{doc_id}*"))
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")[:8000]
            if not text.strip():
                continue
            return [
                {
                    "doc_id": doc_id,
                    "element_id": f"{doc_id}:src",
                    "element_type": "teacher_support",
                    "excerpt": text,
                    "source_file": path.name,
                }
            ]
    return []


def _steps_for_doc(
    elements: list[dict], checklist: dict, doc_id: str
) -> dict:
    steps = {"D1": d1_inventory(elements, doc_id)}
    for step in ("D2", "D3", "D4"):
        steps[step] = d_presence_for_step(elements, checklist, step)
    steps["D5"] = {
        "step": "D5",
        "status": "STUB",
        "note": "emit Path D one-pager TBD",
    }
    return steps


def run_path_d_for_project(project_id: str) -> dict:
    """Run Path D presence extractors for each routed TE / guide doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="teacher_support")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_teacher_support_checklist()

    inventory = []
    steps_by_doc: dict[str, dict] = {}
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        sf = r.get("source_file") or did
        dtype = r.get("doc_type") or classify_doc_type(sf)
        elements = _elements_for_doc(ledger, did)
        if not elements:
            elements = _source_text_elements(root, did, sf)
        steps = _steps_for_doc(elements, checklist, did)
        steps_by_doc[did] = steps
        row = {
            "doc_id": did,
            "doc_type": dtype,
            "graph_role": r.get("graph_role"),
            "element_count": steps["D1"].get("element_count", 0),
        }
        for step in ("D1", "D2", "D3", "D4", "D5"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step in {"D2", "D3", "D4"}
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "teacher_support",
        "path": "D",
        "lens": "Teacher support",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/teacher_support.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
    }
    dest = root / "path_d" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path D → {len(doc_ids)} teacher_support doc(s); D1–D4 presence extract")
    return out
