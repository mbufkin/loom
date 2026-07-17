#!/usr/bin/env python3
"""
path_a_depth.py — Real Path A depth on preserved lesson plans (spike).

single_lp: A1–A7 on that one doc only + day-claim vs meeting_count.
lp_block:  A1–A7 per LP + group overlap / joint coverage (not one mashed plate).

Auditor-only: never invents content. Does not rebuild a replacement LESSON-PLAN.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_lib import project_dir
from lesson_plan_fill import load_daily_lesson_checklist
from workflows.lesson_plan import (
    a1_inventory,
    a2_standards,
    a3_coherence,
    a4_assessment_path,
    a5_hunter_matrix,
    a7_supports,
    _elements_for_docs,
    _trunc,
)

DAY_N_RE = re.compile(r"\bDay\s*(\d+)\b", re.I)
ESTIMATED_RE = re.compile(r"Estimated\s+Day\(s\):\s*(\d+)", re.I)


def _load_ledger(project_id: str) -> list[dict]:
    path = project_dir(project_id) / "layer0" / "ledger.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _day_claims_in_elements(elements: list[dict]) -> dict[str, Any]:
    """Which Day N sections appear inside this LP's excerpts (coverage signal)."""
    days_seen: set[int] = set()
    estimated = 0
    samples: dict[str, str] = {}
    for e in elements:
        ex = e.get("excerpt") or ""
        pos = str(e.get("inferred_position") or "")
        for m in ESTIMATED_RE.finditer(ex):
            estimated = max(estimated, int(m.group(1)))
        for blob in (ex, pos):
            for m in DAY_N_RE.finditer(blob):
                n = int(m.group(1))
                days_seen.add(n)
                key = f"d{n}"
                if key not in samples:
                    samples[key] = _trunc(ex or pos, 160)
    return {
        "days_mentioned": sorted(days_seen),
        "estimated_in_doc": estimated or None,
        "samples": samples,
    }


def _run_a1_a7(elements: list[dict], checklist: dict) -> dict[str, Any]:
    a1 = a1_inventory(elements)
    a2 = a2_standards(elements)
    a3 = a3_coherence(elements, a2)
    a4 = a4_assessment_path(elements)
    a5 = a5_hunter_matrix(elements, checklist)
    a7 = a7_supports(elements)
    return {
        "A1": a1,
        "A2": a2,
        "A3": a3,
        "A4": a4,
        "A5": a5,
        "A7": a7,
        # A6 intentionally skipped here — placement rebuild is not the goal;
        # we review the preserved plan, we don't remake field fills.
        "A6": {
            "step": "A6",
            "status": "skipped_preserve_mode",
            "note": "Preserve author's plan; no scrap field remake in this depth pass",
        },
        "A8": {
            "step": "A8",
            "status": "review_emit",
            "note": "Findings written to path_a_review.*; originals stay in lesson-plans/",
        },
    }


def review_one_lp(
    project_id: str,
    lp: dict,
    *,
    ledger: list[dict] | None = None,
    checklist: dict | None = None,
    meeting_count: int | None = None,
) -> dict[str, Any]:
    """Deep single-document Path A review."""
    ledger = ledger if ledger is not None else _load_ledger(project_id)
    checklist = checklist or load_daily_lesson_checklist()
    did = lp.get("doc_id")
    elements = _elements_for_docs(ledger, {did} if did else set())
    steps = _run_a1_a7(elements, checklist)
    claims = _day_claims_in_elements(elements)

    # Day-claim vs unit meeting_count (metadata compare — not a rebuild)
    day_notes: list[str] = []
    mentioned = claims.get("days_mentioned") or []
    est = claims.get("estimated_in_doc")
    if meeting_count and mentioned:
        missing_days = [d for d in range(1, int(meeting_count) + 1) if d not in mentioned]
        if missing_days:
            day_notes.append(
                f"meeting_count={meeting_count} but Day {missing_days} not evidenced "
                f"in this LP's excerpts (coverage gap signal)."
            )
        else:
            day_notes.append(
                f"Day headers in this LP cover 1..{meeting_count} (aligned with meeting_count)."
            )
    elif meeting_count and est and est != meeting_count:
        day_notes.append(
            f"Doc Estimated Day(s)={est} vs unit meeting_count={meeting_count} (mismatch note)."
        )
    elif meeting_count and not mentioned and not est:
        day_notes.append(
            f"meeting_count={meeting_count} but no Day N / Estimated Day(s) found in this LP."
        )

    a5 = steps["A5"]
    return {
        "doc_id": did,
        "title": lp.get("title"),
        "source_file": lp.get("source_file"),
        "element_count": len(elements),
        "steps": steps,
        "day_claims": claims,
        "day_coverage_notes": day_notes,
        "summary": {
            "coherence": steps["A3"].get("status"),
            "hunter_core_present": a5.get("hunter_core_present"),
            "hunter_core_total": a5.get("hunter_core_total"),
            "teks": steps["A2"]["teks"]["status"],
            "objective": steps["A2"]["objective"]["status"],
            "formative": steps["A4"]["formative"]["status"],
            "summative": steps["A4"]["summative"]["status"],
            "elps": steps["A7"]["elps"]["status"],
            "accommodations": steps["A7"]["accommodations"]["status"],
        },
    }


