#!/usr/bin/env python3
"""
lesson_rung.py — the LOCKED lesson rung of the curriculum waterfall.

The bake-off (lesson_bakeoff.py) compared four reused methods against a hand-seeded
gold set. Outcome on the Dallas gold (see projects/dallas-career-2026/layer_lesson/
BAKEOFF.md and docs/LESSON-RUNG.md):
  - S1 completeness (deterministic)      — mean abs error ~0.07, closest + free.
  - S3 curriculum's-own (deterministic)  — ~0.07, ties S1, adds the district bar.
  - S2 UbD / S4 quality (model)          — the local model returned UNCITED bands,
    which the auditor guard correctly downgraded to needs-review; not trustworthy
    on this model yet, so deferred (re-run the bake-off --with-model when a model
    that reliably cites evidence is available).

So the locked lesson rung is the two DETERMINISTIC, evidence-cited scorers: a
subject-agnostic completeness gate plus, where a project ships one, its own
template. This module runs them over every lesson (including TE children) and
emits ONE stable artifact — LESSON-RUNG.json — that the future unit rung consumes:
per-lesson verdicts rolled up per unit. Cheap, offline, and honest.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from audit_lib import atomic_write, log, project_dir, validate_slug_id
from lesson_scoring import build_scorer

# The methods the bake-off picked. Deterministic + evidence-cited; model methods
# stay out of the locked rung until they can cite reliably (add them here after a
# bake-off run shows they match gold). S1 is the gate; S3 is the per-project bar.
LOCKED_SCORERS = ["s1_completeness", "s3_curriculum_own"]
GATE_SCORER = "s1_completeness"  # the scorer whose required-parts gate is authoritative


def _lesson_row(lesson, results: dict) -> dict:
    """One lesson's locked-rung verdict: the gate + each method's coverage, with the
    per-criterion detail kept for drill-down (every verdict is evidence-cited)."""
    gate = results[GATE_SCORER].summary.get("gate_pass", False)
    return {
        "lesson_id": lesson.lesson_id,
        "unit_id": lesson.unit_id,
        "title": lesson.title,
        "gate_pass": gate,
        "coverage": {sid: r.summary.get("coverage") for sid, r in results.items()},
        "scores": {sid: r.to_dict() for sid, r in results.items()},
    }


def rollup_units(lesson_rows: list[dict]) -> dict:
    """Compose per-lesson rows into a per-unit summary — the handoff the unit rung
    reads. Pure (no I/O) so it is unit-testable in isolation.

    Per unit we report how many lessons cleared the completeness gate and the mean
    coverage per method; the unit rung will layer coherence + standards coverage on
    top of this (see the plan's 'Then upward' sketch)."""
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for row in lesson_rows:
        by_unit[row["unit_id"]].append(row)

    units: dict[str, dict] = {}
    for uid, rows in sorted(by_unit.items()):
        n = len(rows)
        gate_pass = sum(1 for r in rows if r["gate_pass"])
        method_means: dict[str, float] = {}
        for sid in LOCKED_SCORERS:
            vals = [
                r["coverage"].get(sid)
                for r in rows
                if r["coverage"].get(sid) is not None
            ]
            if vals:
                method_means[sid] = round(sum(vals) / len(vals), 3)
        units[uid] = {
            "lesson_count": n,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / n, 3) if n else 0.0,
            "mean_coverage": method_means,
            "lessons": [
                {
                    "lesson_id": r["lesson_id"],
                    "title": r["title"],
                    "gate_pass": r["gate_pass"],
                    "coverage": r["coverage"],
                }
                for r in rows
            ],
        }
    return units


def build_lesson_rung(project_id: str, scorer_ids: list[str] | None = None) -> Path:
    """Score every lesson with the locked scorers and write LESSON-RUNG.json (+ a
    short markdown summary). Returns the artifact path."""
    from lesson_bakeoff import enumerate_lessons  # local import avoids cycle

    ids = scorer_ids or LOCKED_SCORERS
    scorers = {sid: build_scorer(sid) for sid in ids}
    lessons = enumerate_lessons(project_id)

    lesson_rows: list[dict] = []
    for lesson in lessons:
        # Deterministic scorers ignore cfg; None keeps this offline + fast.
        results = {sid: sc.score(lesson, None) for sid, sc in scorers.items()}
        lesson_rows.append(_lesson_row(lesson, results))

    units = rollup_units(lesson_rows)
    total = len(lesson_rows)
    gate_pass = sum(1 for r in lesson_rows if r["gate_pass"])
    artifact = {
        "project_id": project_id,
        "scorers": ids,
        "gate_scorer": GATE_SCORER,
        "summary": {
            "lesson_count": total,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / total, 3) if total else 0.0,
            "unit_count": len(units),
        },
        "units": units,
        "lessons": lesson_rows,
    }

    out_dir = project_dir(project_id) / "layer_lesson"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "LESSON-RUNG.json"
    atomic_write(dest, json.dumps(artifact, indent=2))

    md = [
        "# Lesson rung (locked)",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Methods (locked):** {', '.join(ids)}  ",
        f"**Lessons:** {total}  ·  **Passed completeness gate:** {gate_pass} "
        f"({artifact['summary']['gate_pass_rate']:.0%})",
        "",
        "Per-lesson, evidence-cited detail is in `LESSON-RUNG.json`; the future unit "
        "rung reads the per-unit rollup below.",
        "",
        "| Unit | Lessons | Gate pass | " + " | ".join(ids) + " |",
        "|---|---|---|" + "|".join("---" for _ in ids) + "|",
    ]
    for uid, u in units.items():
        means = " | ".join(
            (
                f"{u['mean_coverage'].get(sid):.2f}"
                if u["mean_coverage"].get(sid) is not None
                else "—"
            )
            for sid in ids
        )
        md.append(
            f"| {uid} | {u['lesson_count']} | "
            f"{u['gate_pass_count']}/{u['lesson_count']} | {means} |"
        )
    atomic_write(out_dir / "LESSON-RUNG.md", "\n".join(md) + "\n")
    log(
        f"lesson-rung → {dest} ({total} lessons, {gate_pass} passed gate, "
        f"{len(units)} units)"
    )
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Locked lesson rung (feeds the unit rung)")
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--scorers", help="override locked scorer ids (comma-separated)"
    )
    args = ap.parse_args()
    validate_slug_id(args.project, "project id")
    ids = (
        [s.strip() for s in args.scorers.split(",") if s.strip()]
        if args.scorers
        else None
    )
    try:
        build_lesson_rung(args.project, ids)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
