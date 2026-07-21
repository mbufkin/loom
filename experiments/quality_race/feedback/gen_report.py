#!/usr/bin/env python3
"""
gen_report.py — render the feedback-first quality scorer's per-lesson output as a
human-readable markdown plate the Loom Run Review site can display.

Writes projects/<project>/output/LESSON-QUALITY-FEEDBACK.md. This is ADDITIVE: it
does not touch the existing LESSON-RUNG / UNIT-RUNG plates (which came from an
older full-corpus run), it just adds a new quality-feedback view over whatever
lessons the current ledger enumerates.

Run: python3 experiments/quality_race/feedback/gen_report.py [project_id]
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

import feedback_scorer  # noqa: F401 — registers s4_quality_feedback
from audit_lib import load_config, log, project_dir
from lesson_bakeoff import enumerate_lessons
from lesson_scoring import build_scorer

BAND_LABEL = {0: "Absent", 1: "Weak", 2: "Developing", 3: "Strong", None: "—"}


def _bar(band) -> str:
    n = band if isinstance(band, int) else 0
    return "●" * n + "○" * (3 - n)


def main() -> int:
    project = sys.argv[1] if len(sys.argv) > 1 else "dallas-career-2026"
    cfg = load_config()
    scorer = build_scorer("s4_quality_feedback")
    lessons = enumerate_lessons(project)
    log(f"scoring {len(lessons)} lessons for {project}")

    lines: list[str] = []
    lines.append("# Lesson Quality Feedback")
    lines.append("")
    lines.append(
        "> Per-dimension instructional-coach diagnosis from the feedback-first "
        "quality scorer (`s4_quality_feedback`). **Advisory** — it surfaces "
        "strengths and gaps in each lesson's own text; it does not gate verdicts. "
        "Bands: ●○○ Weak · ●●○ Developing · ●●● Strong · ○○○ Absent."
    )
    lines.append("")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"_Generated {stamp} over {len(lessons)} enumerated lessons._")
    lines.append("")

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
        for c in res.criteria:
            note = (c.note or "").replace("\n", " ").replace("|", "\\|").strip() or "—"
            band_txt = f"{_bar(c.band)} {BAND_LABEL.get(c.band, '—')}"
            lines.append(f"| {c.label} | {band_txt} | {note} |")
        # Optional secondary evidence, when the model offered a valid quote.
        cited = [c for c in res.criteria if c.evidence]
        if cited:
            lines.append("")
            lines.append("<details><summary>Evidence cited</summary>")
            lines.append("")
            for c in cited:
                ev = c.evidence[0]
                q = ev.excerpt[:200].replace("\n", " ")
                lines.append(f"- **{c.label}** — `{ev.element_id}`: {q}")
            lines.append("")
            lines.append("</details>")
        lines.append("")

    out_dir = project_dir(project) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "LESSON-QUALITY-FEEDBACK.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {out_path}")
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
