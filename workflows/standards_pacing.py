#!/usr/bin/env python3
"""workflows/standards_pacing.py — Path F (Standards & pacing) F1–F5 presence.

Educational note: Path F reviews YAG / pacing / scope-sequence / standards
overviews — course spine for teachers, not the student syllabus (Path G) and
not a daily Hunter lesson (Path A). Presence-first (F1–F4): scan Layer 0
excerpts with the standards_pacing checklist; fall back to source text when
the ledger is empty so labs still smoke. Auditor-only — never invent pacing
or TEKS. F5 stays stubbed (one-pager).
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
    Path(__file__).resolve().parent / "checklists" / "standards_pacing.yaml"
)


def load_standards_pacing_checklist() -> dict:
    """Load Path F checklist; empty dict if missing (tests can inject)."""
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


def f1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "F1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 / source excerpt inventory for this standards/pacing doc",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def f_presence_for_step(
    elements: list[dict], checklist: dict, step: str
) -> dict:
    """Run one F2–F4 step: PRESENT/PARTIAL/MISSING (+ optional soft-miss)."""
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
            note = "optional standards cue not found"
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
        # All optional (F4): PRESENT if any optional hit, else MISSING.
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
                    "element_type": "standards_objectives",
                    "excerpt": text,
                    "source_file": path.name,
                }
            ]
    return []


def _steps_for_doc(
    elements: list[dict], checklist: dict, doc_id: str
) -> dict:
    steps = {"F1": f1_inventory(elements, doc_id)}
    for step in ("F2", "F3", "F4"):
        steps[step] = f_presence_for_step(elements, checklist, step)
    steps["F5"] = {
        "step": "F5",
        "status": "STUB",
        "note": "emit Path F one-pager TBD",
    }
    return steps


def run_path_f_for_project(project_id: str) -> dict:
    """Run Path F presence extractors for each routed standards/pacing doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="standards_pacing")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_standards_pacing_checklist()

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
            "element_count": steps["F1"].get("element_count", 0),
        }
        for step in ("F1", "F2", "F3", "F4", "F5"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step in {"F2", "F3", "F4"}
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "standards_pacing",
        "path": "F",
        "lens": "Standards & pacing",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/standards_pacing.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
    }
    dest = root / "path_f" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path F → {len(doc_ids)} standards_pacing doc(s); F1–F4 presence extract")
    return out
