#!/usr/bin/env python3
"""workflows/syllabus.py — Path G (Syllabus) G1–G9.

Educational note: Path G audits a course-level student/family syllabus —
identity, outcomes, grading, TEKS timeline, policies, CTE extras — not a
Hunter lesson plate (Path A) and not YAG/pacing alone (Path F).

Presence-first (G1–G7): scan Layer 0 excerpts with a syllabus checklist YAML.
Auditor-only — blank / MISSING = not found; never invent syllabus text.
G8 (cross-artifact) and G9 (one-pager) stay stubbed until presence is trusted.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_lib import load_yaml, log, project_dir
from route import load_route_map, routed_doc_ids
from unit_plan_fill import _trunc
from workflows.findings_io import write_path_findings

CHECKLIST_PATH = (
    Path(__file__).resolve().parent / "checklists" / "syllabus.yaml"
)

# Doc-level cues that optional CTE fields (safety / WBL / ack) should be required.
CTE_DOC_SIGNALS = (
    "cte",
    "career and technical",
    "career prep",
    "internship",
    "work-based",
    "work based",
    "wbl",
    "practicum",
    "shop",
    "lab safety",
    "ppe",
    "industry partner",
    "training plan",
)


def load_syllabus_checklist() -> dict:
    """Load Path G checklist; empty dict if missing (tests can inject)."""
    if not CHECKLIST_PATH.is_file():
        return {}
    data = load_yaml(CHECKLIST_PATH)
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.suffix == ".json" else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _elements_for_doc(ledger: list, doc_id: str) -> list[dict]:
    """Scope excerpts to one syllabus doc — avoid Path A–style cite bleed."""
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
    """Keyword-first presence (syllabus text is mostly logistics/unclear).

    Educational note: Path A Hunter can lean on element_types because Layer 0
    tags daily lesson slots. Syllabus sections rarely get distinct types, so
    type-alone PRESENT would false-hit nearly every logistics excerpt. Require
    a keyword match when keywords are listed; fall back to types only when not.
    """
    keywords = [str(k) for k in (field.get("keywords") or [])]
    etypes = set(field.get("element_types") or [])
    hits: list[dict] = []
    seen: set[str] = set()
    for e in elements:
        ex = e.get("excerpt") or ""
        low = ex.lower()
        if keywords:
            if not any(k.lower() in low for k in keywords):
                continue
        else:
            et = e.get("element_type") or ""
            if not any(t in et for t in etypes):
                continue
        eid = str(e.get("element_id") or id(e))
        if eid in seen:
            continue
        seen.add(eid)
        hits.append(e)
    return hits


def _doc_has_cte_signals(elements: list[dict]) -> bool:
    blob = " ".join((e.get("excerpt") or "") for e in elements).lower()
    return any(sig in blob for sig in CTE_DOC_SIGNALS)


def g1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "G1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 excerpt inventory for this syllabus doc",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def _fields_for_step(checklist: dict, step: str) -> list[dict]:
    """Fields belonging to a G2–G7 section (step stamped on the section)."""
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


def g_presence_for_step(
    elements: list[dict],
    checklist: dict,
    step: str,
    *,
    cte_signaled: bool,
) -> dict:
    """Run one G2–G7 step: PRESENT/PARTIAL/MISSING/OPTIONAL_ABSENT
    (field-level NOT_SIGNALED for optional CTE when the doc has no CTE cues)."""
    fields_out = []
    present = 0
    required = 0
    for field in _fields_for_step(checklist, step):
        hits = _field_hits(elements, field)
        optional = bool(field.get("optional"))
        cte_field = bool(field.get("cte_signal"))
        if hits:
            status = "PRESENT"
            present += 1
            required += 1
            note = ""
        elif optional and cte_field and not cte_signaled:
            # Soft gate: don't fail WBL/safety/ack when the syllabus isn't CTE-shaped.
            status = "NOT_SIGNALED"
            note = "optional CTE field; no CTE cues in this document"
        else:
            status = "MISSING"
            required += 1
            note = "not found in Layer 0 excerpts"
        fields_out.append(
            {
                "id": field.get("id"),
                "label": field.get("label") or field.get("id"),
                "status": status,
                "count": len(hits),
                "cites": [_trunc(h.get("excerpt") or "") for h in hits[:3]],
                "note": note,
            }
        )
    # Rollup: all required fields present → PRESENT; some → PARTIAL; none → MISSING.
    # required == 0 means every field was soft-gated (optional CTE + no CTE cues in
    # the doc) — that is OPTIONAL_ABSENT, not a finding. The shared step-status
    # vocabulary has no separate "not run" token for this case.
    if required == 0:
        opt_hits = sum(1 for f in fields_out if f["status"] == "PRESENT")
        rollup = "PRESENT" if opt_hits else "OPTIONAL_ABSENT"
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


def _steps_for_doc(elements: list[dict], checklist: dict, doc_id: str) -> dict:
    cte = _doc_has_cte_signals(elements)
    steps = {"G1": g1_inventory(elements, doc_id)}
    for step in ("G2", "G3", "G4", "G5", "G6", "G7"):
        steps[step] = g_presence_for_step(
            elements, checklist, step, cte_signaled=cte
        )
    steps["G8"] = {
        "step": "G8",
        "status": "STUB",
        "note": "cross-artifact alignment (syllabus ↔ Path F) TBD",
    }
    steps["G9"] = {
        "step": "G9",
        "status": "STUB",
        "note": "emit Path G one-pager TBD",
    }
    return steps


def run_path_g_for_project(project_id: str) -> dict:
    """Run Path G presence extractors for each routed syllabus doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="syllabus")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_syllabus_checklist()

    inventory = []
    steps_by_doc: dict[str, dict] = {}
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        elements = _elements_for_doc(ledger, did)
        steps = _steps_for_doc(elements, checklist, did)
        steps_by_doc[did] = steps
        # Compact inventory row mirrors prior stub shape for handoffs.
        row = {
            "doc_id": did,
            "doc_type": r.get("doc_type"),
            "graph_role": r.get("graph_role"),
            "element_count": steps["G1"].get("element_count", 0),
        }
        for step in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step in {"G2", "G3", "G4", "G5", "G6", "G7"}
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "syllabus",
        "path": "G",
        "lens": "Syllabus",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/syllabus.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
    }

    dest = root / "path_g" / "findings.json"
    write_path_findings(dest, out)
    log(f"path G → {len(doc_ids)} syllabus doc(s); G2–G7 presence extract")
    return out
