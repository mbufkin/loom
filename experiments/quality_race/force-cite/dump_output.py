#!/usr/bin/env python3
"""
dump_output.py — forget the gold score for a moment; show what each scorer
ACTUALLY produced on each lesson: per-dimension band, verdict, the cited
evidence, and the model/code note. This answers "did the model give output on
the lessons?" directly, in human-readable form.

Run: python3 experiments/quality_race/force-cite/dump_output.py [scorer_id]
     (default scorer_id = s4_quality_forcecite)
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import force_cite_scorer  # noqa: F401
import lesson_scorers  # noqa: F401
from audit_lib import load_config
from lesson_bakeoff import enumerate_lessons
from lesson_scoring import build_scorer

PROJECT = "dallas-career-2026"


def main() -> int:
    scorer_id = sys.argv[1] if len(sys.argv) > 1 else "s4_quality_forcecite"
    cfg = load_config()
    scorer = build_scorer(scorer_id)
    lessons = enumerate_lessons(PROJECT)

    print(f"\n################ SCORER: {scorer_id} ################\n")
    for le in lessons:
        res = scorer.score(le, cfg)
        print("=" * 88)
        print(f"LESSON: {le.title}  ({len(le.elements)} elements, id={le.lesson_id})")
        if res.error:
            print(f"  ERROR: {res.error}")
            continue
        summ = res.summary or {}
        print(
            f"  summary: mean_band={summ.get('mean_band')} "
            f"max_band={summ.get('max_band')} scoring={res.scoring} "
            f"calls={(res.cost or {}).get('model_calls')}"
        )
        for c in res.criteria:
            band = c.band if c.band is not None else "-"
            ev = c.evidence[0] if c.evidence else None
            quote = (ev.excerpt[:150].replace("\n", " ") if ev and ev.excerpt else "—")
            eid = ev.element_id if ev else "—"
            note = (c.note or "")[:120].replace("\n", " ")
            print(f"  [{band}] {c.label:26s} verdict={c.verdict}")
            print(f"        cite={eid}: {quote}")
            if note:
                print(f"        note: {note}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
