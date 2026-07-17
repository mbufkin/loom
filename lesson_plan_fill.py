#!/usr/bin/env python3
"""
lesson_plan_fill.py — Discovery-fill a lesson-plan plate (test draft).

Structure-first inventory for each unit: every core structure element appears as a
named field. PRESENT = cited Layer 0/1 evidence; MISSING / blank = not found.
Never invents lesson content (docs/STRUCTURAL-FILL.md).

Companion to unit_plan_fill.py (NW ISD Unit Plan macro). This plate is the
daily-lesson *structure* view (labeled test draft on PDFs).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from audit_lib import BASE_DIR, atomic_write, load_yaml, log, project_dir
from unit_plan_fill import (
    _pick_excerpts,
    _trunc,
    collect_unit_evidence,
    iter_checklist_fields,
)

CHECKLIST_PATH = BASE_DIR / "workflows" / "checklists" / "daily_lesson_plan.yaml"

# Ordered structure-core field ids — used for the matrix at the top of the plate.
HUNTER_CORE_IDS = (
    "anticipatory_set",
    "objective_purpose",
    "input",
    "modeling",
    "check_for_understanding",
    "guided_practice",
    "independent_practice",
    "closure",
)


def load_daily_lesson_checklist() -> dict:
    if not CHECKLIST_PATH.is_file():
        raise FileNotFoundError(
            f"Missing daily lesson checklist at {CHECKLIST_PATH} — "
            "expected workflows/checklists/daily_lesson_plan.yaml"
        )
    return load_yaml(CHECKLIST_PATH)


def fill_lesson_plan(
    project_id: str,
    unit_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
    checklist: dict | None = None,
) -> dict[str, Any]:
    """Return filled lesson plate: fields keyed by id → status/text/sources."""
    checklist = checklist or load_daily_lesson_checklist()
    evidence = collect_unit_evidence(
        project_id, unit_id, manifest=manifest, title_map=title_map
    )
    by_type = evidence["by_type"]
    role_hits = evidence["role_hits"]
    filled: dict[str, Any] = {
        "unit_id": unit_id,
        "title": evidence["title"],
        "checklist_version": checklist.get("version"),
        "framework": checklist.get("framework") or "madeline_hunter",
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
            if fid == "lesson_title":
                text = evidence["title"]
            if text:
                status = "PRESENT"
                sources = ["manifest.yaml"]
        else:
            candidates: list[dict] = []
            for t in etypes:
                candidates.extend(by_type.get(t, []))
            if keywords:
                for items in by_type.values():
                    for c in items:
                        ex = c.get("excerpt") or ""
                        low = ex.lower()
                        if any(k.lower() in low for k in keywords):
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

            # TEKS: prefer excerpts that actually cite standards.
            if fid == "teks" and candidates:
                candidates = sorted(
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

            # Modeling vs Input share direct_instruction — prefer keyword hits
            # for modeling so structure stays distinct when possible.
            if fid == "modeling" and keywords:
                keyed = [
                    c
                    for c in candidates
                    if any(
                        k.lower() in (c.get("excerpt") or "").lower() for k in keywords
                    )
                ]
                if keyed:
                    candidates = keyed

            picked = _pick_excerpts(candidates)
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
    hunter_present = sum(
        1
        for hid in HUNTER_CORE_IDS
        if (filled["fields"].get(hid) or {}).get("status") == "PRESENT"
    )
    filled["summary"] = {
        "present": present,
        "missing": missing,
        "total": present + missing,
        "hunter_core_present": hunter_present,
        "hunter_core_total": len(HUNTER_CORE_IDS),
    }
    return filled


def render_lesson_plan_md(filled: dict[str, Any]) -> str:
    """Structure-first markdown: test-draft matrix, then every field."""
    title = filled.get("title") or filled.get("unit_id")
    summary = filled.get("summary") or {}
    lines = [
        f"# Lesson Plan (test draft) — {title}",
        "",
        "**Structure inventory from folder evidence (test draft).** Every core "
        "structure element is listed below. Blank / MISSING = not found in "
        "uploaded materials — not authored curriculum.",
        "",
        f"**Unit id:** `{filled.get('unit_id')}`  ",
        f"**Framework:** `test_draft`  ",
        f"**Checklist:** `{filled.get('checklist_version') or 'daily_lesson_plan'}`  ",
        f"**Structure core:** {summary.get('hunter_core_present', 0)} / "
        f"{summary.get('hunter_core_total', 8)} present  ·  "
        f"**All fields:** {summary.get('present', 0)} found / "
        f"{summary.get('missing', 0)} not found",
        "",
        "## Structure matrix (test draft)",
        "",
        "| # | Element | Status |",
        "|---|---------|--------|",
    ]

    fields = filled.get("fields") or {}
    for i, hid in enumerate(HUNTER_CORE_IDS, start=1):
        cell = fields.get(hid) or {}
        label = cell.get("label") or hid
        # Strip leading "N. " from label for the matrix cell
        short = re.sub(r"^\d+\.\s*", "", label)
        status = cell.get("status") or "MISSING"
        mark = "PRESENT" if status == "PRESENT" else "MISSING"
        lines.append(f"| {i} | {short} | **{mark}** |")

    lines += ["", "---", ""]

    current_section = None
    for fid, cell in fields.items():
        sec = cell.get("section_label")
        if sec != current_section:
            current_section = sec
            lines += ["", f"## {sec}", ""]
        label = cell.get("label") or fid
        status = cell.get("status") or "MISSING"
        text = (cell.get("text") or "").strip()
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"**Status:** {status}")
        lines.append("")
        if status == "PRESENT" and text:
            lines.append(text)
        else:
            lines.append("*(not found in uploaded materials)*")
        lines.append("")

    lines += [
        "---",
        "",
        "*Unit-level inventory remains in `UNIT-PLAN.md`. Auditor punch list "
        "remains in `TEACHER-PACKET.md`. This plate is daily-lesson structure.*",
        "",
    ]
    return "\n".join(lines)


def write_lesson_plan_for_unit(
    project_id: str,
    unit_id: str,
    *,
    manifest: dict,
    title_map: dict[str, str],
    out_dir: Path | None = None,
) -> Path:
    """Write output/teachers/<unit>/LESSON-PLAN.md (+ .json)."""
    filled = fill_lesson_plan(
        project_id, unit_id, manifest=manifest, title_map=title_map
    )
    root = project_dir(project_id)
    dest_dir = out_dir or (root / "output" / "teachers" / unit_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    md_path = dest_dir / "LESSON-PLAN.md"
    atomic_write(md_path, render_lesson_plan_md(filled))
    atomic_write(
        dest_dir / "LESSON-PLAN.json",
        json.dumps(filled, indent=2, ensure_ascii=False),
    )
    s = filled["summary"]
    log(
        f"lesson plan → {md_path} "
        f"(test draft {s['hunter_core_present']}/{s['hunter_core_total']}; "
        f"{s['present']} present / {s['missing']} missing)"
    )
    return md_path
