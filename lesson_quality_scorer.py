#!/usr/bin/env python3
"""
lesson_quality_scorer.py — research-backed redesign of the lesson-quality judge
(promoted from experiments/quality_race/decomposed/decomposed_scorer.py).

Motivation and citations live in docs/LESSON-QUALITY-RESEARCH.md. In short, the
baseline `s4_quality_feedback` scorer has four design flaws the LLM-as-judge /
automated-essay-scoring literature warns about:

  1. it scores all six criteria in ONE call            -> criterion conflation / halo,
                                                          "mental averaging" (Autorubric;
                                                          Nemorize "one criterion, one call")
  2. it lets the band come with NO grounding, any order-> loses the G-Eval "reason/cite
                                                          before you score" constraint
  3. it uses DEFICIT framing ("do not inflate")        -> ~1.2/6 harshness shift (GMU 2025)
  4. it dumps up to 40 elements truncated to 600 chars -> "lost in the middle" (Liu 2024):
                                                          the real objective gets buried

This scorer flips all four:

  * DECOMPOSE   — one focused model call per criterion (6 calls/lesson).
  * RERANK      — feed only that criterion's reads_from elements, best-first by
                  keyword/label relevance, top-K, at generous length (no 600-char cut).
  * EVIDENCE-FIRST — the model must copy a verbatim quote and reason BEFORE the band.
  * NEUTRAL     — describe the band scale plainly; no "don't inflate" deficit language.

Registers id: s4_quality_decomposed (same quality rubric, so it's directly A/B-able
against s4_quality_feedback on the same LessonInput).

NOTE: gold-set score calibration is intentionally NOT done here (deferred by decision);
this experiment isolates the *design* changes only.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

# This module now lives at the repo root (promoted out of experiments/), so its own
# directory is the import root for the shared scoring package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

# How many reranked candidate elements to show the model per criterion. Kept small
# on purpose: Liu et al. show reader performance saturates/degrades past ~20 chunks,
# and a handful of *relevant* elements keeps the key text out of the lossy "middle".
TOP_K = 6
# Generous per-element budget — big enough to hold a full objective block / activity,
# unlike the baseline's 600-char guillotine, but bounded so the prompt stays sane.
EXCERPT_CHARS = 1400

# Neutral, non-deficit reviewer stance (finding 3). We still keep Loom's read-only
# auditor rule (diagnose the lesson's own words; never rewrite it).
PREAMBLE = (
    "You are an instructional reviewer. You judge ONLY what the lesson's own text "
    "shows, using the band scale as written. You are read-only: you never rewrite the "
    "lesson or invent content. Assign the band that best fits the evidence — neither "
    "inflate nor deflate."
)

_WORD_RE = re.compile(r"[a-z]{3,}")
# Very common words that would otherwise dominate the keyword-overlap reranker.
_STOP = {
    "the", "and", "for", "with", "that", "this", "does", "are", "did", "not", "any",
    "its", "from", "into", "level", "lesson", "student", "students", "toward",
    "beyond", "present", "clear", "real", "purposeful", "genuinely", "meaningful",
    "evidence", "varied", "learners", "opening", "task", "demand", "demands",
}

# Structural anchor phrases per criterion. These give the reranker RECALL beyond the
# rubric's meta-vocabulary: an objective block rarely contains the word "clarity", but
# it does contain "objective" / "students will" / "SWBAT". Matching on structure lets us
# surface the right element even when Layer 0 mis-typed it (finding 5 + the A/B finding
# that objective bullets were typed `direct_instruction`).
_ANCHORS: dict[str, tuple[str, ...]] = {
    "objective_clarity": (
        "objective", "students will", "swbat", "i can", "learning target",
        "learning goal", "essential question", "by the end", "goal:",
    ),
    "engagement": (
        "getting started", "hook", "warm up", "warm-up", "engage", "opener",
        "launch", "do now", "bell ringer", "real-world", "real world",
    ),
    "checks_for_understanding": (
        "check for understanding", "formative", "exit ticket", "assess",
        "ask yourself", "show me", "student look-fors", "opportunity to assess",
    ),
    "differentiation_supports": (
        "ell", "elps", "language objective", "sentence stem", "accommodation",
        "modification", "iep", "504", "gifted", "extension", "scaffold",
        "just in time", "support",
    ),
    "cognitive_rigor": (
        "analyze", "justify", "explain why", "prove", "evaluate", "construct",
        "reasoning", "interpret", "why or why not",
    ),
    "coherent_sequence_closure": (
        "closure", "summarize", "summary", "wrap up", "wrap-up", "reflect",
        "consolidat", "share and summarize", "essential question",
    ),
}

_SPLIT_RE = re.compile(r"-split(\d+)$")


def _base_id(element_id: str) -> str:
    """The pre-split element id, so fragments Layer 0 chopped mid-block regroup."""
    return _SPLIT_RE.sub("", element_id)


def _split_no(element_id: str) -> int:
    m = _SPLIT_RE.search(element_id)
    return int(m.group(1)) if m else 0


def _keywords_for(criterion: dict) -> set[str]:
    """Relevance vocabulary for one criterion: its explicit `keywords` (if any) plus
    the content words of its label and description. Used only to RERANK candidates
    (bring the on-topic element to the front), never to score."""
    kws: set[str] = {k.lower() for k in (criterion.get("keywords") or [])}
    text = f"{criterion.get('label','')} {criterion.get('description','')}".lower()
    kws.update(w for w in _WORD_RE.findall(text) if w not in _STOP)
    return kws


def _rerank(lesson: LessonInput, criterion: dict) -> list:
    """Pick + order the candidate elements for ONE criterion.

    Three ideas, all learned from the first A/B:
      * RECALL by TYPE **or** STRUCTURE — an element qualifies if its type is in the
        criterion's `reads_from` OR its text hits the criterion's structural anchors.
        This rescues relevant text Layer 0 mis-typed (the objective bullets were typed
        `direct_instruction`, so a type-only pool never saw them).
      * RELEVANCE ranking — anchors weigh 3, rubric keywords weigh 1, being a
        reads_from type adds 1.
      * SIBLING REUNIFICATION — when a chosen element is a `-splitN` fragment, its
        siblings come along so a block Layer 0 chopped mid-way (OBJECTIVES header in
        split1, its bullets in split2) is judged whole and contiguous.
    Never starves: falls back to all elements if nothing qualifies."""
    wanted = list(criterion.get("reads_from") or [])
    type_rank = {t: i for i, t in enumerate(wanted)}
    kws = _keywords_for(criterion)
    anchors = _ANCHORS.get(criterion["id"], ())

    groups: dict[str, list] = defaultdict(list)
    for el in lesson.elements:
        groups[_base_id(el.element_id)].append(el)

    def relevance(el) -> int:
        text = (el.excerpt or "").lower()
        a = sum(1 for p in anchors if p in text)
        k = sum(1 for w in kws if w in text)
        typed = 1 if el.element_type in type_rank else 0
        return a * 3 + k + typed

    qualified = [
        (relevance(el), el)
        for el in lesson.elements
        if el.element_type in type_rank or relevance(el) > 0
    ]
    if not qualified:
        qualified = [(0, el) for el in lesson.elements]
    qualified.sort(
        key=lambda t: (
            -t[0],
            type_rank.get(t[1].element_type, 99),
            -len(t[1].excerpt or ""),
        )
    )

    chosen: list = []
    seen: set[str] = set()
    for _score, el in qualified:
        for sib in sorted(groups[_base_id(el.element_id)], key=lambda e: _split_no(e.element_id)):
            if sib.element_id not in seen:
                chosen.append(sib)
                seen.add(sib.element_id)
        if len(chosen) >= TOP_K:
            break
    # Allow a little overflow so a reunified sibling group is never cut in half.
    return chosen[: TOP_K + 3]


def _prompt(lesson: LessonInput, rubric: dict, criterion: dict, cands: list) -> str:
    scale = "\n".join(
        f"  {k}: {v}" for k, v in (rubric.get("band_scale") or {}).items()
    )
    # SHORT tags (E1, E2, ...) instead of 40-char element ids. The first A/B showed the
    # model would not echo our long ids, so citation never bound; a tiny tag it will
    # reliably reproduce, and we map it back to the real element id afterward.
    cand_block = "\n\n".join(
        f"[E{i}] ({el.element_type})\n\"\"\"\n{(el.excerpt or '')[:EXCERPT_CHARS]}\n\"\"\""
        for i, el in enumerate(cands, 1)
    ) or "(no candidate elements for this dimension)"
    return f"""{PREAMBLE}