def _group_analysis(per_lp: list[dict], meeting_count: int | None) -> dict[str, Any]:
    """lp_block-only: how the set fits together (not a mashed single pass)."""
    type_sets: dict[str, set[str]] = {}
    all_days: set[int] = set()
    titles = []
    for rev in per_lp:
        did = rev.get("doc_id") or "?"
        titles.append(rev.get("title") or did)
        a1 = (rev.get("steps") or {}).get("A1") or {}
        type_sets[did] = set((a1.get("by_element_type") or {}).keys())
        for d in (rev.get("day_claims") or {}).get("days_mentioned") or []:
            all_days.add(int(d))

    # Overlap: element types present in more than one LP
    type_owners: dict[str, list[str]] = defaultdict(list)
    for did, types in type_sets.items():
        for t in types:
            type_owners[t].append(did)
    overlapping = sorted(t for t, owners in type_owners.items() if len(owners) > 1)
    unique_per: dict[str, list[str]] = {}
    for did, types in type_sets.items():
        unique_per[did] = sorted(t for t in types if len(type_owners[t]) == 1)

    notes: list[str] = []
    if len(per_lp) >= 2:
        notes.append(
            f"Block of {len(per_lp)} plans — review jointly; do not treat as one document."
        )
    if overlapping:
        notes.append(
            f"Shared element-type signals across plans: {', '.join(overlapping[:12])}"
            + ("…" if len(overlapping) > 12 else "")
        )
    else:
        notes.append("Little element-type overlap — plans may be alternate or specialized.")

    if meeting_count:
        missing = [d for d in range(1, int(meeting_count) + 1) if d not in all_days]
        if missing:
            notes.append(
                f"Joint day coverage: meeting_count={meeting_count}; "
                f"group missing Day {missing} headers across all LPs."
            )
        else:
            notes.append(
                f"Joint day coverage: Days {sorted(all_days)} span meeting_count={meeting_count}."
            )

    # Heuristic relationship note (not a free pass)
    if len(per_lp) == 2 and overlapping:
        notes.append(
            "Possible relationship: complementary or overlapping coverage "
            "(operator should confirm alternate vs sequential)."
        )

    return {
        "plan_titles": titles,
        "overlapping_element_types": overlapping,
        "unique_element_types_by_doc": unique_per,
        "joint_days_mentioned": sorted(all_days),
        "notes": notes,
    }


