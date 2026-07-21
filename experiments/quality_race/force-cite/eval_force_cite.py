#!/usr/bin/env python3
"""
eval_force_cite.py — measure the "force-cite" scorer against the shared baseline.

WHAT IT MEASURES
----------------
For each lesson we run BOTH the shared baseline `s4_quality` and the new
`s4_quality_forcecite`, then compute the SAME strict metric on both (so it is a
fair, apples-to-apples comparison):

  citation_rate = (# criteria with band>0 whose cited element_id is a real
                   candidate AND whose quote is a verbatim substring of it)
                / (# criteria with band>0)

  coverage      = (# criteria with any VALID evidence) / (# all criteria)

Plus calls_per_lesson, wall_time_per_lesson, and — for lessons that appear in the
Dallas GOLD-LESSON.json — mean absolute error of the normalized band score vs the
human gold quality (0-1).

Crucially, the metric is recomputed INDEPENDENTLY from each lesson's candidate
elements (not read from the scorer's own stored evidence). The baseline stores
evidence that only passed a LOOSE guard (id valid + non-empty); we re-check it
verbatim so both scorers are held to the same, stricter bar.

DATA REALITY
------------
The Dallas ledger may be partial (a rebuild is pending), so enumerate_lessons()
can return very few lessons. We do NOT block on that: we evaluate over whatever it
returns (capped) PLUS 3 hand-crafted mini lessons defined here — one clearly
STRONG, one WEAK/skeletal, one with an explicit ELPS/language-support sentence —
so citation behaviour is measurable deterministically regardless of the ledger.

Run:  python3 experiments/quality_race/force-cite/eval_force_cite.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Make BOTH the repo root (shared stack) and this dir (sibling scorer module)
# importable when run as a plain script from anywhere.
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]  # force-cite -> quality_race -> experiments -> repo root
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import force_cite_scorer  # noqa: F401 — registers s4_quality_forcecite / s2_ubd_forcecite
import lesson_scorers  # noqa: F401 — registers the baseline s4_quality
from audit_lib import excerpt_cited_in, load_config, log, project_dir
from lesson_bakeoff import enumerate_lessons, normalized_score
from lesson_scorers import _band_candidates
from lesson_scoring import LessonElement, LessonInput, build_scorer
from rubrics import QUALITY_RUBRIC, load_rubric

REAL_LESSON_CAP = 3  # frugal: single shared GPU
OUT_DIR = Path(__file__).resolve().parent


# --- hand-crafted mini lessons (deterministic, ledger-independent) -----------


def _mini_lessons() -> list[LessonInput]:
    """Three tiny LessonInputs whose citation behaviour is predictable, so the
    metric is meaningful even when the ledger is empty. element_type tokens match
    the quality rubric's reads_from so they surface as candidate elements."""
    strong = LessonInput(
        project_id="_mini",
        lesson_id="mini_strong",
        unit_id="mini",
        title="Mini STRONG lesson (photosynthesis)",
        elements=[
            LessonElement(
                "s-obj",
                "standards_objectives",
                "Objective: Students will be able to explain how plants convert "
                "sunlight, water, and carbon dioxide into glucose and oxygen, and "
                "diagram the inputs and outputs of photosynthesis.",
            ),
            LessonElement(
                "s-hook",
                "hook_engagement",
                "Hook: Show a time-lapse of a bean sprout growing in a dark closet "
                "versus a sunny window, then ask students why one thrived.",
            ),
            LessonElement(
                "s-di",
                "direct_instruction",
                "Direct instruction: Teacher models the photosynthesis equation "
                "6CO2 + 6H2O + light -> C6H12O6 + 6O2 and labels each reactant and "
                "product on a leaf-cross-section diagram.",
            ),
            LessonElement(
                "s-gp",
                "guided_practice",
                "Guided practice: In pairs, students trace a molecule of water from "
                "the roots to the chloroplast and predict what happens if sunlight "
                "is removed.",
            ),
            LessonElement(
                "s-cfu",
                "assessment_checkpoint",
                "Check for understanding: Exit ticket asks students to identify the "
                "two products of photosynthesis and explain one input's role.",
            ),
            LessonElement(
                "s-close",
                "reflection_closure",
                "Closure: Students write one sentence connecting photosynthesis to "
                "the oxygen they breathe, then share with a partner.",
            ),
        ],
    )
    weak = LessonInput(
        project_id="_mini",
        lesson_id="mini_weak",
        unit_id="mini",
        title="Mini WEAK lesson (skeleton)",
        elements=[
            LessonElement("w-title", "unclear", "Business Marketing Finance Lesson"),
            LessonElement("w-days", "unclear", "Day 1 / Day 2 / Day 3"),
        ],
    )
    elps = LessonInput(
        project_id="_mini",
        lesson_id="mini_elps",
        unit_id="mini",
        title="Mini ELPS-supported lesson",
        elements=[
            LessonElement(
                "e-obj",
                "standards_objectives",
                "Objective: Students will compare two career pathways using a "
                "T-chart and justify a preference in writing.",
            ),
            LessonElement(
                "e-di",
                "direct_instruction",
                "Direct instruction: Teacher defines 'pathway' and 'credential' "
                "with visuals.",
            ),
            LessonElement(
                "e-gp",
                "guided_practice",
                "Language support (ELPS): Provide sentence stems such as 'I would "
                "choose ___ because ___' and a bilingual glossary so emergent "
                "bilingual students can access the comparison task.",
            ),
        ],
    )
    return [strong, weak, elps]


# --- strict, independent metric ----------------------------------------------