DIMENSION TO JUDGE: {criterion.get('label', criterion['id'])}
WHAT IT MEANS: {criterion.get('description', '').strip()}

BAND SCALE:
{scale}

LESSON: {lesson.title}
EXCERPTS (most relevant first, tagged E1..E{len(cands)}):
{cand_block}

Do these steps IN ORDER:
1. evidence_tag: the tag (e.g. "E1") of the ONE excerpt that best speaks to this
   dimension. If truly nothing addresses it, use "".
2. evidence_quote: a short VERBATIM quote (<= 40 words) copied from that excerpt.
3. reasoning: in 1-2 specific sentences, say what that evidence shows about THIS
   dimension (name the concrete content; if weak/absent, say exactly what is lacking).
4. band: ONLY NOW choose the integer band whose description best matches your reasoning.

Respond with ONLY valid JSON (no markdown fences), in this key order:
{{"evidence_tag": "<E# or empty>",
  "evidence_quote": "<verbatim excerpt or empty>",
  "reasoning": "<1-2 sentences>",
  "band": <int 0-3>}}"""


class QualityDecomposedScorer(Scorer):
    scorer_id = "s4_quality_decomposed"
    name = "S4 quality (decomposed: per-criterion, evidence-first, reranked)"
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

        from layer1 import call_and_parse_with_retry

        crits: list[CriterionResult] = []
        calls = 0
        for c in rubric["criteria"]:
            cands = _rerank(lesson, c)
            # Map the short tags we show the model (E1..En) back to real element ids.
            tag_to_id = {f"e{i}": el.element_id for i, el in enumerate(cands, 1)}
            prompt = _prompt(lesson, rubric, c, cands)
            label = c.get("label", c["id"])
            try:
                data = call_and_parse_with_retry(
                    cfg, "analyst", prompt, f"qd-{lesson.lesson_id}-{c['id']}"
                )
                calls += 1
            except Exception as e:  # noqa: BLE001 — one bad criterion must not sink the lesson
                crits.append(
                    CriterionResult(c["id"], label, "band", note=f"model error: {e}")
                )
                continue

            band = data.get("band")
            band = int(band) if isinstance(band, (int, float)) else None
            reasoning = (data.get("reasoning") or "").strip()
            tag = (data.get("evidence_tag") or "").strip().lower().lstrip("[").rstrip("]")
            quote = (data.get("evidence_quote") or "").strip()
            evidence: list[Evidence] = []
            real_id = tag_to_id.get(tag)
            if real_id and quote:
                evidence = [Evidence(real_id, quote)]
            note = reasoning or f"No candidate element addresses {label.lower()}."
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
            cost={"model_calls": calls},
        )


register_scorer(QualityDecomposedScorer)
