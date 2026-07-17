#!/usr/bin/env python3
"""
unit_plan_fill.py — Discovery-fill the CTAT / Northwest ISD Unit Plan Template.

After Layer 0 breaks docs apart and Layer 1 places them into units, this module
pastes cited evidence into the Unit Plan fields. A blank field means that
information was not found in the uploaded materials — discovery inventory, not
authored curriculum (docs/STRUCTURAL-FILL.md).

The Unit Plan plate is the education-space macro view of what a unit HAS.
The teacher packet remains the separate auditor punch list.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from audit_lib import (
    BASE_DIR,
    atomic_write,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
)

CHECKLIST_PATH = BASE_DIR / "workflows" / "checklists" / "lesson_plan.yaml"
EXCERPT_CAP = 500

# Layer 2 presence scoring uses only fields that map to Layer 0 element_types
# (Bet 14: code-only checklist against an already-selected lesson_plan doc).
LAYER2_CORE_ELEMENT_TYPES = frozenset(
    {
        "standards_objectives",
        "logistics_materials",
        "hook_engagement",
        "direct_instruction",
        "guided_practice",
        "independent_practice",
        "assessment_checkpoint",
        "reflection_closure",
    }
)


def load_lesson_plan_checklist() -> dict:
    if not CHECKLIST_PATH.is_file():
        raise FileNotFoundError(
            f"Missing lesson-plan checklist at {CHECKLIST_PATH} — "
            "expected workflows/checklists/lesson_plan.yaml"
        )
    return load_yaml(CHECKLIST_PATH)


def iter_checklist_fields(checklist: dict | None = None) -> list[dict]:
    """Flat list of field defs with section_id / section_label attached."""
    checklist = checklist or load_lesson_plan_checklist()
    out: list[dict] = []
    for section_id, section in (checklist.get("sections") or {}).items():
        for field in section.get("fields") or []:
            out.append(
                {
                    **field,
                    "section_id": section_id,
                    "section_label": section.get("label") or section_id,
                }
            )
    return out


def layer2_expected_element_types(checklist: dict | None = None) -> frozenset[str]:
    """Element types Layer 2 should require for a fulfilled lesson_plan doc."""
    types: set[str] = set()
    for field in iter_checklist_fields(checklist):
        for t in field.get("element_types") or []:
            if t in LAYER2_CORE_ELEMENT_TYPES:
                types.add(t)
    # Always keep the original v1 four as a floor so we never regress coverage.
    types |= {
        "standards_objectives",
        "logistics_materials",
        "direct_instruction",
        "assessment_checkpoint",
    }
    return frozenset(types)


def _trunc(text: str, limit: int = EXCERPT_CAP) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= limit:
        return t
    cut = t[: limit - 1]
    sp = cut.rfind(" ")
    if sp > limit // 2:
        cut = cut[:sp]
    return cut + "…"


def _unit_doc_ids(manifest: dict, unit_id: str) -> set[str]:
    unit = (manifest.get("units") or {}).get(unit_id) or {}
    return {
        doc_id_from_filename(p)
        for p in unit.get("documents") or unit.get("source_files") or []
    }


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if path.name.endswith(".json") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _keyword_hit(excerpt: str, keywords: list[str] | None) -> bool:
    if not keywords:
        return False
    low = excerpt.lower()
    return any(k.lower() in low for k in keywords)


def collect_unit_evidence(
    project_id: str,
    unit_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
) -> dict[str, Any]:
    """Gather Layer 0 excerpts + Layer 1 role hits scoped to this unit."""
    root = project_dir(project_id)
    doc_ids = _unit_doc_ids(manifest, unit_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    findings = _load_json(root / "layer1" / "findings.json")

    elements = [e for e in ledger if e.get("doc_id") in doc_ids]
    # Prefer elements whose final_unit_id / parent matches when present on ledger
    # rows that were enriched by Layer 1 bucket-ledger — fall back to doc list.
    bucket = _load_json(root / "layer1" / "bucket-ledger.json")
    if bucket:
        by_eid = {r.get("element_id"): r for r in bucket}
        scoped: list[dict] = []
        for e in ledger:
            br = by_eid.get(e.get("element_id"))
            if br and (
                br.get("final_unit_id") == unit_id
                or br.get("parent_link_unit_id") == unit_id
            ):
                scoped.append(e)
            elif e.get("doc_id") in doc_ids:
                scoped.append(e)
        elements = scoped

    by_type: dict[str, list[dict]] = {}
    for e in elements:
        et = e.get("element_type") or "unclear"
        for token in str(et).split("|"):
            token = token.strip()
            if not token:
                continue
            by_type.setdefault(token, []).append(
                {
                    "element_id": e.get("element_id"),
                    "doc_id": e.get("doc_id"),
                    "title": title_map.get(e.get("doc_id") or "", e.get("doc_id")),
                    "excerpt": e.get("excerpt") or "",
                    "element_type": token,
                }
            )

    unit_findings = [f for f in findings if f.get("unit_id") == unit_id]
    role_hits: dict[str, list[dict]] = {}
    for f in unit_findings:
        role = f.get("role") or "other"
        if f.get("status") not in ("FULFILLED", "DUPLICATE"):
            continue
        titles: list[str] = []
        for eid in f.get("fulfilled_by") or []:
            doc = str(eid).replace("CANDIDATE ", "").split("-e")[0]
            titles.append(title_map.get(doc, doc))
        role_hits.setdefault(role, []).append(
            {
                "day_id": f.get("day_id"),
                "status": f.get("status"),
                "titles": titles,
                "reasoning": f.get("reasoning") or "",
            }
        )

    unit = (manifest.get("units") or {}).get(unit_id) or {}
    cal_meta: dict[str, Any] = {}
    cal_rel = unit.get("calendar")
    if cal_rel:
        try:
            cal = load_yaml(root / cal_rel)
            days = cal.get("days") or []
            cal_meta = {
                "day_count": len(days),
                "day_ids": [d.get("id") for d in days],
            }
        except Exception:
            cal_meta = {}

    return {
        "unit_id": unit_id,
        "title": unit.get("title") or unit_id,
        "program_of_study": unit.get("cluster")
        or unit.get("program_of_study")
        or unit.get("career_cluster")
        or "",
        "by_type": by_type,
        "role_hits": role_hits,
        "calendar": cal_meta,
        "doc_ids": sorted(doc_ids),
    }


def _pick_excerpts(
    candidates: list[dict], *, limit: int = 3
) -> list[dict]:
    """Dedupe by excerpt prefix; keep first N with non-empty text."""
    out: list[dict] = []
    seen: set[str] = set()
    for c in candidates:
        ex = (c.get("excerpt") or "").strip()
        if not ex:
            continue
        key = ex[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def fill_unit_plan(
    project_id: str,
    unit_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
    checklist: dict | None = None,
) -> dict[str, Any]:
    """Return filled Unit Plan: fields keyed by id → {label, status, text, sources}."""
    checklist = checklist or load_lesson_plan_checklist()
    evidence = collect_unit_evidence(
        project_id, unit_id, manifest=manifest, title_map=title_map
    )
    by_type = evidence["by_type"]
    role_hits = evidence["role_hits"]
    filled: dict[str, Any] = {
        "unit_id": unit_id,
        "title": evidence["title"],
        "checklist_version": checklist.get("version"),
        "fields": {},
    }

    for field in iter_checklist_fields(checklist):
        fid = field["id"]
        label = field.get("label") or fid
        fill_from = field.get("fill_from")
        etypes = field.get("element_types") or []
        roles = field.get("roles") or []
        keywords = field.get("keywords") or []

        text = ""
        sources: list[str] = []
        status = "MISSING"

        if fill_from == "manifest":
            if fid == "program_of_study":
                text = evidence.get("program_of_study") or ""
            elif fid == "course_name":
                text = evidence["title"]
            elif fid == "lesson_unit_title":
                text = evidence["title"]
            if text:
                status = "PRESENT"
                sources = ["manifest.yaml"]

        elif fill_from == "calendar":
            n = (evidence.get("calendar") or {}).get("day_count")
            if n:
                text = f"{n} day(s) on this unit's calendar grid"
                status = "PRESENT"
                sources = [f"units/{unit_id}/calendar.yaml"]

        else:
            candidates: list[dict] = []
            for t in etypes:
                candidates.extend(by_type.get(t, []))
            if keywords:
                # Keyword routing across all unit excerpts (accommodations / CTE).
                for items in by_type.values():
                    for c in items:
                        if _keyword_hit(c.get("excerpt") or "", keywords):
                            candidates.append(c)
            for role in roles:
                for hit in role_hits.get(role, []):
                    titles = ", ".join(hit.get("titles") or []) or role
                    day = hit.get("day_id") or ""
                    day_s = f" ({day})" if day else ""
                    candidates.append(
                        {
                            "excerpt": f"{role}{day_s}: found in {titles}",
                            "title": titles,
                            "element_id": None,
                            "doc_id": None,
                        }
                    )

            picked = _pick_excerpts(candidates)
            # Prefer stronger TEKS citations when the field is teks.
            if fid == "teks" and candidates:
                scored = sorted(
                    candidates,
                    key=lambda c: (
                        0
                        if re.search(
                            r"TEKS|§\s*\d+|Student Expectation",
                            c.get("excerpt") or "",
                            re.I,
                        )
                        else 1,
                        -len(c.get("excerpt") or ""),
                    ),
                )
                picked = _pick_excerpts(scored)
            if picked:
                status = "PRESENT"
                parts = []
                for p in picked:
                    src = p.get("title") or p.get("doc_id") or "source"
                    if src not in sources:
                        sources.append(str(src))
                    parts.append(f"{_trunc(p['excerpt'])}  _(Source: {src})_")
                text = "\n\n".join(parts)

        filled["fields"][fid] = {
            "label": label,
            "section_id": field["section_id"],
            "section_label": field["section_label"],
            "status": status,
            "text": text,
            "sources": sources,
        }

    present = sum(1 for f in filled["fields"].values() if f["status"] == "PRESENT")
    missing = sum(1 for f in filled["fields"].values() if f["status"] == "MISSING")
    filled["summary"] = {"present": present, "missing": missing, "total": present + missing}
    return filled


def render_unit_plan_md(filled: dict[str, Any]) -> str:
    """Render CTAT-shaped markdown. Blank cells show as empty with MISSING mark."""
    lines = [
        f"# Unit Plan — {filled.get('title') or filled.get('unit_id')}",
        "",
        "**Discovery fill from folder evidence.** Blank / MISSING = not found in "
        "uploaded materials. This is not an authored unit plan.",
        "",
        f"**Unit id:** `{filled.get('unit_id')}`  ",
        f"**Checklist:** `{filled.get('checklist_version') or 'lesson_plan'}`  ",
        f"**Fields found:** {filled.get('summary', {}).get('present', 0)}  ·  "
        f"**Not found:** {filled.get('summary', {}).get('missing', 0)}",
        "",
    ]

    current_section = None
    for fid, cell in filled.get("fields", {}).items():
        sec = cell.get("section_label")
        if sec != current_section:
            current_section = sec
            lines += ["", f"## {sec}", ""]
        label = cell.get("label") or fid
        status = cell.get("status") or "MISSING"
        text = (cell.get("text") or "").strip()
        lines.append(f"### {label}")
        lines.append("")
        if status == "PRESENT" and text:
            lines.append(text)
        else:
            lines.append("*(not found in uploaded materials)*")
        lines.append("")

    lines += [
        "---",
        "",
        "*Auditor punch list for this unit remains in `TEACHER-PACKET.md`. "
        "This Unit Plan is the education-space macro inventory.*",
        "",
    ]
    return "\n".join(lines)


def write_unit_plan_for_unit(
    project_id: str,
    unit_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
    out_dir: Path | None = None,
) -> Path:
    """Write output/teachers/<unit>/UNIT-PLAN.md and return its path."""
    filled = fill_unit_plan(
        project_id, unit_id, manifest=manifest, title_map=title_map
    )
    root = project_dir(project_id)
    dest_dir = out_dir or (root / "output" / "teachers" / unit_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    md_path = dest_dir / "UNIT-PLAN.md"
    atomic_write(md_path, render_unit_plan_md(filled))
    # Raw JSON for ops / golden drift
    atomic_write(
        dest_dir / "UNIT-PLAN.json",
        json.dumps(filled, indent=2, ensure_ascii=False),
    )
    log(
        f"unit plan → {md_path} "
        f"({filled['summary']['present']} present / {filled['summary']['missing']} missing)"
    )
    return md_path
