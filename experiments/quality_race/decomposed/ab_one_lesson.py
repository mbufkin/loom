#!/usr/bin/env python3
"""
ab_one_lesson.py — single-lesson A/B: baseline single-pass quality scorer vs. the
research-backed decomposed (per-criterion, evidence-first, reranked) scorer.

We validate the redesign on ONE lesson whose ground truth we can read with our own
eyes — Algebra I Module 2, Lesson 2 — where the baseline emits a known FALSE NEGATIVE
(objective clarity = 0 despite objectives printed verbatim). Success = that dimension
flips to a defensible band WITH a cited quote, without the other dimensions collapsing.

No gold set involved (deferred by decision) — this isolates the design change.

Usage:
  python3 experiments/quality_race/decomposed/ab_one_lesson.py \
      [project_id] [lesson_id_substring]
Defaults: bluebonnet-math-2026  Module_2.pdf__L2
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
# Register both scorers.
sys.path.insert(0, str(_REPO_ROOT / "experiments" / "quality_race" / "feedback"))
sys.path.insert(0, str(_HERE))

import decomposed_scorer  # noqa: F401,E402 — registers s4_quality_decomposed
import feedback_scorer  # noqa: F401,E402 — registers s4_quality_feedback
from audit_lib import load_config  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402
from lesson_scoring import build_scorer  # noqa: E402

BASELINE = "s4_quality_feedback"
DECOMPOSED = "s4_quality_decomposed"
BAND_LABEL = {0: "Absent", 1: "Weak", 2: "Developing", 3: "Strong", None: "—"}


def _bar(band) -> str:
    n = band if isinstance(band, int) else 0
    return "●" * n + "○" * (3 - n)


def _by_id(res):
    return {c.criterion_id: c for c in res.criteria}


def main() -> int:
    project = sys.argv[1] if len(sys.argv) > 1 else "bluebonnet-math-2026"
    needle = sys.argv[2] if len(sys.argv) > 2 else "Module_2.pdf__L2"

    lessons = enumerate_lessons(project)
    matches = [le for le in lessons if needle in le.lesson_id]
    if not matches:
        print(f"no lesson matching '{needle}' in {project}")
        print("available (first 20):")
        for le in lessons[:20]:
            print("  ", le.lesson_id)
        return 1
    lesson = matches[0]

    cfg = load_config()
    print("=" * 92)
    print(f"A/B  project={project}")
    print(f"lesson={lesson.lesson_id}")
    print(f"title={lesson.title}")
    print(f"elements={len(lesson.elements)}")
    print("=" * 92)

    print("\n[running baseline single-pass ...]")
    base = build_scorer(BASELINE).score(lesson, cfg)
    print("[running decomposed per-criterion evidence-first ...]")
    dec = build_scorer(DECOMPOSED).score(lesson, cfg)

    b_by, d_by = _by_id(base), _by_id(dec)

    print("\n" + "-" * 92)
    print(f"{'DIMENSION':32} | {'BASELINE':>14} | {'DECOMPOSED':>14} | cited?")
    print("-" * 92)
    for cid in b_by:
        bc = b_by.get(cid)
        dc = d_by.get(cid)
        bb = f"{_bar(bc.band)} {BAND_LABEL.get(bc.band,'—')}" if bc else "—"
        db = f"{_bar(dc.band)} {BAND_LABEL.get(dc.band,'—')}" if dc else "—"
        cited = "yes" if (dc and dc.evidence) else "no"
        label = (bc.label if bc else cid)[:32]
        print(f"{label:32} | {bb:>14} | {db:>14} | {cited}")

    def mean(res):
        return (res.summary or {}).get("mean_band")

    print("-" * 92)
    print(
        f"{'MEAN BAND (/3)':32} | {str(mean(base)):>14} | {str(mean(dec)):>14} |"
        f"  calls: base={ (base.cost or {}).get('model_calls') }"
        f" dec={ (dec.cost or {}).get('model_calls') }"
    )

    # Full decomposed detail — the reasoning + cited quote per dimension, so we can
    # eyeball whether the flips are justified rather than trusting the number.
    print("\n" + "=" * 92)
    print("DECOMPOSED — reasoning + evidence per dimension")
    print("=" * 92)
    for c in dec.criteria:
        print(f"\n• {c.label}: {_bar(c.band)} {BAND_LABEL.get(c.band,'—')}")
        print(f"    {(c.note or '').strip()}")
        for e in c.evidence or []:
            q = (e.excerpt or "").replace("\n", " ")[:180]
            print(f"    ↳ [{e.element_id}] \"{q}\"")

    print("\n" + "=" * 92)
    print("BASELINE — note per dimension (for contrast)")
    print("=" * 92)
    for c in base.criteria:
        print(f"\n• {c.label}: {_bar(c.band)} {BAND_LABEL.get(c.band,'—')}")
        print(f"    {(c.note or '').strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
