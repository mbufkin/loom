#!/usr/bin/env python3
"""
path_a_modes.py — Path A mode headers: single_lp vs lp_block vs synthesize_missing.

Depth review lives in path_a_depth.py (A1–A7 on preserved LPs).
"""

from __future__ import annotations

from typing import Any


def build_path_a_stub(org: dict[str, Any], meeting: dict[str, Any]) -> str:
    """Markdown stub describing which Path A mode would run and why."""
    mode = org.get("path_a_mode")
    title = org.get("title") or org.get("unit_id")
    lps = org.get("lesson_plans") or []
    mc = meeting.get("meeting_count")
    ms = meeting.get("meeting_source")

    lines = [
        f"# Path A stub — {title}",
        "",
        f"**Unit:** `{org.get('unit_id')}`  ",
        f"**Mode:** `{mode}`  ",
        f"**Lesson plans preserved:** {len(lps)}  ",
        f"**Meeting count (metadata):** {mc if mc is not None else 'unknown'}"
        + (f" (`{ms}`)" if ms else ""),
        "",
    ]

    if mode == "single_lp" and lps:
        lp = lps[0]
        lines += [
            "## Mode: `single_lp`",
            "",
            "Review **this one** lesson plan deeply — structure, UbD coherence, "
            "and whether day claims inside *this* document match `meeting_count`.",
            "",
            f"- **Title:** {lp.get('title')}",
            f"- **doc_id:** `{lp.get('doc_id')}`",
            f"- **source:** `{lp.get('source_file')}`",
            f"- **detect:** {', '.join(lp.get('detect_reasons') or [])}",
            "",
            "### Review focus (not a scrap rebuild)",
            "",
            "- Preserve the author's plan; score presence/gaps against checklist",
            "- If the plan claims N days, note coverage inside this file only",
            "- Do **not** mash other unit docs into a replacement LESSON-PLAN.pdf",
            "",
        ]
    elif mode == "lp_block":
        lines += [
            "## Mode: `lp_block`",
            "",
            "Review the **set** of lesson plans together — different from a single-doc pass. "
            "Ask how they fit the unit: overlap, gaps between plans, joint meeting coverage.",
            "",
            "### Plans in group",
            "",
        ]
        for i, lp in enumerate(lps, start=1):
            lines.append(
                f"{i}. **{lp.get('title')}** — `{lp.get('doc_id')}` "
                f"({', '.join(lp.get('detect_reasons') or [])})"
            )
        lines += [
            "",
            "### Block review focus",
            "",
            "- Each plan still gets piece-by-piece evidence review",
            "- Plus group questions: alternate vs sequential? joint `meeting_count`?",
            "- Still **preserve** originals — do not merge into one remade plate",
            "",
        ]
    elif mode == "synthesize_missing":
        lines += [
            "## Mode: `synthesize_missing`",
            "",
            "Signal says a lesson plan **should** exist, but the LP group is empty. "
            "Emit a **gap** structure inventory (test draft) so the missing artifact is visible. "
            "Do not invent teachable curriculum — blanks stay blanks.",
            "",
        ]
    elif mode == "none":
        lines += [
            "## Mode: `none`",
            "",
            "No lesson plans found and no strong signal that one must exist. "
            "No LP plate created.",
            "",
        ]
    else:
        lines += [
            f"## Mode: `{mode}`",
            "",
            "(Unresolved — run signal resolution.)",
            "",
        ]

    lines += [
        "---",
        "",
        "## Path order reminder",
        "",
        "1. Organize inventory",
        "2. Non-LP document paths",
        "3. **Path A on LP group last** (this stub)",
        "",
    ]
    return "\n".join(lines)


def resolve_mode_with_signal(
    org: dict[str, Any],
    *,
    expects_lp: bool,
    expect_reasons: list[str],
) -> dict[str, Any]:
    """Finalize path_a_mode when LP group is empty."""
    out = dict(org)
    if out.get("lesson_plan_count", 0) > 0:
        out["expects_lesson_plan"] = True
        out["expect_reasons"] = ["lp_group_nonempty"]
        return out
    out["expects_lesson_plan"] = expects_lp
    out["expect_reasons"] = expect_reasons
    if expects_lp:
        out["path_a_mode"] = "synthesize_missing"
    else:
        out["path_a_mode"] = "none"
    return out
