#!/usr/bin/env python3
"""
calibrate_gold.py — the real calibration the race deferred.

The race proved citation MECHANICS on hand-crafted mini lessons because the
Dallas ledger was truncated (0 id-overlap with GOLD-LESSON.json). Once the
ledger is rebuilt from cache, the 7 human-scored gold lessons enumerate again.
This script scores EXACTLY those gold-overlapping lessons with the baseline and
the force-cite winner, and reports the metric that actually gates promotion:

    gold MAE = mean |normalized_band_score - human_quality(0-1)|

plus the strict citation_rate (recomputed independently, same bar for both), so
we can see both "does it cite?" (mechanics) and "is it right?" (calibration).

Run:  python3 experiments/quality_race/force-cite/calibrate_gold.py
Optionally add a third scorer id as argv[1] (e.g. a grounded/hybrid id already
registered on the import path).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import force_cite_scorer  # noqa: F401 — registers s4_quality_forcecite
import lesson_scorers  # noqa: F401 — registers baseline s4_quality
from audit_lib import load_config, log, project_dir
from eval_force_cite import _example_cited_band, _strict_citation_stats
from lesson_bakeoff import enumerate_lessons, normalized_score
from lesson_scoring import build_scorer
from rubrics import QUALITY_RUBRIC, load_rubric

PROJECT = "dallas-career-2026"


def _gold_quality(gold: dict, lesson_id: str) -> float | None:
    rec = gold.get(lesson_id)
    if not isinstance(rec, dict):
        return None
    q = rec.get("quality")
    return float(q) if q is not None else None


def main() -> int:
    cfg = load_config()
    rubric = load_rubric(QUALITY_RUBRIC)

    gold_path = project_dir(PROJECT) / "layer_lesson" / "GOLD-LESSON.json"
    gold = json.loads(gold_path.read_text()) if gold_path.is_file() else {}
    gold_ids = {k for k in gold if k != "_meta"}
    log(f"gold set has {len(gold_ids)} lessons")

    lessons = enumerate_lessons(PROJECT)
    log(f"enumerated {len(lessons)} Dallas lessons from ledger")
    gold_lessons = [le for le in lessons if le.lesson_id in gold_ids]
    found = {le.lesson_id for le in gold_lessons}
    missing = gold_ids - found
    log(f"matched {len(gold_lessons)}/{len(gold_ids)} gold lessons; missing={sorted(missing)}")
    if not gold_lessons:
        log("ERROR: no gold lessons materialized — is the ledger complete?")
        return 1

    # Scorers under test: baseline + force-cite (+ optional third from argv).
    scorer_ids = ["s4_quality", "s4_quality_forcecite"]
    if len(sys.argv) > 1:
        scorer_ids.append(sys.argv[1])
    scorers = {sid: build_scorer(sid) for sid in scorer_ids}

    per_lesson: list[dict] = []
    example_cited = None
    for lesson in gold_lessons:
        gq = _gold_quality(gold, lesson.lesson_id)
        row: dict = {
            "lesson_id": lesson.lesson_id,
            "title": lesson.title,
            "elements": len(lesson.elements),
            "gold_quality": gq,
        }
        for sid, scorer in scorers.items():
            t0 = time.perf_counter()
            res = scorer.score(lesson, cfg)
            dt = round(time.perf_counter() - t0, 2)
            norm = normalized_score(res)
            stats = _strict_citation_stats(res, lesson, rubric)
            row[sid] = {
                "error": res.error,
                "normalized": norm,
                "abs_error": (
                    round(abs(norm - gq), 3)
                    if norm is not None and gq is not None
                    else None
                ),
                "calls": (res.cost or {}).get("model_calls", 0),
                "wall_s": dt,
                "citation_rate": stats["citation_rate"],
                "coverage": stats["coverage"],
            }
            if sid == "s4_quality_forcecite" and example_cited is None:
                example_cited = _example_cited_band(res, rubric.get("title", ""))
        per_lesson.append(row)
        log(
            f"  {lesson.title[:48]:48s} gold={gq} "
            + " ".join(
                f"{sid.split('_')[-1]}={row[sid]['normalized']}(cite {row[sid]['citation_rate']})"
                for sid in scorer_ids
            )
        )

    def _agg(sid: str, key: str) -> float | None:
        vals = [r[sid][key] for r in per_lesson if r[sid][key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    summary = {
        "gold_lessons_scored": len(per_lesson),
        "gold_lessons_total": len(gold_ids),
        "by_scorer": {
            sid: {
                "gold_mae": _agg(sid, "abs_error"),
                "citation_rate": _agg(sid, "citation_rate"),
                "coverage": _agg(sid, "coverage"),
                "calls_per_lesson": _agg(sid, "calls"),
                "wall_per_lesson": _agg(sid, "wall_s"),
            }
            for sid in scorer_ids
        },
        "example_cited_band": example_cited,
    }
    out = {"summary": summary, "per_lesson": per_lesson}
    (_HERE / "calibrate_gold_results.json").write_text(json.dumps(out, indent=2))
    print("\n=== GOLD CALIBRATION SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nfull results -> {_HERE / 'calibrate_gold_results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
