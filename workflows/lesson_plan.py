#!/usr/bin/env python3
"""
workflows/lesson_plan.py — Path A (A1–A8) for docs routed as lesson_plan.

Auditor-only: presence / mismatch from evidence; never invent content.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_lib import (
    atomic_write,
    load_config,
    load_yaml,
    log,
    model_chat,
    parse_model_json,
    project_dir,
)
from lesson_plan_fill import (
    HUNTER_CORE_IDS,
    load_daily_lesson_checklist,
    render_lesson_plan_md,
)
from route import routed_doc_ids
from unit_plan_fill import _pick_excerpts, _trunc, iter_checklist_fields
from workflows.findings_io import write_path_findings

TEKS_RE = re.compile(r"TEKS|§\s*\d+|Student Expectation", re.I)
OBJECTIVE_RE = re.compile(
    r"objective|learning target|students will|SWBAT|purpose", re.I
)
FORMATIVE_KW = ("exit ticket", "formative", "check for understanding", "do now", "CFU")
SUMMATIVE_KW = ("summative", "unit test", "exam", "quiz", "post-assessment", "rubric")
ELPS_KW = ("ELPS", "language objective", "sentence stem")
ACCOM_KW = ("accommodation", "modification", "IEP", "504", "differentiated")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.suffix == ".json" else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _elements_for_docs(ledger: list, doc_ids: set[str]) -> list[dict]:
    return [e for e in ledger if e.get("doc_id") in doc_ids]


def _by_type(elements: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for e in elements:
        et = e.get("element_type") or "unclear"
        for token in str(et).split("|"):
            token = token.strip()
            if token:
                out[token].append(e)
    return out


def a1_inventory(elements: list[dict]) -> dict:
    by_type = {t: len(v) for t, v in _by_type(elements).items()}
    return {
        "step": "A1",
        "element_count": len(elements),
        "by_element_type": by_type,
        "doc_ids": sorted({e.get("doc_id") for e in elements if e.get("doc_id")}),
    }


def a2_standards(elements: list[dict]) -> dict:
    teks = [
        e
        for e in elements
        if (e.get("element_type") or "") == "standards_objectives"
        and TEKS_RE.search(e.get("excerpt") or "")
    ]
    objectives = [
        e
        for e in elements
        if (e.get("element_type") or "") == "standards_objectives"
        and OBJECTIVE_RE.search(e.get("excerpt") or "")
    ]
    return {
        "step": "A2",
        "teks": {
            "status": "PRESENT" if teks else "MISSING",
            "count": len(teks),
            "cites": [_trunc(e.get("excerpt") or "") for e in teks[:3]],
        },
        "objective": {
            "status": "PRESENT" if objectives else "MISSING",
            "count": len(objectives),
            "cites": [_trunc(e.get("excerpt") or "") for e in objectives[:3]],
        },
    }


def a3_coherence(elements: list[dict], a2: dict) -> dict:
    by = _by_type(elements)
    has_obj = a2["objective"]["status"] == "PRESENT"
    has_act = bool(
        by.get("direct_instruction")
        or by.get("guided_practice")
        or by.get("independent_practice")
    )
    has_assess = bool(by.get("assessment_checkpoint"))
    mismatches = []
    if has_act and not has_obj:
        mismatches.append("activities_without_objective")
    if has_assess and not has_obj:
        mismatches.append("assessment_without_objective")
    if has_obj and not has_assess:
        mismatches.append("objective_without_assessment")
    return {
        "step": "A3",
        "has_objective": has_obj,
        "has_activities": has_act,
        "has_assessment": has_assess,
        "mismatches": mismatches,
        "status": "COHERENT" if has_obj and has_act and has_assess and not mismatches else (
            "PARTIAL" if (has_obj or has_act or has_assess) else "MISSING"
        ),
    }


def a4_assessment_path(elements: list[dict]) -> dict:
    formative, summative = [], []
    for e in elements:
        if (e.get("element_type") or "") != "assessment_checkpoint":
            continue
        ex = (e.get("excerpt") or "").lower()
        row = {
            "element_id": e.get("element_id"),
            "excerpt": _trunc(e.get("excerpt") or ""),
        }
        if any(k.lower() in ex for k in FORMATIVE_KW):
            formative.append(row)
        elif any(k.lower() in ex for k in SUMMATIVE_KW):
            summative.append(row)
        else:
            # Ambiguous checkpoint — count as formative candidate (CFU-like)
            formative.append(row)
    return {
        "step": "A4",
        "formative": {"status": "PRESENT" if formative else "MISSING", "items": formative[:5]},
        "summative": {"status": "PRESENT" if summative else "MISSING", "items": summative[:5]},
    }


def a5_hunter_matrix(elements: list[dict], checklist: dict) -> dict:
    by = _by_type(elements)
    fields = {f["id"]: f for f in iter_checklist_fields(checklist)}
    matrix = []
    for hid in HUNTER_CORE_IDS:
        field = fields.get(hid) or {}
        etypes = field.get("element_types") or []
        keywords = field.get("keywords") or []
        hits = []
        for t in etypes:
            hits.extend(by.get(t, []))
        if keywords:
            for e in elements:
                ex = (e.get("excerpt") or "").lower()
                if any(str(k).lower() in ex for k in keywords):
                    hits.append(e)
        # modeling vs input: prefer keyword when both share type
        if hid == "modeling" and keywords:
            keyed = [
                e
                for e in hits
                if any(str(k).lower() in (e.get("excerpt") or "").lower() for k in keywords)
            ]
            if keyed:
                hits = keyed
        status = "PRESENT" if hits else "MISSING"
        matrix.append(
            {
                "id": hid,
                "label": field.get("label") or hid,
                "status": status,
                "cite": _trunc(hits[0].get("excerpt") or "") if hits else "",
            }
        )
    present = sum(1 for m in matrix if m["status"] == "PRESENT")
    return {
        "step": "A5",
        "hunter_core_present": present,
        "hunter_core_total": len(HUNTER_CORE_IDS),
        "matrix": matrix,
    }


def a6_model_place(
    elements: list[dict],
    checklist: dict,
    *,
    cfg: dict | None,
    use_model: bool = True,
) -> dict:
    """Assign existing excerpts to structure fields via model; blank if none fit."""
    candidates = []
    for e in elements:
        candidates.append(
            {
                "element_id": e.get("element_id"),
                "element_type": e.get("element_type"),
                "excerpt": _trunc(e.get("excerpt") or "", 280),
            }
        )
    field_ids = [f["id"] for f in iter_checklist_fields(checklist)]
    placed: dict[str, Any] = {}

    if use_model and cfg and candidates:
        system = (
            "You are a curriculum auditor assigning EXISTING excerpts to daily "
            "lesson-plan fields (test draft plate). Never invent content. If nothing "
            "fits a field, use null. "
            "Return JSON only: {\"assignments\": {\"<field_id>\": \"<element_id>|null\", ...}}"
        )
        user = (
            f"FIELDS: {json.dumps(field_ids)}\n\n"
            f"CANDIDATES:\n{json.dumps(candidates[:40], ensure_ascii=False)}\n\n"
            "Assign at most one element_id per field. Prefer the best fit. "
            "Do not reuse the same element_id across multiple structure-core fields if avoidable."
        )
        try:
            resp = model_chat(
                cfg,
                "analyst",
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                step="path-a-a6-place",
                temperature=0.1,
                max_tokens=2048,
            )
            content = resp["choices"][0]["message"]["content"]
            parsed = parse_model_json(content) or {}
            assignments = parsed.get("assignments") or {}
            by_eid = {e.get("element_id"): e for e in elements}
            used: set[str] = set()
            for fid in field_ids:
                eid = assignments.get(fid)
                if not eid or eid == "null" or eid not in by_eid:
                    placed[fid] = {"status": "MISSING", "text": "", "sources": [], "element_id": None}
                    continue
                # Prefer unique for hunter core
                if fid in HUNTER_CORE_IDS and eid in used:
                    placed[fid] = {"status": "MISSING", "text": "", "sources": [], "element_id": None}
                    continue
                e = by_eid[eid]
                used.add(eid)
                placed[fid] = {
                    "status": "PRESENT",
                    "text": _trunc(e.get("excerpt") or ""),
                    "sources": [e.get("doc_id") or ""],
                    "element_id": eid,
                }
            return {"step": "A6", "method": "model", "fields": placed}
        except Exception as ex:
            log(f"WARN: A6 model place failed ({ex}); falling back to code routing")

    # Fallback: keyword / type routing (same spirit as lesson_plan_fill)
    by = _by_type(elements)
    used_keys: set[str] = set()
    for field in iter_checklist_fields(checklist):
        fid = field["id"]
        etypes = field.get("element_types") or []
        keywords = [str(k) for k in (field.get("keywords") or [])]
        cands: list[dict] = []
        for t in etypes:
            cands.extend(by.get(t, []))
        if keywords:
            for e in elements:
                ex = (e.get("excerpt") or "").lower()
                if any(k.lower() in ex for k in keywords):
                    cands.append(e)
        picked = None
        for c in _pick_excerpts(
            [
                {
                    "excerpt": c.get("excerpt") or "",
                    "element_id": c.get("element_id"),
                    "doc_id": c.get("doc_id"),
                    "title": c.get("doc_id"),
                }
                for c in cands
            ],
            limit=5,
        ):
            key = (c.get("excerpt") or "")[:80].lower()
            if key in used_keys and fid in HUNTER_CORE_IDS:
                continue
            picked = c
            used_keys.add(key)
            break
        if picked:
            placed[fid] = {
                "status": "PRESENT",
                "text": _trunc(picked.get("excerpt") or ""),
                "sources": [picked.get("doc_id") or ""],
                "element_id": picked.get("element_id"),
            }
        else:
            placed[fid] = {"status": "MISSING", "text": "", "sources": [], "element_id": None}
    return {"step": "A6", "method": "code_fallback", "fields": placed}


def a7_supports(elements: list[dict]) -> dict:
    elps, accom = [], []
    for e in elements:
        ex = e.get("excerpt") or ""
        if any(k.lower() in ex.lower() for k in ELPS_KW):
            elps.append(_trunc(ex))
        if any(k.lower() in ex.lower() for k in ACCOM_KW):
            accom.append(_trunc(ex))
    return {
        "step": "A7",
        "elps": {"status": "PRESENT" if elps else "MISSING", "cites": elps[:3]},
        "accommodations": {"status": "PRESENT" if accom else "MISSING", "cites": accom[:3]},
    }


def a8_emit(
    project_id: str,
    *,
    doc_ids: set[str],
    a5: dict,
    a6: dict,
) -> list[str]:
    """Write per-doc Path A summaries; aggregate findings are written by the caller.

    Keeping the project-level findings write in one place (after A8 is filled)
    lets the shared validator see the complete payload once, instead of an
    intermediate file that still lacks emit_paths / status.
    """
    root = project_dir(project_id)
    out_dir = root / "path_a"
    out_dir.mkdir(parents=True, exist_ok=True)
    for did in sorted(doc_ids):
        atomic_write(
            out_dir / f"{did}.json",
            json.dumps(
                {
                    "doc_id": did,
                    "hunter": a5,
                    "placed_fields": a6.get("fields"),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
    return ["path_a/findings.json"]


def run_path_a_for_project(project_id: str, *, use_model: bool = True) -> dict:
    root = project_dir(project_id)
    doc_ids = routed_doc_ids(project_id, workflow_id="lesson_plan")
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []
    elements = _elements_for_docs(ledger, doc_ids)
    checklist = load_daily_lesson_checklist()
    cfg = None
    if use_model:
        try:
            cfg = load_config()
        except Exception:
            cfg = None

    a1 = a1_inventory(elements)
    a2 = a2_standards(elements)
    a3 = a3_coherence(elements, a2)
    a4 = a4_assessment_path(elements)
    a5 = a5_hunter_matrix(elements, checklist)
    a6 = a6_model_place(elements, checklist, cfg=cfg, use_model=use_model)
    a7 = a7_supports(elements)

    # Path A scores at project grain (`steps` / a6_fields / emit_paths). The
    # shared B–H envelope keys sit alongside so every consumer can read one
    # shape; inventory lists routed docs without fabricating per-doc step cells.
    by_doc_count: dict[str, int] = defaultdict(int)
    for e in elements:
        did = e.get("doc_id")
        if did:
            by_doc_count[str(did)] += 1
    inventory = [
        {
            "doc_id": did,
            "doc_type": "lesson_plan",
            "element_count": by_doc_count.get(did, 0),
        }
        for did in sorted(doc_ids)
    ]
    emits = a8_emit(project_id, doc_ids=doc_ids, a5=a5, a6=a6)
    findings = {
        "project_id": project_id,
        "workflow_id": "lesson_plan",
        "path": "A",
        "lens": "Lesson",
        "status": "ok" if doc_ids else "skipped",
        "doc_ids": sorted(doc_ids),
        "checklist": "workflows/checklists/daily_lesson_plan.yaml",
        "inventory": inventory,
        "steps_by_doc": {},
        "steps": {
            "A1": a1,
            "A2": a2,
            "A3": a3,
            "A4": a4,
            "A5": a5,
            "A6": {
                "method": a6.get("method"),
                "present": sum(
                    1
                    for f in (a6.get("fields") or {}).values()
                    if f.get("status") == "PRESENT"
                ),
            },
            "A7": a7,
            "A8": {
                "step": "A8",
                "emit_paths": emits,
                "status": "emitted" if emits else "skipped",
            },
        },
        "a6_fields": a6.get("fields"),
        "emit_paths": emits,
    }
    write_path_findings(root / "path_a" / "findings.json", findings)
    log(
        f"path A → {len(doc_ids)} lesson_plan doc(s); "
        f"test draft {a5['hunter_core_present']}/{a5['hunter_core_total']}"
    )
    return findings


def write_unit_lesson_plans_from_path_a(
    project_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
) -> list[Path]:
    """Merge Path A A6 field placements into per-unit LESSON-PLAN plates."""
    from lesson_plan_fill import write_lesson_plan_for_unit
    from render_pdf import render_lesson_plan_pdf

    root = project_dir(project_id)
    path_a = _load_json(root / "path_a" / "findings.json")
    written: list[Path] = []
    for uid in sorted((manifest.get("units") or {}).keys()):
        md = write_lesson_plan_for_unit(
            project_id, uid, manifest=manifest, title_map=title_map
        )
        # Overlay A6 placements when Path A ran (prefer model-placed text)
        if isinstance(path_a, dict) and path_a.get("a6_fields"):
            filled_path = md.parent / "LESSON-PLAN.json"
            if filled_path.is_file():
                filled = json.loads(filled_path.read_text(encoding="utf-8"))
                # Keep unit fill; Path A is doc-scoped — unit plate stays discovery fill
                # but record path_a method for ops.
                filled["path_a"] = {
                    "hunter": (path_a.get("steps") or {}).get("A5"),
                    "a6_method": (path_a.get("steps") or {}).get("A6", {}).get("method"),
                }
                atomic_write(
                    filled_path, json.dumps(filled, indent=2, ensure_ascii=False)
                )
                atomic_write(md, render_lesson_plan_md(filled))
        try:
            render_lesson_plan_pdf(project_id, uid)
        except Exception as e:
            log(f"WARN: LESSON-PLAN PDF skipped for {uid}: {e}")
        written.append(md)
    return written
