#!/usr/bin/env python3
"""
run_eval.py — measure the extractive-2stage quality scorer against the baseline.

WHAT IT DOES
------------
1. Builds the eval set:
     (a) whatever ``enumerate_lessons("dallas-career-2026")`` returns (the ledger is
         PARTIAL right now, so this may be only ~2-3 lessons), capped for frugality;
     (b) THREE hand-crafted mini LessonInput objects — one clearly STRONG, one
         WEAK/skeletal, one carrying an explicit ELPS/language-support sentence — so
         citation behaviour is measurable deterministically regardless of the ledger.
2. Runs, on each lesson, BOTH:
     * baseline  ``s4_quality``            (one big all-dimensions call)
     * candidate ``s4_quality_extractive`` (one focused call per dimension)
3. Computes and reports the race metrics:
     * PRIMARY citation_rate = (#criteria band>0 with a VALID citation) /
                               (#criteria band>0)
       where VALID = evidence element_id resolves to a real lesson element AND the
       quote is a verbatim (whitespace-insensitive) substring of that element.
     * coverage = fraction of ALL criteria with a valid citation.
     * calls_per_lesson, wall_time_per_lesson (extractive is expected to cost more —
       we report the tradeoff honestly).
     * gold MAE for any lessons overlapping GOLD-LESSON.json.

Auditor-only + additive-only: this harness only READS shared modules and writes its
outputs under this experiment folder.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import dataclass

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Importing the scorer module registers s4_quality_extractive; importing
# lesson_scorers registers the shared baseline s4_quality.
import extractive_scorer  # noqa: F401,E402  (registers extractive scorers)
import lesson_scorers  # noqa: F401,E402  (registers baseline scorers)
from audit_lib import load_config  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402
from lesson_scoring import (  # noqa: E402
    LessonElement,
    LessonInput,
    ScorerResult,
    build_scorer,
)

BASELINE_ID = "s4_quality"
CANDIDATE_ID = "s4_quality_extractive"
DALLAS = "dallas-career-2026"
DALLAS_LIMIT = 3  # frugal: single shared local GPU


# --- hand-crafted deterministic lessons -------------------------------------
# These make citation behaviour measurable no matter what the partial ledger holds.
# Every excerpt is plain, self-contained lesson prose the model can quote verbatim.


def _mini_lessons() -> list[LessonInput]:
    strong = LessonInput(
        project_id="_synthetic",
        lesson_id="synthetic-strong",
        unit_id="synthetic",
        title="[synthetic] STRONG photosynthesis lesson",
        elements=[
            LessonElement(
                "strong-e1",
                "standards_objectives",
                "Objective: Students will be able to explain how plants convert "
                "sunlight, water, and carbon dioxide into glucose and oxygen, and "
                "diagram the inputs and outputs of photosynthesis.",
            ),
            LessonElement(
                "strong-e2",
                "hook_engagement",
                "Hook: Show a time-lapse of a bean seed sprouting in a dark closet "
                "versus a sunny window, then ask students to predict why one thrived.",
            ),
            LessonElement(
                "strong-e3",
                "direct_instruction",
                "Direct instruction: Teacher models the photosynthesis equation "
                "6CO2 + 6H2O + light -> C6H12O6 + 6O2, labeling each reactant and "
                "product on a diagram of a chloroplast.",
            ),
            LessonElement(
                "strong-e4",
                "guided_practice",
                "Guided practice: In pairs, students trace a carbon atom from the "
                "air into a glucose molecule, explaining each step to a partner.",
            ),
            LessonElement(
                "strong-e5",
                "assessment_checkpoint",
                "Checkpoint: On an exit ticket, each student labels the inputs and "
                "outputs on a blank photosynthesis diagram and writes one sentence "
                "explaining why plants need sunlight.",
            ),
            LessonElement(
                "strong-e6",
                "reflection_closure",
                "Closure: Students revisit their opening prediction and write two "
                "sentences on what they would now tell a friend about why the plant "
                "in the closet died.",
            ),
        ],
    )
    weak = LessonInput(
        project_id="_synthetic",
        lesson_id="synthetic-weak",
        unit_id="synthetic",
        title="[synthetic] WEAK skeletal lesson",
        elements=[
            LessonElement(
                "weak-e1",
                "standards_objectives",
                "Career unit.",
            ),
            LessonElement(
                "weak-e2",
                "unclear",
                "Day 1. Day 2. Day 3.",
            ),
        ],
    )
    elps = LessonInput(
        project_id="_synthetic",
        lesson_id="synthetic-elps",
        unit_id="synthetic",
        title="[synthetic] ELPS language-support lesson",
        elements=[
            LessonElement(
                "elps-e1",
                "standards_objectives",
                "Objective: Students will compare two career clusters and justify a "
                "preference in writing.",
            ),
            LessonElement(
                "elps-e2",
                "direct_instruction",
                "Language support (ELPS): Provide sentence stems for emergent "
                "bilingual students — 'I would choose the ____ cluster because ____' "
                "— and a bilingual glossary of the cluster names.",
            ),
            LessonElement(
                "elps-e3",
                "guided_practice",
                "Guided practice: Students use the sentence stems to tell a partner "
                "which cluster they prefer before writing independently.",
            ),
            LessonElement(
                "elps-e4",
                "assessment_checkpoint",
                "Checkpoint: Collect the written justification and check that each "
                "student used at least one comparison word (more, less, better).",
            ),
        ],
    )
    return [strong, weak, elps]


# --- metric machinery -------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _valid_citation(cr, lesson: LessonInput) -> bool:
    """A criterion's citation is VALID iff it has evidence whose element_id resolves
    to a real element in THIS lesson and whose quote is a verbatim (whitespace-
    insensitive) substring of that element. This is applied identically to baseline
    and candidate so the comparison is fair."""
    if not cr.evidence:
        return False
    by_id = {el.element_id: el for el in lesson.elements}
    for ev in cr.evidence:
        el = by_id.get(ev.element_id)
        if el is None:
            continue
        q = _normalize(ev.excerpt)
        if len(q) >= 8 and q in _normalize(el.excerpt or ""):
            return True
    return False


@dataclass
class LessonMetric:
    lesson_id: str
    title: str
    scorer_id: str
    n_criteria: int
    n_band_pos: int  # criteria with band > 0
    n_valid_cited: int  # criteria with a valid citation
    n_band_pos_valid: int  # criteria band>0 AND valid citation
    citation_rate: float | None  # n_band_pos_valid / n_band_pos
    coverage: float  # n_valid_cited / n_criteria
    model_calls: int
    wall_seconds: float
    mean_band: float | None
    normalized: float | None  # mean_band / max_band -> 0..1 for gold MAE
    error: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _measure(result: ScorerResult, lesson: LessonInput, wall: float) -> LessonMetric:
    crits = result.criteria
    band_pos = [c for c in crits if (c.band or 0) > 0]
    valid = [c for c in crits if _valid_citation(c, lesson)]
    band_pos_valid = [c for c in band_pos if _valid_citation(c, lesson)]
    n_crit = len(crits) or 1
    bands = [c.band for c in crits if c.band is not None]
    mean_band = round(statistics.mean(bands), 3) if bands else None
    max_band = result.summary.get("max_band") or 3
    normalized = (
        round(mean_band / max_band, 3) if mean_band is not None and max_band else None
    )
    citation_rate = (
        round(len(band_pos_valid) / len(band_pos), 3) if band_pos else None
    )
    return LessonMetric(
        lesson_id=lesson.lesson_id,
        title=lesson.title,
        scorer_id=result.scorer_id,
        n_criteria=len(crits),
        n_band_pos=len(band_pos),
        n_valid_cited=len(valid),
        n_band_pos_valid=len(band_pos_valid),
        citation_rate=citation_rate,
        coverage=round(len(valid) / n_crit, 3),
        model_calls=(result.cost or {}).get("model_calls", 0),
        wall_seconds=round(wall, 2),
        mean_band=mean_band,
        normalized=normalized,
        error=result.error,
    )


def _run_scorer(scorer_id: str, lesson: LessonInput, cfg: dict) -> LessonMetric:
    scorer = build_scorer(scorer_id)
    t0 = time.time()
    result = scorer.score(lesson, cfg)
    wall = time.time() - t0
    return _measure(result, lesson, wall), result


def _aggregate(metrics: list[LessonMetric]) -> dict:
    """Pool metrics the citation-rate way: sum numerators/denominators across lessons
    (a lesson with more band>0 criteria weighs more), plus report simple per-lesson
    averages for the cost columns."""
    tot_band_pos = sum(m.n_band_pos for m in metrics)
    tot_band_pos_valid = sum(m.n_band_pos_valid for m in metrics)
    tot_crit = sum(m.n_criteria for m in metrics)
    tot_valid = sum(m.n_valid_cited for m in metrics)
    return {
        "lessons": len(metrics),
        "citation_rate": (
            round(tot_band_pos_valid / tot_band_pos, 3) if tot_band_pos else None
        ),
        "coverage": round(tot_valid / tot_crit, 3) if tot_crit else None,
        "band_pos_criteria": tot_band_pos,
        "valid_cited_band_pos": tot_band_pos_valid,
        "avg_calls_per_lesson": round(
            statistics.mean([m.model_calls for m in metrics]), 2
        )
        if metrics
        else None,
        "avg_wall_seconds_per_lesson": round(
            statistics.mean([m.wall_seconds for m in metrics]), 2
        )
        if metrics
        else None,
    }


def _gold_mae(metrics: list[LessonMetric], gold: dict) -> dict:
    errs = []
    compared = []
    for m in metrics:
        g = gold.get(m.lesson_id)
        if not g or m.normalized is None or g.get("quality") is None:
            continue
        diff = abs(m.normalized - float(g["quality"]))
        errs.append(diff)
        compared.append({"lesson_id": m.lesson_id, "pred": m.normalized, "gold": g["quality"], "abs_err": round(diff, 3)})
    return {
        "lessons_compared": len(errs),
        "mean_abs_error": round(statistics.mean(errs), 3) if errs else None,
        "detail": compared,
    }


def main() -> int:
    cfg = load_config()

    lessons: list[LessonInput] = []
    try:
        dallas = enumerate_lessons(DALLAS)[:DALLAS_LIMIT]
        lessons.extend(dallas)
        print(f"enumerated {len(dallas)} dallas lesson(s) (partial ledger)")
    except Exception as e:  # noqa: BLE001 — never block on partial data
        print(f"WARN: enumerate_lessons failed ({e}); continuing with synthetic only")
    lessons.extend(_mini_lessons())
    print(f"eval set: {len(lessons)} lessons total\n")

    gold_path = os.path.join(
        _REPO_ROOT, "projects", DALLAS, "layer_lesson", "GOLD-LESSON.json"
    )
    gold = json.loads(open(gold_path).read()) if os.path.isfile(gold_path) else {}

    baseline_metrics: list[LessonMetric] = []
    candidate_metrics: list[LessonMetric] = []
    per_lesson_records: list[dict] = []
    example_cited = None  # a concrete valid cited-band example for the report

    for lesson in lessons:
        print(f"--- {lesson.title} ({lesson.lesson_id}) ---")
        bm, bres = _run_scorer(BASELINE_ID, lesson, cfg)
        print(
            f"  baseline   : citation_rate={bm.citation_rate} coverage={bm.coverage} "
            f"calls={bm.model_calls} {bm.wall_seconds}s"
        )
        cm, cres = _run_scorer(CANDIDATE_ID, lesson, cfg)
        print(
            f"  extractive : citation_rate={cm.citation_rate} coverage={cm.coverage} "
            f"calls={cm.model_calls} {cm.wall_seconds}s"
        )
        baseline_metrics.append(bm)
        candidate_metrics.append(cm)

        # Capture the first valid cited band from the extractive scorer for the report.
        if example_cited is None:
            for cr in cres.criteria:
                if (cr.band or 0) > 0 and _valid_citation(cr, lesson):
                    example_cited = {
                        "lesson_id": lesson.lesson_id,
                        "lesson_title": lesson.title,
                        "criterion_id": cr.criterion_id,
                        "label": cr.label,
                        "band": cr.band,
                        "evidence_element_id": cr.evidence[0].element_id,
                        "evidence_quote": cr.evidence[0].excerpt[:300],
                        "note": cr.note,
                    }
                    break

        per_lesson_records.append(
            {
                "lesson_id": lesson.lesson_id,
                "title": lesson.title,
                "baseline": bm.to_dict(),
                "extractive": cm.to_dict(),
                "baseline_result": bres.to_dict(),
                "extractive_result": cres.to_dict(),
            }
        )

    baseline_agg = _aggregate(baseline_metrics)
    candidate_agg = _aggregate(candidate_metrics)
    baseline_gold = _gold_mae(baseline_metrics, gold)
    candidate_gold = _gold_mae(candidate_metrics, gold)

    lift = None
    if (
        baseline_agg["citation_rate"] is not None
        and candidate_agg["citation_rate"] is not None
    ):
        lift = round(candidate_agg["citation_rate"] - baseline_agg["citation_rate"], 3)

    summary = {
        "approach": "extractive-2stage",
        "eval_lessons": len(lessons),
        "dallas_enumerated": len(lessons) - 3,
        "baseline": {**baseline_agg, "gold": baseline_gold},
        "extractive": {**candidate_agg, "gold": candidate_gold},
        "citation_rate_lift": lift,
        "example_cited_band": example_cited,
    }

    out = {
        "summary": summary,
        "per_lesson": per_lesson_records,
    }
    out_path = os.path.join(_HERE, "results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
