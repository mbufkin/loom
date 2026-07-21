#!/usr/bin/env python3
"""
feedback_scorer.py — optimise the thing that's actually useful: the per-dimension
DIAGNOSTIC NOTE, not the numeric band's agreement with a tiny gold set.

Findings that motivated this (see ../force-cite/calibrate_gold_results.json and
the raw dumps): the baseline model already emits a reasonable band AND a coach-
style note per dimension ("Objective states two clear student-facing goals",
"Closure consists only of a link to external resources, lacking consolidation").
Its only real defects are:
  1. thin/EMPTY notes on some dimensions — the prompt asks for "one short
     sentence" and never requires a rationale for a band-0, so weak dimensions
     come back blank; and
  2. every note is stamped "[unevidenced band — needs review]" because the model
     skips the verbatim quote.

This scorer treats citation as SECONDARY and makes the NOTE the product:
  * every dimension gets a substantive, specific diagnostic note — including
    band 0, where the model must name exactly what is absent;
  * it keeps Loom's read-only AUDITOR stance (diagnose what the lesson shows or
    lacks; never rewrite or prescribe new lesson content);
  * a verbatim quote is captured when offered but a missing quote no longer
    poisons the note with a needs-review stamp;
  * a deterministic fallback guarantees no dimension is ever left noteless.

Registers id: s4_quality_feedback (quality rubric).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from lesson_scorers import _band_candidates  # noqa: E402
from lesson_scoring import (  # noqa: E402
    CriterionResult,
    Evidence,
    LessonInput,
    Scorer,
    ScorerResult,
    register_scorer,
    summarize_bands,
)
from rubrics import QUALITY_RUBRIC, load_rubric  # noqa: E402

# Auditor stance, but tuned for rich DIAGNOSIS rather than terse justification.
FEEDBACK_PREAMBLE = (
    "You are an instructional-coach auditor. READ-ONLY: you judge only what the "
    "lesson's own text shows or fails to show. You NEVER rewrite the lesson or "
    "prescribe new content. Your job is a specific, honest diagnosis a teacher "
    "could act on."
)


def _build_feedback_prompt(lesson: LessonInput, rubric: dict, candidates: list) -> str:
    scale = "\n".join(
        f"  {k}: {v}" for k, v in (rubric.get("band_scale") or {}).items()
    )
    crit_block = "\n".join(
        f"- {c['id']}: {c.get('label', c['id'])} — {c.get('description', '').strip()}"
        for c in rubric["criteria"]
    )
    cand_block = "\n\n".join(
        f"[{el.element_id}] ({el.element_type})\n\"\"\"\n{(el.excerpt or '')[:600]}\n\"\"\""
        for el in candidates
    ) or "(no candidate elements for this lesson)"
    ids = ", ".join(c["id"] for c in rubric["criteria"])
    return f"""{FEEDBACK_PREAMBLE}

RUBRIC: {rubric.get('title', rubric['rubric_id'])}
BAND SCALE:
{scale}

CRITERIA to diagnose (one per criterion):
{crit_block}

LESSON: {lesson.title}
CANDIDATE ELEMENTS:
{cand_block}

For EACH criterion produce:
  - band: integer per the scale above (an honest 0 is correct; do not inflate).
  - note: 1-2 SPECIFIC sentences. Name the concrete lesson content you observed
    (paraphrase or short quote) that justifies the band. If the band is 0 or 1,
    state EXACTLY what is missing or weak (e.g. "no exit ticket or other check
    for understanding appears"). Never leave the note empty; never use generic
    filler like "could be improved" without saying how it falls short.
  - evidence_element_id / evidence_quote: OPTIONAL. If a candidate element
    supports your note, give its id and a verbatim excerpt; otherwise leave both
    empty. A missing quote is fine — the note is what matters.

Respond with ONLY valid JSON (no markdown fences):
{{
  "scores": [
    {{"criterion_id": "<one of: {ids}>", "band": <int>,
      "evidence_element_id": "<id or empty>",
      "evidence_quote": "<verbatim excerpt or empty>",
      "note": "<1-2 specific sentences>"}}
  ]
}}
One entry per criterion above."""


def _fallback_note(label: str, band, has_note: bool) -> str:
    """Guarantee coverage: if the model returned nothing usable, synthesise an
    honest, non-generic placeholder from the band so no dimension is noteless."""
    if has_note:
        return ""
    if band in (0, None):
        return f"No candidate element in the lesson addresses {label.lower()}."
    return f"{label} is present but the model returned no rationale (band {band})."


class QualityFeedbackScorer(Scorer):
    scorer_id = "s4_quality_feedback"
    name = "S4 quality (feedback-first: rich diagnostic note, citation secondary)"
    rubric_id = QUALITY_RUBRIC

    def __init__(self) -> None:
        self.rubric = load_rubric(QUALITY_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        rubric = self.rubric
        max_band = max((rubric.get("band_scale") or {0: ""}).keys())
        base = ScorerResult(
            scorer_id=self.scorer_id,
            rubric_id=rubric["rubric_id"],
            rubric_version=rubric["version"],
            scoring="band",
            lesson_id=lesson.lesson_id,
        )
        if cfg is None:
            base.error = "no model config (offline)"
            base.criteria = [
                CriterionResult(c["id"], c.get("label", c["id"]), "band", note="skipped")
                for c in rubric["criteria"]
            ]
            return base

        candidates = _band_candidates(lesson, rubric)
        valid_ids = {el.element_id for el in candidates}
        prompt = _build_feedback_prompt(lesson, rubric, candidates)
        try:
            from layer1 import call_and_parse_with_retry

            data = call_and_parse_with_retry(
                cfg, "analyst", prompt, f"lesson-feedback-{lesson.lesson_id}"
            )
        except Exception as e:  # noqa: BLE001
            base.error = f"model call failed: {e}"
            base.criteria = [
                CriterionResult(c["id"], c.get("label", c["id"]), "band", note="error")
                for c in rubric["criteria"]
            ]
            base.cost = {"model_calls": 1}
            return base

        scored = {s.get("criterion_id"): s for s in (data.get("scores") or [])}
        crits: list[CriterionResult] = []
        for c in rubric["criteria"]:
            s = scored.get(c["id"]) or {}
            band = s.get("band")
            band = int(band) if isinstance(band, (int, float)) else None
            note = (s.get("note") or "").strip()
            eid = (s.get("evidence_element_id") or "").strip()
            quote = (s.get("evidence_quote") or "").strip()
            evidence: list[Evidence] = []
            # Citation is SECONDARY: attach it when valid, but never downgrade the
            # note when it is absent.
            if eid in valid_ids and quote:
                evidence = [Evidence(eid, quote)]
            label = c.get("label", c["id"])
            if not note:
                note = _fallback_note(label, band, has_note=False)
            crits.append(
                CriterionResult(c["id"], label, "band", band=band, evidence=evidence, note=note)
            )
        return ScorerResult(
            scorer_id=self.scorer_id,
            rubric_id=rubric["rubric_id"],
            rubric_version=rubric["version"],
            scoring="band",
            lesson_id=lesson.lesson_id,
            criteria=crits,
            summary=summarize_bands(crits, max_band=max_band),
            cost={"model_calls": 1},
        )


register_scorer(QualityFeedbackScorer)
