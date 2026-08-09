#!/usr/bin/env python3
"""workflows/exit_ticket.py — Path H (Exit ticket) H1–H5 formative presence.

Educational note: Exit tickets are short end-of-lesson formative checks.
They are *not* quiz↔key pairs (Path B). Presence-first (H1–H4): scan Layer 0
excerpts with the exit-ticket checklist; fall back to source text when the
ledger is empty. Auditor-only — never invent prompts or reteach plans.
H5 stays stubbed (one-pager).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_lib import (
    classify_doc_type,
    load_yaml,
    log,
    project_dir,
)
from route import load_route_map, routed_doc_ids
from unit_plan_fill import _trunc
from workflows.findings_io import write_path_findings

CHECKLIST_PATH = (
    Path(__file__).resolve().parent / "checklists" / "exit_ticket.yaml"
)


def load_exit_ticket_checklist() -> dict:
    """Load Path H checklist; empty dict if missing (tests can inject)."""
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


def h1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "H1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 / source excerpt inventory for this exit ticket",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def h_presence_for_step(
    elements: list[dict], checklist: dict, step: str
) -> dict:
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
            note = "optional target cue not found"
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
        # All-optional step (H3): a hit is still good news (PRESENT), but finding
        # nothing is not a gap. OPTIONAL_ABSENT keeps MISSING reserved for
        # required fields that failed — otherwise the Paths panel and the
        # artifact gate cannot tell "nice-to-have absent" from a real finding.
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


def _source_text_elements(root: Path, doc_id: str, source_file: str) -> list[dict]:
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
                    "element_type": "exit_ticket",
                    "excerpt": text,
                    "source_file": path.name,
                }
            ]
    return []


def _steps_for_doc(
    elements: list[dict], checklist: dict, doc_id: str
) -> dict:
    steps = {"H1": h1_inventory(elements, doc_id)}
    for step in ("H2", "H3", "H4"):
        steps[step] = h_presence_for_step(elements, checklist, step)
    steps["H5"] = {
        "step": "H5",
        "status": "STUB",
        "note": "emit Path H one-pager TBD",
    }
    return steps


def run_path_h_for_project(project_id: str) -> dict:
    """Run Path H presence extractors for each routed exit-ticket doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="exit_ticket")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_exit_ticket_checklist()

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
            "element_count": steps["H1"].get("element_count", 0),
        }
        for step in ("H1", "H2", "H3", "H4", "H5"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step in {"H2", "H3", "H4"}
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "exit_ticket",
        "path": "H",
        "lens": "Exit ticket",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/exit_ticket.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
    }
    dest = root / "path_h" / "findings.json"
    write_path_findings(dest, out)
    log(f"path H → {len(doc_ids)} exit_ticket doc(s); H1–H4 presence extract")
    return out
