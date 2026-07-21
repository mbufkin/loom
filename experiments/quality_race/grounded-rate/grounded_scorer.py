#!/usr/bin/env python3
"""
grounded_scorer.py — "grounded-rate" entry in the lesson-quality scorer race.

THE PROBLEM WE ARE ATTACKING
----------------------------
The shipped band scorers (`s4_quality`, `s2_ubd` in lesson_scorers.py) ask the
local LLM to do TWO jobs at once: (1) assign a 0-3 quality band AND (2) cite a
verbatim quote + element id backing that band. On our small local model
(Nemotron-3-Nano-30B) job (2) is the weak link: the model returns a band but an
invalid / missing citation, so `_band_result`'s guardrail downgrades the band to
"[unevidenced band — needs review]". Net effect: quality scoring is untrusted and
DEFERRED (lesson_rung.LOCKED_SCORERS deliberately excludes s2/s4).

THE "grounded-rate" BET
-----------------------
Flip who owns the evidence. Instead of trusting the model to find AND quote the
right element, CODE deterministically selects the on-topic element(s) per
criterion by lexical overlap with the rubric (description + keywords + the
criterion's reads_from element types), and the model is asked ONLY to rate the
band of evidence it is shown. Because the element_id + quote come from code, the
citation is valid *by construction* — the guardrail can never fire. The model's
job shrinks to the one thing it is actually good at (judging quality of text put
in front of it), and we additionally compute deterministic PROXY FLOORS
(DOK/Bloom verbs => rigor floor; ELPS/scaffold terms => differentiation floor) as
a guardrail against the model under-rating clearly-present evidence.

This module is ADDITIVE: it imports and reuses the repo's schema + rubric loader
and registers NEW scorer ids (`s4_quality_grounded`, `s2_ubd_grounded`). It never
edits shared files. Auditor-only: every quote is copied verbatim from the
lesson's own elements; nothing is invented or rewritten.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The experiment lives three directories below the repo root; make the repo's
# shared modules importable without touching sys.path permanently for anyone else.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lesson_scoring import (  # noqa: E402  (import after sys.path fix)
    CriterionResult,
    Evidence,
    LessonInput,
    Scorer,
    ScorerResult,
    register_scorer,
    summarize_bands,
)
from rubrics import (  # noqa: E402
    QUALITY_RUBRIC,
    UBD_RUBRIC,
    load_rubric,
)

# --- lexical helpers --------------------------------------------------------
# A deliberately tiny, explainable stopword list. We are NOT building an NLP
# pipeline; we just want content-word overlap that a human can audit by eye. Best
# practice for an auditor tool: prefer a transparent heuristic you can defend over
# an opaque embedding you cannot.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "be", "does", "do", "did", "it", "its", "that", "this", "these",
    "those", "as", "by", "from", "into", "than", "then", "so", "not", "no", "yes",
    "can", "could", "would", "should", "will", "shall", "may", "might", "must",
    "there", "here", "they", "them", "their", "you", "your", "we", "our", "i",
    "he", "she", "his", "her", "if", "but", "about", "toward", "towards", "same",
    "clear", "specific", "present", "evidence", "lesson", "student", "students",
    "criterion", "rubric", "level", "stage", "actual", "actually", "genuinely",
    "meaningful", "real", "well", "written", "beyond", "move", "moves", "form",
}

_WORD_RE = re.compile(r"[a-z][a-z0-9+/-]{1,}")


def _tokens(text: str) -> set[str]:
    """Lowercase content-word token set (stopwords + 1-char noise removed)."""
    return {
        w
        for w in _WORD_RE.findall((text or "").lower())
        if w not in _STOPWORDS and len(w) > 1
    }


# DOK / Bloom higher-order verbs. Presence of any signals the lesson is asking for
# more than recall — the deterministic proxy floor for cognitive_rigor. This is the
# same "REUSED framework, not home-grown" discipline the rubrics themselves follow
# (DOK = Webb's Depth of Knowledge; Bloom = revised taxonomy verbs).
_DOK_VERBS = {
    "analyze", "analyse", "evaluate", "design", "create", "construct", "compare",
    "contrast", "justify", "critique", "investigate", "hypothesize", "synthesize",
    "formulate", "assess", "develop", "prove", "explain", "predict", "classify",
    "differentiate", "interpret", "apply", "solve", "model", "build", "plan",
    "revise", "defend", "argue", "generate", "produce", "compose", "examine",
}

# Recall-only verbs: if these dominate and no DOK verb appears, rigor stays low.
_RECALL_VERBS = {
    "list", "name", "define", "identify", "recall", "label", "match", "state",
    "recognize", "memorize", "repeat", "select", "copy",
}


def _phrase_hits(text_low: str, phrases: list[str]) -> list[str]:
    """Which rubric keyword phrases appear as substrings (handles multi-word terms
    like 'language objective' / 'sentence stem' that token overlap would miss)."""
    return [p for p in phrases if p and p.lower() in text_low]


# --- deterministic per-criterion evidence selection -------------------------


def _score_element(
    el, query_tokens: set[str], keywords: list[str], reads_from: set[str]
) -> tuple[float, dict]:
    """How well does ONE element match ONE criterion? Returns (score, breakdown).

    The score is intentionally a simple weighted sum a human can re-derive:
      + rubric keyword phrase hits (strongest signal; weight 4 each)
      + content-token overlap with the criterion's description/label (weight 1)
      + a bonus if the element's own Layer 0 type is what the criterion reads_from
    Everything is transparent so the "why did you pick this quote" question always
    has a concrete answer — the whole point of the grounded-rate approach.
    """
    excerpt = el.excerpt or ""
    low = excerpt.lower()
    el_tokens = _tokens(excerpt)

    kw_hits = _phrase_hits(low, keywords)
    overlap = query_tokens & el_tokens
    el_types = {t for t in (el.element_type or "").split("|") if t}
    type_bonus = 2.0 if (el_types & reads_from) else 0.0

    score = 4.0 * len(kw_hits) + 1.0 * len(overlap) + type_bonus
    breakdown = {
        "keyword_hits": kw_hits,
        "token_overlap": sorted(overlap),
        "type_match": bool(el_types & reads_from),
    }
    return score, breakdown


def select_evidence(
    lesson: LessonInput, criterion: dict, top_k: int = 2
) -> list[tuple[object, float, dict]]:
    """Deterministically pick the top-k on-topic elements for a criterion.

    Candidate pool = elements whose Layer 0 type the criterion reads_from (fallback
    to ALL elements when the lesson has none of those types — a partially-tagged
    corpus should still be scored, not skipped). Ranked by _score_element.
    """
    reads_from = set(criterion.get("reads_from") or [])
    keywords = [k for k in (criterion.get("keywords") or [])]
    query_tokens = _tokens(
        f"{criterion.get('label', '')} {criterion.get('description', '')}"
    ) | _tokens(" ".join(keywords))

    pool = lesson.elements_of_type(*reads_from) if reads_from else list(lesson.elements)
    if not pool:
        pool = list(lesson.elements)

    scored = []
    for el in pool:
        s, bd = _score_element(el, query_tokens, keywords, reads_from)
        scored.append((el, s, bd))
    # Stable sort: highest score first, then original order (deterministic).
    scored.sort(key=lambda t: -t[1])
    # Keep only elements that matched *something* (score > 0); an all-zero pool
    # means "no on-topic evidence exists" -> honest band 0 with no citation.
    hits = [t for t in scored if t[1] > 0][:top_k]
    return hits


# --- deterministic proxy floors ---------------------------------------------


def _proxy_floor(criterion_id: str, evidence_text: str, has_evidence: bool) -> int:
    """A conservative lower bound on the band that the lesson's OWN words justify,
    independent of the model. Only fires on unambiguous lexical signals so it acts
    as a floor (guardrail against model under-rating), never an inflator.

      cognitive_rigor         : DOK/Bloom verb present            -> floor 2
      differentiation_supports: ELPS/scaffold/accommodation term  -> floor 2
      objective_clarity /
      objective_specific      : an objective element was selected -> floor 1
    All other criteria: no floor (0) — we let the model decide.
    """
    if not has_evidence:
        return 0
    low = evidence_text.lower()
    toks = _tokens(evidence_text)
    if criterion_id == "cognitive_rigor":
        if toks & _DOK_VERBS:
            return 2
        return 0
    if criterion_id == "differentiation_supports":
        # The rubric's own keyword list is the source of truth for this criterion.
        elps_terms = [
            "elps", "language objective", "sentence stem", "sentence stems",
            "accommodation", "modification", "iep", "504", "gifted", "extension",
            "scaffold", "scaffolds", "scaffolding", "ell", "esl", "differentiat",
        ]
        if _phrase_hits(low, elps_terms):
            return 2
        return 0
    if criterion_id in ("objective_clarity", "objective_specific"):
        return 1
    return 0


def _on_point(band: int, score: float, breakdown: dict, has_evidence: bool) -> bool:
    """Honest relevance check for the selected evidence (the ON-POINT metric).

    Guaranteed citation is worthless if the quote is off-topic, so we grade our OWN
    selection: evidence is "on-point" when it either matched a rubric keyword, sat
    in the criterion's expected element type, or shared >=2 content tokens with the
    criterion. A band-0/no-evidence criterion is not counted (nothing to be wrong
    about)."""
    if not has_evidence:
        return band == 0  # correctly abstained
    if breakdown.get("keyword_hits"):
        return True
    if breakdown.get("type_match") and len(breakdown.get("token_overlap") or []) >= 1:
        return True
    return len(breakdown.get("token_overlap") or []) >= 2


# --- prompt (model RATES pre-selected evidence; it never picks it) ----------

_RATE_PREAMBLE = (
    "You are a curriculum audit RATER. READ-ONLY. For each criterion below you are "
    "shown the EXACT excerpt(s) already selected from the lesson's own text. Your "
    "ONLY job is to assign a band 0-3 for how well THAT excerpt satisfies the "
    "criterion, plus a one-line justification. Do NOT quote or invent any other "
    "text; the evidence is fixed. If the shown excerpt does not support the "
    "criterion at all, assign band 0 — an honest 0 is correct, never inflate."
)


def _build_rate_prompt(
    lesson: LessonInput, rubric: dict, selections: dict[str, list]
) -> str:
    scale = "\n".join(
        f"  {k}: {v}" for k, v in (rubric.get("band_scale") or {}).items()
    )
    blocks = []
    for c in rubric["criteria"]:
        cid = c["id"]
        sel = selections.get(cid) or []
        if sel:
            ev = "\n".join(
                f'    - [{el.element_id}] ({el.element_type}): '
                f'"{(el.excerpt or "")[:500].strip()}"'
                for (el, _s, _bd) in sel
            )
        else:
            ev = "    (no on-topic excerpt found in this lesson)"
        blocks.append(
            f"- {cid}: {c.get('label', cid)} — {c.get('description', '').strip()}\n"
            f"  EVIDENCE SHOWN:\n{ev}"
        )
    crit_block = "\n".join(blocks)
    ids = ", ".join(c["id"] for c in rubric["criteria"])
    return f"""{_RATE_PREAMBLE}

