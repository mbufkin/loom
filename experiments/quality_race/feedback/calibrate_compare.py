#!/usr/bin/env python3
"""
calibrate_compare.py — put two curricula's lesson-quality feedback side by side so we
can SEE how the grader behaves on a strong vs a weak curriculum, and decide how to
calibrate the bands.

Why this exists
---------------
Dallas (career/CTE) scored poorly and genuinely is thin. To know whether our grader is
*correctly harsh* or just *harsh*, we run it on a professionally-authored curriculum
(Bluebonnet math) that should score higher. If a strong curriculum still floors, the
rubric/prompt is mis-calibrated. If it clearly out-scores Dallas, the grader
discriminates and we can trust the bands.

The fragment confound
---------------------
`enumerate_lessons` over-segments Teacher Editions, so some "lessons" are 1-2 element
scraps that score ~0 no matter how good the curriculum is. We therefore report the band
distribution BOTH raw and filtered to "substantive" lessons (>= MIN_ELEMENTS elements),
so the comparison is apples-to-apples.

Run: python3 experiments/quality_race/feedback/calibrate_compare.py [projA] [projB]
Defaults: bluebonnet-math-2026 vs dallas-career-2026 (strong vs weak).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

MIN_ELEMENTS = 4  # a "substantive" lesson; below this it's a TE fragment, not a lesson


def _load(project: str) -> list[dict]:
    """Flatten LESSON-QUALITY-FEEDBACK.json (grouped by unit) into a lesson list."""
    p = _REPO_ROOT / "projects" / project / "output" / "LESSON-QUALITY-FEEDBACK.json"
    if not p.is_file():
        raise SystemExit(f"missing {p} — run gen_report.py {project} first")
    data = json.loads(p.read_text())
    units = data.get("units", data) if isinstance(data, dict) else data
    lessons: list[dict] = []
    if isinstance(units, dict):
        for arr in units.values():
            lessons.extend(arr)
    else:
        lessons = units
    return lessons


def _dist(bands: list[int]) -> str:
    """Compact 0..3 histogram like '0:12 1:8 2:5 3:2'."""
    counts = {b: 0 for b in range(4)}
    for b in bands:
        if b in counts:
            counts[b] += 1
    return "  ".join(f"{k}:{counts[k]}" for k in range(4))


def _summarize(project: str) -> dict:
    lessons = _load(project)
    substantive = [le for le in lessons if (le.get("element_count") or 0) >= MIN_ELEMENTS]

    def means(rows: list[dict]) -> list[float]:
        out = []
        for le in rows:
            mb = le.get("mean_band")
            if isinstance(mb, (int, float)):
                out.append(float(mb))
        return out

    # Per-dimension band aggregation (substantive only — the fair comparison).
    per_dim: dict[str, list[int]] = {}
    for le in substantive:
        for d in le.get("dimensions", []):
            b = d.get("band")
            if isinstance(b, int):
                per_dim.setdefault(d.get("label", d.get("criterion_id", "?")), []).append(b)

    all_means = means(lessons)
    sub_means = means(substantive)
    return {
        "project": project,
        "total": len(lessons),
        "substantive": len(substantive),
        "mean_all": round(statistics.mean(all_means), 2) if all_means else None,
        "mean_substantive": round(statistics.mean(sub_means), 2) if sub_means else None,
        "sub_mean_dist": _dist([round(m) for m in sub_means]),
        "per_dim": {k: round(statistics.mean(v), 2) for k, v in per_dim.items()},
        "per_dim_raw": per_dim,
    }


def main() -> int:
    a = sys.argv[1] if len(sys.argv) > 1 else "bluebonnet-math-2026"
    b = sys.argv[2] if len(sys.argv) > 2 else "dallas-career-2026"
    A, B = _summarize(a), _summarize(b)

    print(f"\nCALIBRATION COMPARE  (substantive = >= {MIN_ELEMENTS} elements)\n")
    print(f"{'metric':<34}{A['project']:>22}{B['project']:>22}")
    print("-" * 78)
    for key, label in [
        ("total", "lessons enumerated"),
        ("substantive", "substantive lessons"),
        ("mean_all", "mean band (all, /3)"),
        ("mean_substantive", "mean band (substantive, /3)"),
    ]:
        print(f"{label:<34}{str(A[key]):>22}{str(B[key]):>22}")
    print(f"\n{'rounded mean-band histogram (substantive)':<40}")
    print(f"  {A['project']:<28} {A['sub_mean_dist']}")
    print(f"  {B['project']:<28} {B['sub_mean_dist']}")

    dims = list(dict.fromkeys(list(A["per_dim"]) + list(B["per_dim"])))
    print(f"\n{'per-dimension mean band (substantive)':<40}")
    print(f"{'dimension':<34}{a[:20]:>22}{b[:20]:>22}")
    print("-" * 78)
    for d in dims:
        print(f"{d[:33]:<34}{str(A['per_dim'].get(d,'—')):>22}{str(B['per_dim'].get(d,'—')):>22}")

    # A blunt calibration verdict.
    ma, mb = A["mean_substantive"], B["mean_substantive"]
    print()
    if ma is not None and mb is not None:
        gap = round(ma - mb, 2)
        if gap >= 0.4:
            print(f"SIGNAL: strong curriculum out-scores weak by {gap} band — grader discriminates.")
        elif gap <= 0:
            print(f"WARNING: strong curriculum did NOT out-score weak (gap {gap}) — grader likely mis-calibrated / too harsh.")
        else:
            print(f"WEAK SIGNAL: only {gap} band separation — rubric may be too harsh at the top.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
