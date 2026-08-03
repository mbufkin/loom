#!/usr/bin/env python3
"""
lesson_scorers.py — the four reused lesson-scoring methods for the bake-off.

  S1 completeness (deterministic presence gate) — rubric completeness_core8.
  S2 UbD alignment (model, banded)             — rubric ubd_alignment.
  S3 curriculum's-own rubric (deterministic)   — per-project rubric, else S1's.
  S4 LLM-as-judge quality (model, banded)      — rubric quality_dimensions.

Presence scorers are pure code (Bet 0: never spend a model call on a fact). Band
scorers make exactly ONE model call per lesson (all criteria at once) and REQUIRE
the model to cite a verbatim excerpt from the lesson's own elements for each band;
an uncited band is downgraded to needs-review rather than trusted. Every scorer
degrades gracefully: if the model endpoint is unavailable, band scorers return an
errored result (bands = None) instead of crashing the harness.
"""

from __future__ import annotations

import json

from audit_lib import parse_model_json
from lesson_scoring import (
    CriterionResult,
    Evidence,
    LessonInput,
    Scorer,
    ScorerResult,
    presence_result,
    register_scorer,
    summarize_bands,
)
from rubrics import (
    COMPLETENESS_RUBRIC,
    QUALITY_RUBRIC,
    UBD_RUBRIC,
    load_curriculum_own,
    load_rubric,
)

AUDITOR_PREAMBLE = (
    "You are a curriculum audit scorer. READ-ONLY. You judge only what the lesson's "
    "own text shows; you NEVER write, rewrite, or suggest lesson content. For every "
    "band you assign you MUST quote a verbatim excerpt from the CANDIDATE elements "
    "below and give its id. If nothing in the candidates supports a criterion, assign "
    "band 0 with an empty quote — an honest 0 is correct, do not inflate."
)


# --- deterministic presence scoring (S1, S3) --------------------------------
# The presence logic now lives in lesson_scoring.presence_result so the artifact
# scorers reuse the exact same deterministic gate; this thin wrapper keeps the
# lesson scorers reading naturally.


def _presence_result(
    lesson: LessonInput, rubric: dict, scorer_id: str
) -> ScorerResult:
    return presence_result(lesson, rubric, scorer_id)


# --- model band scoring (S2, S4) --------------------------------------------


def _band_candidates(lesson: LessonInput, rubric: dict) -> list:
    """Elements a band rubric may cite: the union of every criterion's reads_from
    types (fallback to all elements). Capped so the prompt stays bounded."""
    wanted: set[str] = set()
    for c in rubric["criteria"]:
        wanted.update(c.get("reads_from") or [])
    els = lesson.elements_of_type(*wanted) if wanted else list(lesson.elements)
    if not els:
        els = list(lesson.elements)
    return els[:40]


def _build_band_prompt(lesson: LessonInput, rubric: dict, candidates: list) -> str:
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
    return f"""{AUDITOR_PREAMBLE}

RUBRIC: {rubric.get('title', rubric['rubric_id'])}
BAND SCALE:
{scale}

CRITERIA to score (one band each):
{crit_block}

LESSON: {lesson.title}
CANDIDATE ELEMENTS (cite by id):
{cand_block}

Respond with ONLY valid JSON (no markdown fences):
{{
  "scores": [
    {{"criterion_id": "<one of: {ids}>", "band": <int>,
      "evidence_element_id": "<id from candidates, or empty>",
      "evidence_quote": "<verbatim excerpt from that element, or empty>",
      "note": "<one short sentence>"}}
  ]
}}
One entry per criterion above."""


