#!/usr/bin/env python3
"""
eval_feedback.py — measure FEEDBACK QUALITY (not band-vs-gold MAE).

Metrics per scorer, over the enumerated Dallas lessons:
  * note_coverage   : fraction of dimensions with a SUBSTANTIVE note
                      (>= MIN_CHARS after stripping the needs-review tag).
  * specificity     : mean fraction of a note's content words that also appear
                      in the lesson's own text — a proxy for "grounded in THIS
                      lesson" vs generic filler.
  * avg_note_len    : mean characters per note.
  * calls_per_lesson, wall_time.
It also prints every note side by side so a human can eyeball which reads better.

Run: python3 experiments/quality_race/feedback/eval_feedback.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import feedback_scorer  # noqa: F401 — registers s4_quality_feedback
import lesson_scorers  # noqa: F401 — registers baseline s4_quality
from audit_lib import load_config, log
from lesson_bakeoff import enumerate_lessons
from lesson_scoring import build_scorer

PROJECT = "dallas-career-2026"
MIN_CHARS = 40
NEEDS_REVIEW = "[unevidenced band — needs review]"
_STOP = set(
    "the a an and or of to in is are for with that this it its as on at be by "
    "not no than then so student students lesson band note".split()
)


def _clean(note: str) -> str:
    return (note or "").replace(NEEDS_REVIEW, "").strip()


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in _STOP}


def _specificity(note: str, lesson_text_words: set[str]) -> float | None:
    nw = _content_words(_clean(note))
    if not nw:
        return None
    return round(len(nw & lesson_text_words) / len(nw), 3)


def main() -> int:
    cfg = load_config()
    lessons = enumerate_lessons(PROJECT)
    log(f"enumerated {len(lessons)} lessons")

    scorer_ids = ["s4_quality", "s4_quality_feedback"]
    scorers = {sid: build_scorer(sid) for sid in scorer_ids}

    agg: dict[str, dict] = {sid: {"cov": [], "spec": [], "len": [], "calls": [], "t": []} for sid in scorer_ids}

    for le in lessons:
        lesson_words = _content_words(" ".join(e.excerpt or "" for e in le.elements))
        print("=" * 90)
        print(f"LESSON: {le.title}  ({len(le.elements)} elements)")
        results = {}
        for sid, scorer in scorers.items():
            t0 = time.perf_counter()
            res = scorer.score(le, cfg)
            dt = round(time.perf_counter() - t0, 2)
            results[sid] = res
            covered = specs = 0
            for c in res.criteria:
                clean = _clean(c.note)
                if len(clean) >= MIN_CHARS:
                    covered += 1
                sp = _specificity(c.note, lesson_words)
                if sp is not None:
                    agg[sid]["spec"].append(sp)
                agg[sid]["len"].append(len(clean))
            n = len(res.criteria) or 1
            agg[sid]["cov"].append(round(covered / n, 3))
            agg[sid]["calls"].append((res.cost or {}).get("model_calls", 0))
            agg[sid]["t"].append(dt)
        # side-by-side notes per dimension
        base, feat = results["s4_quality"], results["s4_quality_feedback"]
        fmap = {c.criterion_id: c for c in feat.criteria}
        for c in base.criteria:
            f = fmap.get(c.criterion_id)
            print(f"  • {c.label}")
            print(f"      baseline [{c.band}]: {(_clean(c.note) or '—')[:150]}")
            print(f"      feedback [{f.band if f else '-'}]: {(_clean(f.note) if f else '—')[:150]}")
        print()

    def _m(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 3) if xs else None

    summary = {
        sid: {
            "note_coverage": _m(agg[sid]["cov"]),
            "specificity": _m(agg[sid]["spec"]),
            "avg_note_len": _m(agg[sid]["len"]),
            "calls_per_lesson": _m(agg[sid]["calls"]),
            "wall_per_lesson": _m(agg[sid]["t"]),
        }
        for sid in scorer_ids
    }
    (_HERE / "eval_feedback_results.json").write_text(json.dumps(summary, indent=2))
    print("=== FEEDBACK-QUALITY SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