def run_path_a_depth(
    project_id: str,
    org: dict[str, Any],
    meeting: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute depth review for the unit's Path A mode.

    Returns a structured review dict suitable for JSON + markdown render.
    """
    mode = org.get("path_a_mode")
    lps = org.get("lesson_plans") or []
    meeting_count = meeting.get("meeting_count")
    checklist = load_daily_lesson_checklist()
    ledger = _load_ledger(project_id)

    base = {
        "project_id": project_id,
        "unit_id": org.get("unit_id"),
        "title": org.get("title"),
        "path_a_mode": mode,
        "meeting_count": meeting_count,
        "meeting_source": meeting.get("meeting_source"),
    }

    if mode == "single_lp" and lps:
        rev = review_one_lp(
            project_id,
            lps[0],
            ledger=ledger,
            checklist=checklist,
            meeting_count=meeting_count,
        )
        return {
            **base,
            "reviews": [rev],
            "group": None,
            "depth": "A1-A7_single_doc",
        }

    if mode == "lp_block" and lps:
        reviews = [
            review_one_lp(
                project_id,
                lp,
                ledger=ledger,
                checklist=checklist,
                meeting_count=meeting_count,
            )
            for lp in lps
        ]
        group = _group_analysis(reviews, meeting_count)
        return {
            **base,
            "reviews": reviews,
            "group": group,
            "depth": "A1-A7_per_lp_plus_block",
        }

    return {
        **base,
        "reviews": [],
        "group": None,
        "depth": "skipped",
        "note": f"No LP depth for mode={mode}",
    }


def render_path_a_review_md(review: dict[str, Any]) -> str:
    """Human-readable Path A depth report."""
    mode = review.get("path_a_mode")
    title = review.get("title") or review.get("unit_id")
    lines = [
        f"# Path A review — {title}",
        "",
        f"**Mode:** `{mode}`  ",
        f"**Depth:** `{review.get('depth')}`  ",
        f"**Meeting count:** {review.get('meeting_count')} "
        f"({review.get('meeting_source') or 'unknown'})",
        "",
        "Preserved author lesson plans are reviewed in place — "
        "**not** remade into a scrap LESSON-PLAN plate.",
        "",
    ]

    if mode == "lp_block" and review.get("group"):
        g = review["group"]
        lines += ["## Block analysis (`lp_block`)", ""]
        for n in g.get("notes") or []:
            lines.append(f"- {n}")
        lines += [
            "",
            f"**Joint days mentioned:** {g.get('joint_days_mentioned') or []}",
            f"**Overlapping element types:** {g.get('overlapping_element_types') or []}",
            "",
        ]

    for i, rev in enumerate(review.get("reviews") or [], start=1):
        s = rev.get("summary") or {}
        a5 = (rev.get("steps") or {}).get("A5") or {}
        lines += [
            f"## {'Plan' if mode == 'lp_block' else 'Lesson plan'} {i}: {rev.get('title')}",
            "",
            f"- **doc_id:** `{rev.get('doc_id')}`",
            f"- **elements:** {rev.get('element_count')}",
            f"- **UbD coherence (A3):** **{s.get('coherence')}**",
            f"- **Structure core (A5):** "
            f"**{s.get('hunter_core_present')}/{s.get('hunter_core_total')}**",
            f"- **TEKS / objective (A2):** {s.get('teks')} / {s.get('objective')}",
            f"- **Formative / summative (A4):** {s.get('formative')} / {s.get('summative')}",
            f"- **ELPS / accommodations (A7):** {s.get('elps')} / {s.get('accommodations')}",
            "",
        ]
        for note in rev.get("day_coverage_notes") or []:
            lines.append(f"- *Day coverage:* {note}")
        if rev.get("day_coverage_notes"):
            lines.append("")

        lines += ["### Structure matrix (A5)", "", "| Element | Status |", "|---------|--------|"]
        for row in a5.get("matrix") or []:
            label = re.sub(r"^\d+\.\s*", "", row.get("label") or row.get("id") or "")
            lines.append(f"| {label} | **{row.get('status')}** |")
        lines.append("")

        # Cite one sample per PRESENT core for audit trail
        cites = [r for r in (a5.get("matrix") or []) if r.get("status") == "PRESENT" and r.get("cite")]
        if cites:
            lines += ["### Evidence cites (sample)", ""]
            for r in cites[:6]:
                label = re.sub(r"^\d+\.\s*", "", r.get("label") or r.get("id") or "")
                lines.append(f"- **{label}:** {r.get('cite')}")
            lines.append("")

        a3 = (rev.get("steps") or {}).get("A3") or {}
        if a3.get("mismatches"):
            lines += [
                "### Coherence mismatches (A3)",
                "",
                *[f"- `{m}`" for m in a3["mismatches"]],
                "",
            ]

    if not review.get("reviews"):
        lines += [
            "## No LP depth",
            "",
            review.get("note") or f"Mode `{mode}` has no preserved LPs to review.",
            "",
        ]

    lines += [
        "---",
        "",
        "*A6 skipped (preserve mode). A8 = this review emit + originals in `lesson-plans/`.*",
        "",
    ]
    return "\n".join(lines)
