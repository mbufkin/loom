#!/usr/bin/env python3
"""
run_eval.py — head-to-head eval for the "grounded-rate" quality scorer.

Compares the shipped baseline `s4_quality` (model picks AND cites evidence) against
`s4_quality_grounded` (code selects+cites evidence, model only rates + proxy floors)
on the SAME lessons, and reports the race metrics:

  * citation_rate   — fraction of non-zero bands that carry a valid citation.
  * on_point_rate   — fraction of criteria where the code-selected evidence is
                      genuinely relevant (grounded scorer only; honesty check).
  * gold_mae        — mean abs error vs a small gold set (holistic 0-1 quality).
  * calls_per_lesson / wall_time_per_lesson.

Data reality: the Dallas ledger is a PARTIAL rebuild, so enumerate_lessons() may
return only ~3 lessons whose doc_ids no longer match GOLD-LESSON.json. We do NOT
block on that. We evaluate over (a) whatever enumerate_lessons returns, plus (b)
3 hand-crafted mini lessons (STRONG / WEAK / explicit-ELPS). Gold for MAE = the
mini anchors we designed + any Dallas lesson we can confidently title-match to a
GOLD-LESSON.json entry (reported transparently).

    python3 run_eval.py            # full run (hits the local model)
    python3 run_eval.py --offline  # deterministic selection only, no model calls
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import lesson_scorers  # noqa: F401,E402 — registers baseline s1..s4
import grounded_scorer  # noqa: F401  — registers s4_quality_grounded / s2_ubd_grounded
from audit_lib import load_config  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402
from lesson_scoring import (  # noqa: E402
    LessonElement,
    LessonInput,
    ScorerResult,
    build_scorer,
)

HERE = Path(__file__).resolve().parent
PROJECT = "dallas-career-2026"

# --- hand-crafted mini lessons ---------------------------------------------
# Three tiny LessonInputs that exercise the scorer's edges. Element types match
# the rubric reads_from vocabulary so selection behaves exactly as in production.
# These double as gold ANCHORS (values we designed, labelled as such — not SME
# ground truth), so MAE is meaningful even while the Dallas ledger is partial.


def mini_lessons() -> list[tuple[LessonInput, float]]:
    strong = LessonInput(
        project_id="_mini",
        lesson_id="mini_strong",
        unit_id="mini",
        title="MINI: Strong photosynthesis lesson",
        elements=[
            LessonElement(
                "mini_strong-obj", "standards_objectives",
                "Objective: Students will analyze how light intensity affects the "
                "rate of photosynthesis and justify a claim with data (measurable).",
            ),
            LessonElement(
                "mini_strong-hook", "hook_engagement",
                "Do Now: A plant on a dim windowsill is dying. Turn and talk: why "
                "might light matter? Post your prediction on the board.",
            ),
            LessonElement(
                "mini_strong-di", "direct_instruction",
                "Mini-lecture: we define photosynthesis, then model how to design a "
                "controlled experiment and analyze the data to evaluate a hypothesis.",
            ),
            LessonElement(
                "mini_strong-gp", "guided_practice",
                "Guided practice: in pairs, students compare two data tables and "
                "explain which light level maximized oxygen output, citing evidence.",
            ),
            LessonElement(
                "mini_strong-assess", "assessment_checkpoint",
                "Exit ticket: given a new data set, students construct a claim and "
                "justify it — scored with a 3-point rubric to check understanding.",
            ),
            LessonElement(
                "mini_strong-close", "reflection_closure",
                "Closure: students revise their opening prediction and write one "
                "sentence on what changed their thinking.",
            ),
        ],
    )
    weak = LessonInput(
        project_id="_mini",
        lesson_id="mini_weak",
        unit_id="mini",
        title="MINI: Skeletal marketing lesson",
        elements=[
            LessonElement(
                "mini_weak-hdr", "standards_objectives",
                "Marketing careers. Day 1. Day 2. Day 3.",
            ),
            LessonElement(
                "mini_weak-x", "unclear",
                "See slides. TBD.",
            ),
        ],
    )
    elps = LessonInput(
        project_id="_mini",
        lesson_id="mini_elps",
        unit_id="mini",
        title="MINI: Lesson with explicit ELPS language support",
        elements=[
            LessonElement(
                "mini_elps-obj", "standards_objectives",
                "Objective: Students will identify the three branches of government.",
            ),
            LessonElement(
                "mini_elps-di", "direct_instruction",
                "Teacher presents each branch with a labeled diagram and examples.",
            ),
            LessonElement(
                "mini_elps-gp", "guided_practice",
                "Language objective / ELPS support: provide sentence stems ('The "
                "____ branch is responsible for ____') and a bilingual word bank as "
                "an accommodation for emergent bilingual (ELL) students; scaffold "
                "with a graphic organizer.",
            ),
        ],
    )
    return [(strong, 0.85), (weak, 0.15), (elps, 0.6)]


# --- gold: mini anchors + confident Dallas title matches --------------------


def build_gold(dallas: list[LessonInput], minis: list[tuple[LessonInput, float]]) -> dict:
    """gold: lesson_id -> {"quality": 0-1, "source": ...}. Mini anchors are the
    values we designed. Dallas entries are matched to GOLD-LESSON.json ONLY when a
    title match is unambiguous (reported so the reader can discount it)."""
    gold: dict[str, dict] = {}
    for le, q in minis:
        gold[le.lesson_id] = {"quality": q, "source": "designed mini anchor"}

    gold_path = REPO_ROOT / "projects" / PROJECT / "layer_lesson" / "GOLD-LESSON.json"
    shipped = json.loads(gold_path.read_text()) if gold_path.is_file() else {}
    # Only one current Dallas doc has an unambiguous counterpart in the shipped gold:
    # "Engineering Lesson Plan" (current) == "Engineering Lesson" (gold 4b97944cd264).
    # We match by normalized title prefix rather than the (now-diverged) doc_id.
    def norm(t: str) -> str:
        return "".join(ch for ch in (t or "").lower() if ch.isalnum())

    shipped_by_title = {
        norm(v.get("title", "")): v
        for k, v in shipped.items()
        if not k.startswith("_")
    }
    for le in dallas:
        nt = norm(le.title)
        # startswith either direction handles "engineering lesson" vs "...plan".
        match = None
        for gt, gv in shipped_by_title.items():
            if nt.startswith(gt) or gt.startswith(nt):
                match = gv
                break
        if match is not None:
            gold[le.lesson_id] = {
                "quality": match["quality"],
                "source": f"title-matched to shipped gold ('{match['title']}')",
            }
    return gold


# --- metric helpers ---------------------------------------------------------


def normalized(result: ScorerResult) -> float | None:
    if result.error:
        return None
    mx = result.summary.get("max_band") or 3
    mean = result.summary.get("mean_band")
    return round(mean / mx, 3) if mean is not None and mx else None


def citation_stats(result: ScorerResult) -> tuple[int, int]:
    """(cited_nonzero, total_nonzero) — a band>0 must carry >=1 evidence to count
    as cited. Denominator excludes honest band-0s (nothing to cite)."""
    nonzero = [c for c in result.criteria if c.band]
    cited = [c for c in nonzero if c.is_evidenced()]
    return len(cited), len(nonzero)


def run() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip model calls")
    args = ap.parse_args()

    cfg = None if args.offline else load_config()

    dallas = enumerate_lessons(PROJECT)
    minis = mini_lessons()
    gold = build_gold(dallas, minis)

    all_lessons = list(dallas) + [le for le, _q in minis]

    # baseline s4_quality vs our grounded scorer (blended) and a model-only variant.
    scorer_ids = ["s4_quality", "s4_quality_grounded"]

    per_lesson: list[dict] = []
    agg = {
        sid: {"cited": 0, "nonzero": 0, "calls": 0, "time": 0.0, "n": 0,
              "on_point_num": 0.0, "on_point_den": 0}
        for sid in scorer_ids
    }
    gold_err = {sid: [] for sid in scorer_ids}

    example = None  # a concrete cited-band example from the grounded scorer

    for lesson in all_lessons:
        row = {"lesson_id": lesson.lesson_id, "title": lesson.title,
               "elements": len(lesson.elements), "scores": {}}
        for sid in scorer_ids:
            t0 = time.time()
            res = build_scorer(sid).score(lesson, cfg)
            dt = time.time() - t0
            cited, nonzero = citation_stats(res)
            norm = normalized(res)
            agg[sid]["cited"] += cited
            agg[sid]["nonzero"] += nonzero
            agg[sid]["calls"] += (res.cost or {}).get("model_calls", 0)
            agg[sid]["time"] += dt
            agg[sid]["n"] += 1
            if "on_point_rate" in res.summary:
                agg[sid]["on_point_num"] += res.summary["on_point_rate"] * len(res.criteria)
                agg[sid]["on_point_den"] += len(res.criteria)
            g = gold.get(lesson.lesson_id)
            if g and norm is not None:
                gold_err[sid].append(abs(norm - float(g["quality"])))
            row["scores"][sid] = {
                "normalized": norm,
                "mean_band": res.summary.get("mean_band"),
                "cited": cited, "nonzero": nonzero,
                "on_point_rate": res.summary.get("on_point_rate"),
                "error": res.error,
                "seconds": round(dt, 1),
            }
            # capture first well-cited grounded example
            if sid == "s4_quality_grounded" and example is None and not res.error:
                for c in res.criteria:
                    if c.band and c.is_evidenced():
                        example = {
                            "lesson": lesson.title,
                            "criterion": c.label,
                            "band": c.band,
                            "element_id": c.evidence[0].element_id,
                            "quote": c.evidence[0].excerpt[:240],
                            "note": c.note,
                        }
                        break
        per_lesson.append(row)

    summary = {}
    for sid in scorer_ids:
        a = agg[sid]
        errs = gold_err[sid]
        summary[sid] = {
            "citation_rate": round(a["cited"] / a["nonzero"], 3) if a["nonzero"] else None,
            "on_point_rate": round(a["on_point_num"] / a["on_point_den"], 3)
            if a["on_point_den"] else None,
            "gold_mae": round(sum(errs) / len(errs), 3) if errs else None,
            "gold_lessons_compared": len(errs),
            "calls_per_lesson": round(a["calls"] / a["n"], 2) if a["n"] else 0,
            "wall_time_per_lesson_s": round(a["time"] / a["n"], 1) if a["n"] else 0,
        }

    out = {
        "project": PROJECT,
        "offline": args.offline,
        "dallas_lessons": [le.lesson_id for le in dallas],
        "mini_lessons": [le.lesson_id for le, _q in minis],
        "gold": gold,
        "per_lesson": per_lesson,
        "summary": summary,
        "example_cited_band": example,
    }
    (HERE / "eval_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    if example:
        print("\nExample cited band (grounded):")
        print(json.dumps(example, indent=2))
    return out


if __name__ == "__main__":
    run()