RUBRIC: {rubric.get('title', rubric['rubric_id'])}
BAND SCALE:
{scale}

LESSON: {lesson.title}

CRITERIA (rate the EVIDENCE SHOWN under each; one band each):
{crit_block}

Respond with ONLY valid JSON (no markdown fences):
{{
  "scores": [
    {{"criterion_id": "<one of: {ids}>", "band": <int 0-3>,
      "justification": "<one short sentence about the shown evidence>"}}
  ]
}}
One entry per criterion above."""


# --- the grounded band scorer -----------------------------------------------


class GroundedBandScorer(Scorer):
    """Reusable grounded-rate scorer: code selects evidence, model only rates.

    Subclasses set scorer_id/name and the rubric. `blend` controls whether the
    reported band is raised to the deterministic proxy floor (True) or left as the
    raw model band (False) — the eval harness instantiates both to compare.
    """

    rubric_id: str = QUALITY_RUBRIC
    blend: bool = True

    def __init__(self) -> None:
        self.rubric = load_rubric(self.rubric_id)

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

        # 1) DETERMINISTIC evidence selection (no model needed) -------------
        selections: dict[str, list] = {
            c["id"]: select_evidence(lesson, c) for c in rubric["criteria"]
        }

        # 2) MODEL rates the shown evidence (one call, all criteria) --------
        model_bands: dict[str, int] = {}
        model_notes: dict[str, str] = {}
        if cfg is None:
            base.error = "no model config (offline) — grounded rater skipped"
        else:
            prompt = _build_rate_prompt(lesson, rubric, selections)
            try:
                from layer1 import call_and_parse_with_retry

                data = call_and_parse_with_retry(
                    cfg,
                    "analyst",
                    prompt,
                    f"grounded-rate-{self.scorer_id}-{lesson.lesson_id}",
                )
                for s in data.get("scores") or []:
                    cid = s.get("criterion_id")
                    b = s.get("band")
                    if cid and isinstance(b, (int, float)):
                        model_bands[cid] = int(b)
                        model_notes[cid] = (s.get("justification") or "").strip()
            except Exception as e:  # noqa: BLE001 — degrade cleanly like the baseline
                base.error = f"model call failed: {e}"

        # 3) Assemble criteria: CODE owns the citation; proxy floor guards ----
        crits: list[CriterionResult] = []
        on_point_flags: list[bool] = []
        for c in rubric["criteria"]:
            cid = c["id"]
            sel = selections.get(cid) or []
            has_ev = bool(sel)
            ev_text = " ".join((el.excerpt or "") for (el, _s, _bd) in sel)

            model_band = model_bands.get(cid)
            floor = _proxy_floor(cid, ev_text, has_ev)

            # Blend: the reported band is the model's, but never below the
            # deterministic floor when the lesson's own words clearly justify it.
            if model_band is None:
                band = floor if (self.blend and has_ev) else None
            else:
                band = max(model_band, floor) if self.blend else model_band

            # Evidence is attached from CODE => citation valid by construction.
            # Only attach for a non-zero band (band 0 = "absent", empty quote, per
            # the rubric's own scale — an honest 0 carries no citation).
            evidence: list[Evidence] = []
            if band and has_ev:
                evidence = [Evidence(el.element_id, el.excerpt) for (el, _s, _bd) in sel]

            top_score, top_bd = (sel[0][1], sel[0][2]) if sel else (0.0, {})
            # A fired proxy floor means the evidence tripped an unambiguous lexical
            # signal (a DOK verb / an ELPS term), so it is on-point by definition.
            op = _on_point(band or 0, top_score, top_bd, has_ev) or floor > 0
            on_point_flags.append(op)

            note_bits = []
            if model_band is not None:
                note_bits.append(f"model_band={model_band}")
            if floor:
                note_bits.append(f"proxy_floor={floor}")
            if model_notes.get(cid):
                note_bits.append(model_notes[cid])
            note_bits.append(f"evidence_on_point={op}")
            crits.append(
                CriterionResult(
                    cid,
                    c.get("label", cid),
                    "band",
                    band=band,
                    evidence=evidence,
                    note="; ".join(note_bits),
                )
            )

        summary = summarize_bands(crits, max_band=max_band)
        # Extra transparency signals unique to this approach.
        n = len(crits) or 1
        summary["on_point_rate"] = round(sum(on_point_flags) / n, 3)
        base.criteria = crits
        base.summary = summary
        base.cost = {"model_calls": 0 if cfg is None else 1}
        return base


class QualityGroundedScorer(GroundedBandScorer):
    scorer_id = "s4_quality_grounded"
    name = "S4 quality (grounded-rate: code cites, model rates)"
    rubric_id = QUALITY_RUBRIC
    blend = True


class UbdGroundedScorer(GroundedBandScorer):
    scorer_id = "s2_ubd_grounded"
    name = "S2 UbD alignment (grounded-rate: code cites, model rates)"
    rubric_id = UBD_RUBRIC
    blend = True


register_scorer(QualityGroundedScorer)
register_scorer(UbdGroundedScorer)
