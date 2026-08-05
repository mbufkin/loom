#!/usr/bin/env python3
"""workflows/general.py — Path C (General feedback) C1–C5 nursery presence.

Educational note: Path C is the catch-all + growth queue — not a content lens.
Presence-first (C1–C4): inventory routed docs, confirm catch-all identity,
check feedback logging (route flag or `_loom_feedback.yaml`), and optionally
tag a nursery growth bucket. Do **not** copy TEKS/items/TE checks from other
paths. C5 stays stubbed (one-pager). Feedback append stays route.py's job.
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
    Path(__file__).resolve().parent / "checklists" / "general.yaml"
)


def load_general_checklist() -> dict:
    """Load Path C checklist; empty dict if missing (tests can inject)."""
    if not CHECKLIST_PATH.is_file():
        return {}
    data = load_yaml(CHECKLIST_PATH)
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.suffix == ".json" else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _feedback_doc_ids(root: Path) -> set[str]:
    """doc_ids logged in project `_loom_feedback.yaml` (if present)."""
    path = root / "_loom_feedback.yaml"
    if not path.is_file():
        return set()
    data = load_yaml(path)
    if not isinstance(data, list):
        return set()
    out: set[str] = set()
    for e in data:
        if isinstance(e, dict) and e.get("doc_id"):
            out.add(str(e["doc_id"]))
    return out


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


def c1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "C1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 / source excerpt inventory for this catch-all doc",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def c2_identity(route_row: dict, doc_id: str) -> dict:
    """Catch-all identity from the route row — not other lenses' content checks."""
    wf = (route_row.get("workflow_id") or "").strip()
    path = (route_row.get("path") or "").strip()
    dtype = (route_row.get("doc_type") or "").strip()
    reason = (route_row.get("reason") or "").strip()
    ok = wf == "general" and path == "C" and bool(dtype)
    return {
        "step": "C2",
        "status": "PRESENT" if ok else "MISSING",
        "note": "catch-all identity from route-map (workflow/path/doc_type)",
        "doc_id": doc_id,
        "workflow_id": wf,
        "path": path,
        "doc_type": dtype,
        "reason": reason,
    }


def c3_feedback(route_row: dict, doc_id: str, feedback_ids: set[str]) -> dict:
    """PRESENT if route.feedback or doc_id appears in `_loom_feedback.yaml`."""
    flagged = bool(route_row.get("feedback"))
    in_yaml = doc_id in feedback_ids
    if flagged or in_yaml:
        status = "PRESENT"
        note = (
            "feedback flagged on route-map"
            if flagged and in_yaml
            else (
                "feedback flagged on route-map"
                if flagged
                else "doc_id found in _loom_feedback.yaml"
            )
        )
    else:
        status = "MISSING"
        note = "no route.feedback flag and not in _loom_feedback.yaml"
    return {
        "step": "C3",
        "status": status,
        "note": note,
        "route_feedback": flagged,
        "in_feedback_yaml": in_yaml,
    }


def c_presence_for_step(
    elements: list[dict], checklist: dict, step: str
) -> dict:
    """Run optional C4 growth-bucket step (soft rollup)."""
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
            note = "optional growth-bucket cue not found"
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
            # Include filename in excerpt so C4 can see presentation/coach cues
            # even when body is thin (nursery signals often live in the name).
            excerpt = f"{path.name}\n{text}"
            return [
                {
                    "doc_id": doc_id,
                    "element_id": f"{doc_id}:src",
                    "element_type": "general",
                    "excerpt": excerpt,
                    "source_file": path.name,
                }
            ]
    return []


def _steps_for_doc(
    elements: list[dict],
    checklist: dict,
    doc_id: str,
    *,
    route_row: dict,
    feedback_ids: set[str],
) -> dict:
    steps = {
        "C1": c1_inventory(elements, doc_id),
        "C2": c2_identity(route_row, doc_id),
        "C3": c3_feedback(route_row, doc_id, feedback_ids),
        "C4": c_presence_for_step(elements, checklist, "C4"),
        "C5": {
            "step": "C5",
            "status": "STUB",
            "note": "emit Path C one-pager / growth digest TBD",
        },
    }
    return steps


def run_path_c_for_project(project_id: str) -> dict:
    """Run Path C nursery presence extractors for each routed general doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="general")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_general_checklist()
    feedback_ids = _feedback_doc_ids(root)

    inventory = []
    steps_by_doc: dict[str, dict] = {}
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        sf = r.get("source_file") or did
        dtype = r.get("doc_type") or classify_doc_type(sf)
        elements = _elements_for_doc(ledger, did)
        if not elements:
            elements = _source_text_elements(root, did, sf)
        steps = _steps_for_doc(
            elements,
            checklist,
            did,
            route_row=r,
            feedback_ids=feedback_ids,
        )
        steps_by_doc[did] = steps
        row = {
            "doc_id": did,
            "doc_type": dtype,
            "element_count": steps["C1"].get("element_count", 0),
            "feedback": bool(r.get("feedback")),
        }
        for step in ("C1", "C2", "C3", "C4", "C5"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step == "C4"
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "general",
        "path": "C",
        "lens": "General feedback",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/general.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
        "feedback_file": "_loom_feedback.yaml",
    }
    dest = root / "path_c" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path C → {len(doc_ids)} general doc(s); C1–C4 nursery presence")
    return out