def _strict_citation_stats(result, lesson: LessonInput, rubric: dict) -> dict:
    """Recompute citation validity from scratch against the lesson's candidates —
    NOT from the scorer's own stored evidence — so baseline and force-cite are
    judged by the identical, strict bar."""
    candidates = _band_candidates(lesson, rubric)
    cand_text = {el.element_id: (el.excerpt or "") for el in candidates}

    band_gt0 = 0
    valid_cited = 0
    total = len(result.criteria)
    for c in result.criteria:
        if c.band and c.band > 0:
            band_gt0 += 1
        # A citation is valid only if id is a real candidate AND quote is verbatim.
        ev = c.evidence[0] if c.evidence else None
        cited_ok = bool(
            ev
            and ev.element_id in cand_text
            and ev.excerpt
            and excerpt_cited_in(ev.excerpt, cand_text[ev.element_id])
        )
        if c.band and c.band > 0 and cited_ok:
            valid_cited += 1
    return {
        "band_gt0": band_gt0,
        "valid_cited": valid_cited,
        "total_criteria": total,
        "citation_rate": round(valid_cited / band_gt0, 3) if band_gt0 else None,
        "coverage": round(valid_cited / total, 3) if total else None,
    }


def _example_cited_band(result, rubric_title: str) -> dict | None:
    """Pull one concrete produced CITED band for the report (dimension, band,
    element_id, quote)."""
    for c in result.criteria:
        if c.band and c.band > 0 and c.evidence:
            ev = c.evidence[0]
            return {
                "rubric": rubric_title,
                "dimension": c.criterion_id,
                "label": c.label,
                "band": c.band,
                "element_id": ev.element_id,
                "quote": ev.excerpt[:240],
            }
    return None


def _agg(rates: list) -> float | None:
    vals = [r for r in rates if r is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def main() -> int:
    try:
        cfg = load_config()
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: cannot load model config: {e}")
        return 1

    rubric = load_rubric(QUALITY_RUBRIC)
    rubric_title = rubric.get("title", QUALITY_RUBRIC)

    # Gold (Dallas) for the MAE-vs-human comparison on any overlapping lessons.
    gold_path = project_dir("dallas-career-2026") / "layer_lesson" / "GOLD-LESSON.json"
    gold = json.loads(gold_path.read_text()) if gold_path.is_file() else {}

    lessons: list[LessonInput] = []
    try:
        real = enumerate_lessons("dallas-career-2026")
        # Prefer lessons that are in gold (so we get an MAE signal) then fill up.
        real.sort(key=lambda le: (le.lesson_id not in gold,))
        lessons.extend(real[:REAL_LESSON_CAP])
        log(f"enumerated {len(real)} Dallas lessons; using {len(lessons)}")
    except Exception as e:  # noqa: BLE001 — partial ledger must not block the eval
        log(f"WARN: enumerate_lessons unavailable ({e}); using mini lessons only")
    lessons.extend(_mini_lessons())

    per_lesson: list[dict] = []
    baseline_scorer = build_scorer("s4_quality")
    forcecite_scorer = build_scorer("s4_quality_forcecite")
    example_cited = None

    for lesson in lessons:
        row: dict = {"lesson_id": lesson.lesson_id, "title": lesson.title}
        for name, scorer in (
            ("baseline", baseline_scorer),
            ("forcecite", forcecite_scorer),
        ):
            t0 = time.perf_counter()
            res = scorer.score(lesson, cfg)
            dt = round(time.perf_counter() - t0, 2)
            stats = _strict_citation_stats(res, lesson, rubric)
            norm = normalized_score(res)
            gold_q = (gold.get(lesson.lesson_id) or {}).get("quality")
            row[name] = {
                "error": res.error,
                "calls": (res.cost or {}).get("model_calls", 0),
                "wall_time_s": dt,
                "normalized": norm,
                "gold_quality": gold_q,
                "abs_error": (
                    round(abs(norm - float(gold_q)), 3)
                    if norm is not None and gold_q is not None
                    else None
                ),
                **stats,
                "forced_zero": (res.summary or {}).get("forced_zero"),
            }
            if name == "forcecite" and example_cited is None:
                example_cited = _example_cited_band(res, rubric_title)
        per_lesson.append(row)
        log(
            f"scored {lesson.title}: "
            f"baseline cite={row['baseline']['citation_rate']} "
            f"forcecite cite={row['forcecite']['citation_rate']} "
            f"(calls {row['forcecite']['calls']}, {row['forcecite']['wall_time_s']}s)"
        )

    # Aggregate.
    def col(name, key):
        return [r[name][key] for r in per_lesson]

    summary = {
        "lessons_evaluated": len(per_lesson),
        "baseline": {
            "citation_rate": _agg(col("baseline", "citation_rate")),
            "coverage": _agg(col("baseline", "coverage")),
            "calls_per_lesson": _agg(col("baseline", "calls")),
            "wall_time_per_lesson": _agg(col("baseline", "wall_time_s")),
            "gold_mae": _agg(col("baseline", "abs_error")),
        },
        "forcecite": {
            "citation_rate": _agg(col("forcecite", "citation_rate")),
            "coverage": _agg(col("forcecite", "coverage")),
            "calls_per_lesson": _agg(col("forcecite", "calls")),
            "wall_time_per_lesson": _agg(col("forcecite", "wall_time_s")),
            "gold_mae": _agg(col("forcecite", "abs_error")),
        },
        "example_cited_band": example_cited,
    }
    b = summary["baseline"]["citation_rate"]
    f = summary["forcecite"]["citation_rate"]
    summary["citation_rate_lift"] = (
        round(f - b, 3) if (b is not None and f is not None) else None
    )

    out = {"summary": summary, "per_lesson": per_lesson}
    (OUT_DIR / "eval_results.json").write_text(json.dumps(out, indent=2))
    print("\n=== FORCE-CITE EVAL SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nfull results -> {OUT_DIR / 'eval_results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
