#!/usr/bin/env python3
"""
emit.py — Write spike outputs: preserve LPs, meeting_span, Path A depth, optional gap plate.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from audit_lib import BASE_DIR, atomic_write, log, project_dir
from experiments.lesson_preserve.path_a_depth import (
    render_path_a_review_md,
    run_path_a_depth,
)
from experiments.lesson_preserve.path_a_modes import build_path_a_stub


def spike_out_root(project_id: str) -> Path:
    return BASE_DIR / "experiments" / "lesson_preserve" / "out" / project_id


def preserve_lesson_plans(
    project_id: str,
    unit_id: str,
    lesson_plans: list[dict],
    unit_out: Path,
) -> list[dict]:
    """Copy original sources into units/<unit>/lesson-plans/ (preserve, don't remake)."""
    root = project_dir(project_id)
    sources = root / "sources"
    dest = unit_out / "lesson-plans"
    dest.mkdir(parents=True, exist_ok=True)
    preserved: list[dict] = []
    for lp in lesson_plans:
        src_name = lp.get("source_file") or ""
        src = sources / src_name
        if not src.is_file():
            alt = root / (lp.get("source_rel") or "")
            src = alt if alt.is_file() else src
        entry = {
            **lp,
            "preserved_path": None,
            "preserved": False,
        }
        if src.is_file():
            target = dest / src.name
            shutil.copy2(src, target)
            entry["preserved_path"] = str(target.relative_to(spike_out_root(project_id)))
            entry["preserved"] = True
        else:
            pointer = dest / f"{lp.get('doc_id')}.POINTER.txt"
            pointer.write_text(
                f"Missing source copy for {lp.get('doc_id')}\n"
                f"expected: {src_name}\n",
                encoding="utf-8",
            )
            entry["preserved_path"] = str(pointer.relative_to(spike_out_root(project_id)))
        preserved.append(entry)
    return preserved


def maybe_synthesize_gap_plate(
    project_id: str,
    unit_id: str,
    *,
    title: str,
    mode: str,
    unit_out: Path,
    title_map: dict[str, str],
    manifest: dict,
) -> dict | None:
    """Create structure plate only for synthesize_missing — gap visible."""
    if mode != "synthesize_missing":
        return None
    from lesson_plan_fill import fill_lesson_plan, render_lesson_plan_md

    filled = fill_lesson_plan(
        project_id, unit_id, manifest=manifest, title_map=title_map
    )
    md = render_lesson_plan_md(filled)
    banner = (
        f"# GAP plate (synthesize_missing) — {title}\n\n"
        "**Signal said a lesson plan should exist; none was found in the LP group.** "
        "This is a structure inventory from fragments — not authored curriculum. "
        "Blank / MISSING = gap.\n\n---\n\n"
    )
    md = banner + md
    atomic_write(unit_out / "GAP-LESSON-STRUCTURE.md", md)
    atomic_write(
        unit_out / "GAP-LESSON-STRUCTURE.json",
        json.dumps(
            {
                "note": "Created only because signal expects LP and group was empty",
                "path_a_mode": "synthesize_missing",
                "filled_summary": filled.get("summary"),
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    log(f"spike gap plate → {unit_out / 'GAP-LESSON-STRUCTURE.md'}")
    return {"path": "GAP-LESSON-STRUCTURE.md", "reason": "synthesize_missing"}


def write_unit_outputs(
    project_id: str,
    org: dict[str, Any],
    meeting: dict[str, Any],
    *,
    title_map: dict[str, str],
    manifest: dict,
) -> dict[str, Any]:
    out_root = spike_out_root(project_id)
    unit_id = org["unit_id"]
    unit_out = out_root / "units" / unit_id
    unit_out.mkdir(parents=True, exist_ok=True)

    preserved = preserve_lesson_plans(
        project_id, unit_id, org.get("lesson_plans") or [], unit_out
    )
    atomic_write(
        unit_out / "meeting_span.json",
        json.dumps(meeting, indent=2, ensure_ascii=False),
    )

    stub = build_path_a_stub(org, meeting)
    atomic_write(unit_out / "path_a_stub.md", stub)

    depth = run_path_a_depth(project_id, org, meeting)
    depth_summary = None
    if depth.get("reviews"):
        atomic_write(
            unit_out / "path_a_review.json",
            json.dumps(depth, indent=2, ensure_ascii=False),
        )
        atomic_write(
            unit_out / "path_a_review.md",
            render_path_a_review_md(depth),
        )
        depth_summary = {
            "depth": depth.get("depth"),
            "plans_reviewed": len(depth.get("reviews") or []),
            "summaries": [r.get("summary") for r in depth.get("reviews") or []],
            "group_notes": (depth.get("group") or {}).get("notes"),
        }
        log(
            f"spike Path A depth → {unit_out / 'path_a_review.md'} "
            f"({depth.get('depth')}, {len(depth.get('reviews') or [])} plan(s))"
        )

    gap = maybe_synthesize_gap_plate(
        project_id,
        unit_id,
        title=org.get("title") or unit_id,
        mode=org.get("path_a_mode") or "",
        unit_out=unit_out,
        title_map=title_map,
        manifest=manifest,
    )

    readme = [
        f"# {org.get('title') or unit_id}",
        "",
        f"- **path_a_mode:** `{org.get('path_a_mode')}`",
        f"- **lesson_plan_count:** {org.get('lesson_plan_count')}",
        f"- **meeting_count:** {meeting.get('meeting_count')} "
        f"({meeting.get('meeting_source') or 'unknown'})",
        "",
        "## Preserved lesson plans",
        "",
    ]
    if preserved:
        for p in preserved:
            readme.append(
                f"- {'OK' if p.get('preserved') else 'POINTER'} "
                f"**{p.get('title')}** → `{p.get('preserved_path')}`"
            )
    else:
        readme.append("- *(none — LP group empty)*")
    if depth_summary:
        readme += [
            "",
            "## Path A depth",
            "",
            f"- `{depth_summary.get('depth')}` — see `path_a_review.md`",
        ]
        for i, s in enumerate(depth_summary.get("summaries") or [], start=1):
            readme.append(
                f"- Plan {i}: coherence={s.get('coherence')} "
                f"structure={s.get('hunter_core_present')}/{s.get('hunter_core_total')}"
            )
    if gap:
        readme += ["", "## Gap plate", "", f"- `{gap['path']}`"]
    atomic_write(unit_out / "README.md", "\n".join(readme) + "\n")

    return {
        "unit_id": unit_id,
        "path_a_mode": org.get("path_a_mode"),
        "lesson_plan_count": org.get("lesson_plan_count"),
        "lesson_plans": preserved,
        "meeting_count": meeting.get("meeting_count"),
        "meeting_source": meeting.get("meeting_source"),
        "gap_plate": gap,
        "path_a_depth": depth_summary,
    }
