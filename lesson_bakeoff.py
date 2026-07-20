#!/usr/bin/env python3
"""
lesson_bakeoff.py — the lesson-rung method bake-off.

Runs several REUSED lesson-scoring methods (see lesson_scorers.py) side by side
over already-decomposed lessons, writes one combined evidence-cited artifact per
lesson, and produces a cross-method comparison: where the methods agree, where
they diverge (a human-look queue), what each cost in model calls, and — when a
hand-scored gold set exists — how closely each method matches it.

The point is empirical: pick the lesson-review method that actually works on our
data, rather than assuming one. Deterministic methods (S1 completeness, S3
curriculum's-own) always run; model methods (S2 UbD, S4 quality) run only with
--with-model so the default pass is fast and offline-safe.

    python3 lesson_bakeoff.py --project dallas-career-2026
    python3 lesson_bakeoff.py --project dallas-career-2026 --with-model
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import lesson_scorers  # noqa: F401 — import registers the four scorers
from audit_lib import (
    atomic_write,
    classify_doc_type,
    doc_id_from_filename,
    load_config,
    load_yaml,
    log,
    project_dir,
)
from lesson_scoring import (
    LessonElement,
    LessonInput,
    ScorerResult,
    available_scorers,
    build_scorer,
)

# Deterministic-only default set; model methods are opt-in via --with-model.
DEFAULT_SCORERS = ["s1_completeness", "s3_curriculum_own"]
MODEL_SCORERS = ["s2_ubd", "s4_quality"]
# Doc types that are a "lesson atom" worth scoring (the teachable artifacts).
LESSON_DOC_TYPES = {"lesson_plan", "lesson_content"}
DIVERGENCE_TOLERANCE = 0.15  # |methodA - methodB| within this reads as agreement


def enumerate_lessons(project_id: str) -> list[LessonInput]:
    """Build one LessonInput per lesson-type document from the Layer 0 ledger,
    mapping each doc to its unit via the manifest. Deterministic + offline."""
    root = project_dir(project_id)
    manifest = load_yaml(root / "manifest.yaml")
    ledger_path = root / "layer0" / "ledger.json"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"no Layer 0 ledger at {ledger_path} — run layer0 first")
    ledger = json.loads(ledger_path.read_text())

    # doc_id -> unit_id (a doc listed under multiple units keeps its first unit).
    doc_unit: dict[str, str] = {}
    for uid, unit in (manifest.get("units") or {}).items():
        for rel in unit.get("documents") or unit.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)

    by_doc: dict[str, list[dict]] = defaultdict(list)
    for el in ledger:
        by_doc[el["doc_id"]].append(el)

    from synthesize import readable_title_from_filename

    lessons: list[LessonInput] = []
    for doc_id, els in by_doc.items():
        source_file = els[0].get("source_file", doc_id)
        if classify_doc_type(source_file) not in LESSON_DOC_TYPES:
            continue
        elements = [
            LessonElement(
                e["element_id"], e.get("element_type", ""), e.get("excerpt", "")
            )
            for e in els
        ]
        lessons.append(
            LessonInput(
                project_id=project_id,
                lesson_id=doc_id,
                unit_id=doc_unit.get(doc_id, "(unlinked)"),
                title=readable_title_from_filename(source_file),
                elements=elements,
            )
        )

    # Fan multi-lesson Teacher Editions into per-lesson children so a TE's lessons
    # enter the bake-off exactly like natively-discrete lessons (te_prepass is
    # deterministic and returns nothing when a corpus has no multi-lesson TEs, so
    # this is a no-op for Dallas and a real expansion for Bluebonnet math).
    from te_prepass import te_child_records

    for child in te_child_records(project_id):
        lessons.append(
            LessonInput(
                project_id=project_id,
                lesson_id=child["lesson_id"],
                unit_id=child["unit_id"],
                title=child["title"],
                elements=[
                    LessonElement(
                        e["element_id"], e.get("element_type", ""), e.get("excerpt", "")
                    )
                    for e in child["elements"]
                ],
            )
        )
    lessons.sort(key=lambda le: (le.unit_id, le.title))
    return lessons


def normalized_score(result: ScorerResult) -> float | None:
    """Collapse a method's per-lesson result to a single 0-1 signal so different
    method shapes (presence vs band) can be compared. None when the method errored
    (e.g. model offline) — never silently treated as a zero score."""
    if result.error:
        return None
    if result.scoring == "presence":
        return result.summary.get("coverage")
    if result.scoring == "band":
        mx = result.summary.get("max_band") or 3
        mean = result.summary.get("mean_band")
        return round(mean / mx, 3) if mean is not None and mx else None
    return None


def _divergence(scores: dict[str, float | None]) -> float | None:
    """Spread between methods for one lesson: max-min of available scores. High
    spread = the methods disagree about this lesson -> put it in the human queue."""
    vals = [v for v in scores.values() if v is not None]
    return round(max(vals) - min(vals), 3) if len(vals) >= 2 else None


def score_lesson(
    lesson: LessonInput, scorer_ids: list[str], cfg: dict | None
) -> dict:
    """Run every requested scorer over one lesson; return the combined artifact."""
    results: dict[str, ScorerResult] = {}
    for sid in scorer_ids:
        results[sid] = build_scorer(sid).score(lesson, cfg)
    normalized = {sid: normalized_score(r) for sid, r in results.items()}
    return {
        "lesson_id": lesson.lesson_id,
        "unit_id": lesson.unit_id,
        "title": lesson.title,
        "element_count": len(lesson.elements),
        "results": {sid: r.to_dict() for sid, r in results.items()},
        "normalized": normalized,
        "divergence": _divergence(normalized),
    }


def score_agreement(artifacts: list[dict], gold: dict, scorer_ids: list[str]) -> dict:
    """How closely each method matches the hand-scored gold set. gold maps
    lesson_id -> {"quality": <0-1>}. Reports mean absolute error (lower = better)
    and the count of lessons within tolerance, per method, over gold lessons only."""
    per_method: dict[str, dict] = {}
    for sid in scorer_ids:
        errs: list[float] = []
        within = 0
        for art in artifacts:
            g = gold.get(art["lesson_id"])
            s = art["normalized"].get(sid)
            if not g or s is None or g.get("quality") is None:
                continue
            diff = abs(s - float(g["quality"]))
            errs.append(diff)
            if diff <= DIVERGENCE_TOLERANCE:
                within += 1
        if errs:
            per_method[sid] = {
                "lessons_compared": len(errs),
                "mean_abs_error": round(sum(errs) / len(errs), 3),
                "within_tolerance": within,
            }
    return per_method


def _render_report(
    project_id: str,
    artifacts: list[dict],
    scorer_ids: list[str],
    total_cost: int,
    agreement: dict,
) -> str:
    lines = [
        "# Lesson-rung method bake-off",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Lessons scored:** {len(artifacts)}  ",
        f"**Methods:** {', '.join(scorer_ids)}  ",
        f"**Total model calls:** {total_cost}",
        "",
        "Each method reduces a lesson to a 0-1 signal (presence -> coverage; band -> "
        "mean band / max). This is a comparison of METHODS, not a grade of the lessons.",
        "",
        "## Per-lesson scores by method",
        "",
        "| Lesson | Unit | " + " | ".join(scorer_ids) + " | Divergence |",
        "|---|---|" + "|".join("---" for _ in scorer_ids) + "|---|",
    ]
    for art in sorted(
        artifacts, key=lambda a: (a["divergence"] is None, -(a["divergence"] or 0))
    ):
        cells = []
        for sid in scorer_ids:
            v = art["normalized"].get(sid)
            cells.append("—" if v is None else f"{v:.2f}")
        div = art["divergence"]
        lines.append(
            f"| {art['title']} | {art['unit_id']} | "
            + " | ".join(cells)
            + f" | {'—' if div is None else f'{div:.2f}'} |"
        )

    # Human-look queue: lessons where the methods disagree most.
    diverging = [a for a in artifacts if (a["divergence"] or 0) >= DIVERGENCE_TOLERANCE]
    lines += [
        "",
        "## Where the methods disagree (human-look queue)",
        "",
    ]
    if diverging:
        for a in sorted(diverging, key=lambda a: -(a["divergence"] or 0))[:10]:
            parts = []
            for sid in scorer_ids:
                v = a["normalized"].get(sid)
                parts.append(f"{sid}=" + ("—" if v is None else f"{v:.2f}"))
            pairs = ", ".join(parts)
            lines.append(
                f"- **{a['title']}** ({a['unit_id']}) — spread {a['divergence']:.2f}: {pairs}"
            )
    else:
        lines.append("- Methods broadly agree (no lesson exceeded the tolerance).")

    lines += ["", "## Agreement with hand-scored gold", ""]
    if agreement:
        lines += [
            "| Method | Lessons compared | Mean abs error | Within tolerance |",
            "|---|---|---|---|",
        ]
        for sid in scorer_ids:
            a = agreement.get(sid)
            if a:
                lines.append(
                    f"| {sid} | {a['lessons_compared']} | {a['mean_abs_error']} | "
                    f"{a['within_tolerance']} |"
                )
        lines += [
            "",
            "Lower mean-abs-error = closer to the human gold. This is the number that "
            "picks the winning method (see the lock-in step).",
        ]
    else:
        lines.append(
            "- No gold set yet (`layer_lesson/GOLD-LESSON.json`). Seed one to rank "
            "methods by agreement with human judgment."
        )
    return "\n".join(lines) + "\n"


def run_bakeoff(
    project_id: str,
    with_model: bool = False,
    scorer_ids: list[str] | None = None,
    limit: int | None = None,
) -> Path:
    """Score every lesson with each method, persist per-lesson artifacts + a
    comparison report, and return the output directory."""
    ids = scorer_ids or (
        DEFAULT_SCORERS + MODEL_SCORERS if with_model else DEFAULT_SCORERS
    )
    unknown = [s for s in ids if s not in available_scorers()]
    if unknown:
        raise ValueError(f"unknown scorer(s) {unknown} — known: {available_scorers()}")

    cfg = None
    if with_model:
        try:
            cfg = load_config()
        except Exception as e:  # noqa: BLE001
            log(f"WARN: model config unavailable, band scorers will degrade: {e}")

    lessons = enumerate_lessons(project_id)
    if limit:
        lessons = lessons[:limit]

    out_dir = project_dir(project_id) / "layer_lesson"
    lessons_dir = out_dir / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict] = []
    total_cost = 0
    for lesson in lessons:
        art = score_lesson(lesson, ids, cfg)
        for r in art["results"].values():
            total_cost += (r.get("cost") or {}).get("model_calls", 0)
        atomic_write(
            lessons_dir / f"{lesson.lesson_id}.json", json.dumps(art, indent=2)
        )
        artifacts.append(art)
        log(f"scored lesson {lesson.title} ({lesson.lesson_id})")

    gold_path = out_dir / "GOLD-LESSON.json"
    gold = json.loads(gold_path.read_text()) if gold_path.is_file() else {}
    agreement = score_agreement(artifacts, gold, ids) if gold else {}

    atomic_write(
        out_dir / "bakeoff.json",
        json.dumps(
            {
                "project_id": project_id,
                "scorers": ids,
                "total_model_calls": total_cost,
                "lessons": artifacts,
                "agreement": agreement,
            },
            indent=2,
        ),
    )
    atomic_write(
        out_dir / "BAKEOFF.md",
        _render_report(project_id, artifacts, ids, total_cost, agreement),
    )
    log(
        f"bake-off done: {len(artifacts)} lessons, {total_cost} model calls "
        f"→ {out_dir / 'BAKEOFF.md'}"
    )
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Lesson-rung method bake-off")
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--with-model",
        action="store_true",
        help="also run the model band scorers (S2 UbD, S4 quality)",
    )
    ap.add_argument(
        "--scorers", help="comma-separated scorer ids (default: deterministic set)"
    )
    ap.add_argument("--limit", type=int, help="score only the first N lessons")
    args = ap.parse_args()
    scorer_ids = (
        [s.strip() for s in args.scorers.split(",") if s.strip()]
        if args.scorers
        else None
    )
    try:
        run_bakeoff(args.project, args.with_model, scorer_ids, args.limit)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
