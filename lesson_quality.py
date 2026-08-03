#!/usr/bin/env python3
"""
lesson_quality.py — the lesson-quality stage of the pipeline.

Runs the decomposed, evidence-first quality scorer (`s4_quality_decomposed`, see
lesson_quality_scorer.py + docs/LESSON-QUALITY-RESEARCH.md) over every enumerated
lesson and writes the review plate the Loom Run Review UI reads:

  projects/<id>/output/LESSON-QUALITY-FEEDBACK.md   (human-readable)
  projects/<id>/output/LESSON-QUALITY-FEEDBACK.json (UI drill-down, grouped by unit)

WHY THIS IS A STAGE, NOT A MANUAL STEP
The UI plate must regenerate automatically on every run, so run_project.py calls this
right after the deterministic rungs. It is ADVISORY (model-based, never gates a verdict)
and NON-BLOCKING: if the model is offline or a lesson errors, the stage logs and moves on
rather than failing the whole audit. That mirrors the lesson/artifact-rung contract.

Usage:
  python3 lesson_quality.py --project <project_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lesson_quality_scorer  # noqa: F401 — registers s4_quality_decomposed
from audit_lib import load_config, log, project_dir
from lesson_bakeoff import enumerate_lessons
from lesson_scoring import build_scorer

SCORER_ID = "s4_quality_decomposed"
BAND_LABEL = {0: "Absent", 1: "Weak", 2: "Developing", 3: "Strong", None: "—"}


def _bar(band) -> str:
    """Render a band as filled/empty dots for the markdown plate."""
    n = band if isinstance(band, int) else 0
    return "●" * n + "○" * (3 - n)


def _doc_source_map(project: str) -> dict[str, str]:
    """doc_id -> sources/<file> so the UI can show the raw lesson text beneath the
    review. The ledger stores the basename; the review API serves sources/*.txt."""
    ledger = project_dir(project) / "layer0" / "ledger.json"
    out: dict[str, str] = {}
    if ledger.is_file():
        for row in json.loads(ledger.read_text()):
            did, sf = row.get("doc_id"), row.get("source_file")
            if did and sf and did not in out:
                out[did] = f"sources/{sf}"
    return out


def generate(project: str) -> Path:
    """Score every lesson and write the .md + .json plates. Returns the .md path."""
    cfg = load_config()
    scorer = build_scorer(SCORER_ID)
    lessons = enumerate_lessons(project)
    doc_source = _doc_source_map(project)
    log(f"lesson-quality: scoring {len(lessons)} lessons with {SCORER_ID}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Lesson Quality Feedback",
        "",
        "> Per-dimension instructional-coach diagnosis from the decomposed quality "
        "scorer (`s4_quality_decomposed`): one focused model pass per criterion, "
        "evidence-first, reranked candidates. **Advisory** — it surfaces strengths and "
        "gaps in each lesson's own text; it does not gate verdicts. "
        "Bands: ○○○ Absent · ●○○ Weak · ●●○ Developing · ●●● Strong.",
        "",
        f"_Generated {stamp} over {len(lessons)} enumerated lessons._",
        "",
    ]

    # Grouped by unit_id so the heatmap unit panel can list its own lessons; each
    # lesson carries the full per-dimension breakdown the LessonDetail view renders.
    units: dict[str, list[dict]] = {}
    total_cited = total_crit = 0

    for le in lessons:
        res = scorer.score(le, cfg)
        lines.append(f"## {le.title}")
        if res.error:
            lines.append(f"_scorer error: {res.error}_\n")
            continue
        summ = res.summary or {}
        lines.append(
            f"_mean band {summ.get('mean_band')}/{summ.get('max_band')} "
            f"· {len(le.elements)} elements_"
        )
        lines.append("")
        lines.append("| Dimension | Band | Diagnosis |")
        lines.append("|---|---|---|")
        dims: list[dict] = []
        for c in res.criteria:
            note_md = (c.note or "").strip().replace("\n", " ").replace("|", "\\|") or "—"
            lines.append(f"| {c.label} | {_bar(c.band)} {BAND_LABEL.get(c.band, '—')} | {note_md} |")
            if c.evidence:
                total_cited += 1
            total_crit += 1
            dims.append(
                {
                    "criterion_id": c.criterion_id,
                    "label": c.label,
                    "band": c.band,
                    "note": (c.note or "").strip(),
                    "evidence": [
                        {"element_id": ev.element_id, "excerpt": ev.excerpt[:300]}
                        for ev in (c.evidence or [])
                    ],
                }
            )
        cited = [c for c in res.criteria if c.evidence]
        if cited:
            lines.append("")
            lines.append("<details><summary>Evidence cited</summary>")
            lines.append("")
            for c in cited:
                q = c.evidence[0].excerpt[:200].replace("\n", " ")
                lines.append(f"- **{c.label}** — `{c.evidence[0].element_id}`: {q}")
            lines.append("")
            lines.append("</details>")
        lines.append("")

        units.setdefault(le.unit_id, []).append(
            {
                "lesson_id": le.lesson_id,
                "title": le.title,
                "unit_id": le.unit_id,
                "source_file": doc_source.get(le.lesson_id),
                "mean_band": summ.get("mean_band"),
                "max_band": summ.get("max_band"),
                "element_count": len(le.elements),
                "dimensions": dims,
            }
        )

    out_dir = project_dir(project) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "LESSON-QUALITY-FEEDBACK.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "LESSON-QUALITY-FEEDBACK.json").write_text(
        json.dumps(
            {"generated": stamp, "project": project, "scorer": SCORER_ID, "units": units},
            indent=2,
        ),
        encoding="utf-8",
    )
    pct = round(100 * total_cited / total_crit) if total_crit else 0
    log(f"lesson-quality: wrote {md_path} (citation {total_cited}/{total_crit} = {pct}%)")
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Lesson-quality feedback stage.")
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    generate(args.project)
    return 0


if __name__ == "__main__":
    sys.exit(main())
