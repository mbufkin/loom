#!/usr/bin/env python3
"""workflows/quiz.py — Path B (Assessment) B1–B6: quiz ↔ answer key.

Educational note: Path B reviews quizzes and keys as a **pair**. Exit tickets
are Path H. Presence-first (B1–B5): scan Layer 0 excerpts with the assessment
checklist; fall back to source text when the ledger is empty so labs still
smoke. Auditor-only — never invent items or keys. B6 stays stubbed (one-pager).
"""

from __future__ import annotations

import json
import re
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
    Path(__file__).resolve().parent / "checklists" / "assessment.yaml"
)

# Strip pairing noise so quiz + key filenames can join.
_PAIR_NOISE = re.compile(
    r"(answer[_\s.-]?keys?|quizizz|quiz|total questions|\.txt|\.docx|\.pdf)",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def load_assessment_checklist() -> dict:
    """Load Path B checklist; empty dict if missing (tests can inject)."""
    if not CHECKLIST_PATH.is_file():
        return {}
    data = load_yaml(CHECKLIST_PATH)
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.suffix == ".json" else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _elements_for_doc(ledger: list, doc_id: str) -> list[dict]:
    """Scope excerpts to one assessment doc — avoid cite bleed across quizzes."""
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
    """Keyword presence over excerpts (quizzes are item text, not Hunter slots)."""
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


def b1_inventory(elements: list[dict], doc_id: str) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "B1",
        "status": "PRESENT" if elements else "MISSING",
        "note": "Layer 0 / source excerpt inventory for this assessment doc",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_id": doc_id,
    }


def b_presence_for_step(
    elements: list[dict], checklist: dict, step: str
) -> dict:
    """Run one B2–B4 step: PRESENT/PARTIAL/MISSING (+ optional soft-miss)."""
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
            # Optional fields do not inflate required for rollup.
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
        # All optional (B4): PRESENT if any optional hit, else MISSING.
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


def pair_key(name: str) -> str:
    """Normalize quiz/key filenames into a join key.

    Educational note: Dallas ships Quizizz pairs with noisy suffixes
    (Answer_key, Quizizz). Strip those so siblings share one stem.
    """
    s = (name or "").lower()
    # Drop leading doc_<hash>_ so stem compares on title words.
    s = re.sub(r"^doc_[0-9a-f]+_", "", s)
    s = _PAIR_NOISE.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    return " ".join(s.split())


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
                    "element_type": "assessment_item",
                    "excerpt": text,
                    "source_file": path.name,
                }
            ]
    return []


def _pair_status(
    doc_id: str,
    doc_type: str,
    source_file: str,
    by_pair: dict[str, list[dict]],
) -> dict:
    """B5: is this quiz/key orphaned or matched to a sibling?"""
    key = pair_key(source_file or doc_id)
    siblings = by_pair.get(key) or []
    types = {s.get("doc_type") for s in siblings}
    other_ids = [s["doc_id"] for s in siblings if s["doc_id"] != doc_id]
    has_quiz = "quiz" in types or any(
        classify_doc_type(s.get("source_file") or "") == "quiz" for s in siblings
    )
    has_key = "answer_key" in types or any(
        classify_doc_type(s.get("source_file") or "") == "answer_key"
        for s in siblings
    )
    # Rubrics alone are not a quiz↔key pair.
    if doc_type == "rubric" and not (has_quiz or has_key):
        return {
            "step": "B5",
            "status": "NOT_APPLICABLE",
            "note": "rubric routed to B; pairing is for quiz↔key",
            "pair_key": key,
            "sibling_doc_ids": other_ids,
        }
    if has_quiz and has_key and other_ids:
        status = "PRESENT"
        note = "quiz↔key pair matched by normalized filename stem"
    elif doc_type == "answer_key" and not has_quiz:
        status = "PARTIAL"
        note = "answer key without matched quiz sibling"
    elif doc_type == "quiz" and not has_key:
        status = "PARTIAL"
        note = "quiz without matched answer-key sibling"
    else:
        status = "MISSING"
        note = "no pair group"
    return {
        "step": "B5",
        "status": status,
        "note": note,
        "pair_key": key,
        "sibling_doc_ids": other_ids,
    }


def _steps_for_doc(
    elements: list[dict],
    checklist: dict,
    doc_id: str,
    *,
    doc_type: str,
    source_file: str,
    by_pair: dict[str, list[dict]],
) -> dict:
    steps = {"B1": b1_inventory(elements, doc_id)}
    for step in ("B2", "B3", "B4"):
        steps[step] = b_presence_for_step(elements, checklist, step)
    steps["B5"] = _pair_status(doc_id, doc_type, source_file, by_pair)
    steps["B6"] = {
        "step": "B6",
        "status": "STUB",
        "note": "emit Path B one-pager TBD",
    }
    return steps


def run_path_b_for_project(project_id: str) -> dict:
    """Run Path B presence extractors for each routed quiz/key/rubric doc."""
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="quiz")
    route = load_route_map(project_id)
    by_id = {r["doc_id"]: r for r in route.get("routes") or []}
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    checklist = load_assessment_checklist()

    # Build pair groups before per-doc steps so B5 can see siblings.
    route_recs = []
    for did in sorted(doc_ids):
        r = by_id.get(did) or {}
        sf = r.get("source_file") or did
        dtype = (r.get("doc_type") or classify_doc_type(sf) or "").lower()
        route_recs.append(
            {"doc_id": did, "doc_type": dtype, "source_file": sf}
        )
    by_pair: dict[str, list[dict]] = defaultdict(list)
    for rec in route_recs:
        by_pair[pair_key(rec["source_file"])].append(rec)

    inventory = []
    steps_by_doc: dict[str, dict] = {}
    for rec in route_recs:
        did = rec["doc_id"]
        elements = _elements_for_doc(ledger, did)
        if not elements:
            elements = _source_text_elements(root, did, rec["source_file"])
        steps = _steps_for_doc(
            elements,
            checklist,
            did,
            doc_type=rec["doc_type"],
            source_file=rec["source_file"],
            by_pair=by_pair,
        )
        steps_by_doc[did] = steps
        row = {
            "doc_id": did,
            "doc_type": rec["doc_type"],
            "element_count": steps["B1"].get("element_count", 0),
            "pair_key": steps["B5"].get("pair_key"),
        }
        for step in ("B1", "B2", "B3", "B4", "B5", "B6"):
            s = steps[step]
            row[step] = {
                "status": s.get("status"),
                "note": s.get("note")
                or (
                    f"{s.get('present', 0)}/{s.get('required', 0)} fields present"
                    if step in {"B2", "B3", "B4"}
                    else ""
                ),
            }
        inventory.append(row)

    out = {
        "project_id": project_id,
        "workflow_id": "quiz",
        "path": "B",
        "lens": "Assessment",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/assessment.yaml",
        "inventory": inventory,
        "steps_by_doc": steps_by_doc,
    }
    dest = root / "path_b" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(f"path B → {len(doc_ids)} quiz/key doc(s); B1–B5 presence extract")
    return out
