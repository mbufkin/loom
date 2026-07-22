#!/usr/bin/env python3
"""
run_module.py — run the decomposed (per-criterion, evidence-first, reranked) quality
scorer over every lesson in ONE unit, and report per-lesson bands + citation coverage.

This is the "scale beyond one lesson" step from docs/LESSON-QUALITY-RESEARCH.md: prove
the redesign holds across a whole module, not just the single lesson we hand-checked.

Usage:
  python3 experiments/quality_race/decomposed/run_module.py [project_id] [unit_id]
Defaults: bluebonnet-math-2026  alg1-mod-2
Writes: experiments/quality_race/decomposed/<unit_id>-results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import decomposed_scorer  # noqa: F401,E402 — registers s4_quality_decomposed
from audit_lib import load_config, log  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402
from lesson_scoring import build_scorer  # noqa: E402

SCORER = "s4_quality_decomposed"
BAND_LABEL = {0: "Abs", 1: "Wk", 2: "Dev", 3: "Str", None: "—"}


def main() -> int:
    project = sys.argv[1] if len(sys.argv) > 1 else "bluebonnet-math-2026"
    unit = sys.argv[2] if len(sys.argv) > 2 else "alg1-mod-2"

    lessons = [le for le in enumerate_lessons(project) if le.unit_id == unit]
    if not lessons:
        print(f"no lessons for unit '{unit}' in {project}")
        return 1

    cfg = load_config()
    scorer = build_scorer(SCORER)
    log(f"scoring {len(lessons)} lessons in {unit} with {SCORER}")

    results = []
    # Discover the criterion order from the first result for a stable table header.
    crit_ids: list[str] = []
    for le in lessons:
        res = scorer.score(le, cfg)
        if not crit_ids and res.criteria:
            crit_ids = [c.criterion_id for c in res.criteria]
        dims = {
            c.criterion_id: {
                "band": c.band,
                "cited": bool(c.evidence),
                "note": (c.note or "").strip(),
                "evidence": [
                    {"element_id": e.element_id, "excerpt": e.excerpt[:300]}
                    for e in (c.evidence or [])
                ],
            }
            for c in res.criteria
        }
        bands = [c.band for c in res.criteria if isinstance(c.band, int)]
        cited = sum(1 for c in res.criteria if c.evidence)
        results.append(
            {
                "lesson_id": le.lesson_id,
                "title": le.title,
                "elements": len(le.elements),
                "mean_band": round(sum(bands) / len(bands), 2) if bands else None,
                "cited": cited,
                "n_criteria": len(res.criteria),
                "model_calls": (res.cost or {}).get("model_calls"),
                "dimensions": dims,
            }
        )
        log(f"  {le.lesson_id.split('__')[-1]:4} mean={results[-1]['mean_band']} cited={cited}/{len(res.criteria)}")

    # ---- console summary table -------------------------------------------------
    hdr = f"{'lesson':6} | " + " | ".join(cid[:3].title() for cid in crit_ids) + " | mean | cited"
    print("\n" + "=" * len(hdr))
    print(f"UNIT {unit} — decomposed quality ({project})")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        short = r["lesson_id"].split("__")[-1]
        cells = " | ".join(
            f"{BAND_LABEL.get(r['dimensions'][cid]['band'],'—'):>3}" for cid in crit_ids
        )
        print(f"{short:6} | {cells} | {str(r['mean_band']):>4} | {r['cited']}/{r['n_criteria']}")
    print("-" * len(hdr))
    means = [r["mean_band"] for r in results if r["mean_band"] is not None]
    total_cited = sum(r["cited"] for r in results)
    total_crit = sum(r["n_criteria"] for r in results)
    print(
        f"UNIT MEAN band = {round(sum(means)/len(means),2) if means else '—'} / 3   "
        f"citation = {total_cited}/{total_crit} "
        f"({round(100*total_cited/total_crit) if total_crit else 0}%)"
    )
    print("legend: Abs=0 Wk=1 Dev=2 Str=3  |  criteria: " + ", ".join(crit_ids))

    out = _HERE / f"{unit}-results.json"
    out.write_text(
        json.dumps(
            {"project": project, "unit": unit, "scorer": SCORER, "lessons": results},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