def _band_result(
    lesson: LessonInput, rubric: dict, scorer_id: str, cfg: dict | None
) -> ScorerResult:
    max_band = max((rubric.get("band_scale") or {0: ""}).keys())
    empty = ScorerResult(
        scorer_id=scorer_id,
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["version"],
        scoring="band",
        lesson_id=lesson.lesson_id,
    )
    if cfg is None:
        empty.error = "no model config (offline) — band scorer skipped"
        empty.criteria = [
            CriterionResult(c["id"], c.get("label", c["id"]), "band", note="skipped")
            for c in rubric["criteria"]
        ]
        return empty

    candidates = _band_candidates(lesson, rubric)
    valid_ids = {el.element_id: el for el in candidates}
    prompt = _build_band_prompt(lesson, rubric, candidates)
    try:
        from layer1 import call_and_parse_with_retry

        data = call_and_parse_with_retry(
            cfg, "analyst", prompt, f"lesson-score-{scorer_id}-{lesson.lesson_id}"
        )
    except Exception as e:  # noqa: BLE001 — any model/parse failure degrades cleanly
        empty.error = f"model call failed: {e}"
        empty.criteria = [
            CriterionResult(c["id"], c.get("label", c["id"]), "band", note="error")
            for c in rubric["criteria"]
        ]
        empty.cost = {"model_calls": 1}
        return empty

    scored = {s.get("criterion_id"): s for s in (data.get("scores") or [])}
    crits: list[CriterionResult] = []
    for c in rubric["criteria"]:
        s = scored.get(c["id"]) or {}
        band = s.get("band")
        band = int(band) if isinstance(band, (int, float)) else None
        eid = (s.get("evidence_element_id") or "").strip()
        quote = (s.get("evidence_quote") or "").strip()
        evidence: list[Evidence] = []
        note = (s.get("note") or "").strip()
        # Evidence is only trusted if it cites a real candidate id. An uncited
        # non-zero band is downgraded to needs-review (never invent authority).
        if eid in valid_ids and quote:
            evidence = [Evidence(eid, quote)]
        elif band:
            note = (note + " ").strip() + "[unevidenced band — needs review]"
        crits.append(
            CriterionResult(
                c["id"],
                c.get("label", c["id"]),
                "band",
                band=band,
                evidence=evidence,
                note=note,
            )
        )
    return ScorerResult(
        scorer_id=scorer_id,
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["version"],
        scoring="band",
        lesson_id=lesson.lesson_id,
        criteria=crits,
        summary=summarize_bands(crits, max_band=max_band),
        cost={"model_calls": 1},
    )


# --- the four scorers -------------------------------------------------------


class CompletenessScorer(Scorer):
    scorer_id = "s1_completeness"
    name = "S1 completeness gate (Hunter / core-8, deterministic)"

    def __init__(self) -> None:
        self.rubric = load_rubric(COMPLETENESS_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return _presence_result(lesson, self.rubric, self.scorer_id)


class CurriculumOwnScorer(Scorer):
    scorer_id = "s3_curriculum_own"
    name = "S3 curriculum's own template (deterministic, per-project)"

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        # The project's own rubric if it has one; otherwise fall back to the shared
        # completeness bar so a new corpus is scored, not skipped.
        rubric = load_curriculum_own(lesson.project_id) or load_rubric(
            COMPLETENESS_RUBRIC
        )
        return _presence_result(lesson, rubric, self.scorer_id)


class UbdScorer(Scorer):
    scorer_id = "s2_ubd"
    name = "S2 UbD backward-design alignment (model, banded)"

    def __init__(self) -> None:
        self.rubric = load_rubric(UBD_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return _band_result(lesson, self.rubric, self.scorer_id, cfg)


class QualityScorer(Scorer):
    scorer_id = "s4_quality"
    name = "S4 LLM-as-judge quality (EQuIP/Danielson/5E, banded)"

    def __init__(self) -> None:
        self.rubric = load_rubric(QUALITY_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return _band_result(lesson, self.rubric, self.scorer_id, cfg)


register_scorer(CompletenessScorer)
register_scorer(UbdScorer)
register_scorer(CurriculumOwnScorer)
register_scorer(QualityScorer)
