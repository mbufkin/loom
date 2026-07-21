#!/usr/bin/env python3
"""
extractive_scorer.py — "extractive-2stage" quality scorer (quality-race entry).

WHY THIS EXISTS
---------------
The shared band scorers (``s4_quality`` / ``s2_ubd`` in ``lesson_scorers.py``) ask
the local model to band EVERY rubric dimension in ONE call over a big candidate
block, AND to cite a verbatim excerpt per band. On the local Nemotron-nano-30B the
model reliably returns bands but fabricates / paraphrases its "verbatim" quote, so
the ``_band_result`` guardrail downgrades those bands to
"[unevidenced band — needs review]" and quality scoring ends up DEFERRED
(``lesson_rung.LOCKED_SCORERS`` excludes s2/s4).

APPROACH (extractive-2stage)
----------------------------
Do NOT score all dimensions at once. For EACH rubric criterion, run a focused call
over ONLY that criterion's ``reads_from`` element types:

  * Stage 1 (extract): "Copy the SINGLE most relevant verbatim sentence for
    <dimension>, or reply NONE." Then CODE validates the returned quote is an exact
    substring of one of the provided elements. If not, retry once; else treat as
    NONE.
  * Stage 2 (band): "Given this quote, assign band 0-3 for <dimension>."

We fold both stages into one JSON response ``{quote, band, note}`` per call (cheaper,
one round-trip per criterion) but the quote is STILL code-validated as a real
substring before any band > 0 is trusted. No valid quote => band 0 / absent.

HYPOTHESIS: a smaller, single-dimension context forces the model to actually copy
from the few elements in front of it instead of hallucinating a citation. The cost
is MORE model calls per lesson (one per criterion, +retries) — measured and reported
honestly by the eval harness (``run_eval.py``).

HARD CONSTRAINTS honoured here
------------------------------
* Auditor-only: we only ever cite the lesson's OWN words; never invent/rewrite.
* Additive-only: this module lives entirely under
  ``experiments/quality_race/extractive-2stage/`` and only IMPORTS shared code
  (``lesson_scoring``, ``rubrics``, ``layer1``, ``audit_lib``). It registers a NEW
  scorer id ``s4_quality_extractive`` so nothing shared is edited.
"""

from __future__ import annotations

# --- make the repo root importable when run from this experiment folder ------
# The shared modules (lesson_scoring, rubrics, layer1, audit_lib) live at the repo
# root. Adding it to sys.path keeps this file runnable from anywhere without
# touching packaging or any shared file.
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from audit_lib import parse_model_json  # noqa: E402
from lesson_scoring import (  # noqa: E402
    CriterionResult,
    Evidence,
    LessonInput,
    Scorer,
    ScorerResult,
    register_scorer,
    summarize_bands,
)
from rubrics import QUALITY_RUBRIC, UBD_RUBRIC, load_rubric  # noqa: E402

# How many candidate elements to show the model per criterion. Kept small on
# purpose — the whole bet is that a tight context forces grounded extraction.
MAX_CANDIDATES_PER_CRITERION = 10
# Excerpt length shown per element. Long enough to contain a full sentence, short
# enough to keep the per-criterion prompt cheap.
EXCERPT_CHARS = 600

# Stage 1 (extraction) preamble. Empirically, over-emphasizing "an empty answer is
# fine" makes the local model bail and return no quote even when a clearly relevant
# sentence is right in front of it. So Stage 1 pushes HARD toward copying, and only
# mentions the empty option as a narrow escape hatch for genuinely irrelevant
# candidate sets. (Grounding is still enforced in code, so this cannot fabricate.)
STAGE1_PREAMBLE = (
    "You are a READ-ONLY curriculum auditor. You judge ONLY the lesson's own text and "
    "never write, rewrite, paraphrase, or invent content. Your job here is to COPY a "
    "verbatim sentence — an exact run of characters from ONE element — that is most "
    "relevant to the given dimension."
)

# Stage 2 (band) preamble — the quote is already grounded, so this is pure judgment.
STAGE2_PREAMBLE = (
    "You are a READ-ONLY curriculum audit scorer. You judge ONLY the evidence quote "
    "shown (the lesson's own words); you never rewrite or invent content."
)


# Quote-ish punctuation a model tends to wrap its citation in even when told to copy
# verbatim (straight + curly doubles/singles). Stripped before substring matching.
_QUOTE_CHARS = "\"'“”‘’ \t\r\n"


def _normalize(text: str) -> str:
    """Whitespace-insensitive form for substring matching.

    Models frequently return a quote that is character-for-character correct EXCEPT
    for collapsed runs of spaces / newlines (the source elements carry lots of table
    padding and hard line-wraps). Requiring byte-identical matching would reject
    quotes that a human would call verbatim, so we compare on a whitespace-collapsed
    view of BOTH the quote and the source. We still return the SOURCE slice as the
    stored evidence, so the artifact always shows the lesson's real words.
    """
    return " ".join((text or "").split())


def _find_source_element(quote: str, candidates: list) -> tuple[str, str] | None:
    """Return (element_id, verbatim_source_excerpt) if ``quote`` is a real substring
    of some candidate element (whitespace-insensitive), else None.

    This is the CODE half of "force extraction": the model's claimed quote is only
    trusted when we can locate it inside an element we actually showed it. We also
    strip surrounding quote punctuation the model tends to add (e.g. it echoes the
    sentence wrapped in double quotes), since that wrapper is not part of the source
    and would otherwise fail an honest verbatim citation. We return the SOURCE's own
    text (not the model's echo) so stored evidence is guaranteed to be real words.
    """
    q = _normalize(quote).strip(_QUOTE_CHARS)
    if len(q) < 8:  # too short to be a meaningful citation (avoids matching "the")
        return None
    for el in candidates:
        if q in _normalize(el.excerpt or ""):
            return el.element_id, el.excerpt or ""
    return None


def _candidates_for(lesson: LessonInput, criterion: dict) -> list:
    """The elements a single criterion is allowed to read: its own ``reads_from``
    types only (fall back to all elements if that yields nothing, so a lesson with
    untyped elements is still scored rather than silently zeroed)."""
    reads = criterion.get("reads_from") or []
    els = lesson.elements_of_type(*reads) if reads else list(lesson.elements)
    if not els:
        els = list(lesson.elements)
    return els[:MAX_CANDIDATES_PER_CRITERION]


def _candidate_block(candidates: list) -> str:
    return (
        "\n\n".join(
            f"[{el.element_id}] ({el.element_type})\n\"\"\"\n{(el.excerpt or '')[:EXCERPT_CHARS]}\n\"\"\""
            for el in candidates
        )
        or "(no candidate elements for this dimension)"
    )


def _build_extract_prompt(
    lesson: LessonInput, criterion: dict, candidates: list, *, retry: bool = False
) -> str:
    """STAGE 1 — extraction only. No band asked for yet.

    Learned empirically on the local model: when a single call asks for a band AND a
    quote, the model returns the band and leaves the quote empty (it will judge but
    not commit to copying). Asking ONLY for a quote first forces it to actually pull
    a verbatim span from the few elements in front of it."""
    retry_note = (
        "\nYour previous quote was NOT found verbatim in the elements. Copy an EXACT "
        "run of characters from ONE element below — do not paraphrase, summarize, or "
        "add words. If truly nothing relates, set evidence_quote to \"\".\n"
        if retry
        else ""
    )
    return f"""{STAGE1_PREAMBLE}
{retry_note}
From the elements below, COPY the SINGLE most relevant verbatim sentence for judging
this ONE dimension. You MUST copy an exact span of characters from ONE element — do
not paraphrase or add words. Only set an empty quote if NONE of the elements relate
to this dimension at all.

DIMENSION: {criterion.get('label', criterion['id'])}
WHAT IT MEANS: {(criterion.get('description') or '').strip()}

LESSON: {lesson.title}
ELEMENTS (quote ONLY from these; cite by id):
{_candidate_block(candidates)}

Respond with ONLY valid JSON (no markdown fences):
{{
  "evidence_element_id": "<id from the elements above, or empty>",
  "evidence_quote": "<verbatim span copied from that element, or empty>"
}}"""


def _build_band_prompt(
    lesson: LessonInput, rubric: dict, criterion: dict, quote: str
) -> str:
    """STAGE 2 — band the dimension GIVEN the code-validated quote. The model can no
    longer dodge citing (the quote is already grounded); it only judges strength."""
    scale = "\n".join(
        f"  {k}: {v}" for k, v in (rubric.get("band_scale") or {}).items()
    )
    return f"""{STAGE2_PREAMBLE}

You are judging ONE dimension of a lesson, using ONLY the evidence quote below (it
was already verified to come from the lesson). Assign the single best band.

DIMENSION: {criterion.get('label', criterion['id'])}
WHAT IT MEANS: {(criterion.get('description') or '').strip()}

BAND SCALE (choose exactly one):
{scale}

EVIDENCE QUOTE (the lesson's own words):
\"\"\"
{quote[:EXCERPT_CHARS]}
\"\"\"

Respond with ONLY valid JSON (no markdown fences):
{{
  "band": <int, one of the scale keys above>,
  "note": "<one short sentence justifying the band from the quote>"
}}"""


def _score_one_criterion(
    lesson: LessonInput,
    rubric: dict,
    criterion: dict,
    cfg: dict,
) -> tuple[CriterionResult, int]:
    """Two-stage focused scoring for ONE criterion.

    Stage 1 (extract, +1 retry if the quote is not a verbatim substring) then Stage 2
    (band the validated quote). Returns the criterion result and the number of model
    calls it cost (1-2 for a NONE dimension, 2-3 when a citation is found)."""
    from layer1 import call_and_parse_with_retry

    cid = criterion["id"]
    label = criterion.get("label", cid)
    candidates = _candidates_for(lesson, criterion)
    calls = 0
    matched: tuple[str, str] | None = None
    note = ""

    # --- Stage 1: force a verbatim extraction (validated in code) ---
    for attempt in range(2):
        prompt = _build_extract_prompt(
            lesson, criterion, candidates, retry=(attempt == 1)
        )
        calls += 1
        try:
            data = call_and_parse_with_retry(
                cfg,
                "analyst",
                prompt,
                f"extract-{cid}-{lesson.lesson_id}",
                parse_retries=0,  # we own the semantic retry loop
            )
        except Exception as e:  # noqa: BLE001 — degrade cleanly, never crash harness
            note = f"stage-1 model/parse error: {e}"
            break
        raw_quote = (data.get("evidence_quote") or "").strip()
        if not raw_quote:
            break  # model honestly found nothing relevant -> absent, no retry
        matched = _find_source_element(raw_quote, candidates)
        if matched is not None:
            break

    # No grounded quote => band 0 / absent (the whole bet: never trust an ungrounded
    # judgment).
    if matched is None:
        note = (note or "no verbatim evidence found for this dimension").strip()
        return (
            CriterionResult(cid, label, "band", band=0, evidence=[], note=note),
            calls,
        )

    eid, src_excerpt = matched
    evidence = [Evidence(eid, src_excerpt)]

    # --- Stage 2: band the dimension given the validated quote ---
    band = 1  # floor: a real citation means the dimension is at least emerging
    calls += 1
    try:
        bdata = call_and_parse_with_retry(
            cfg,
            "analyst",
            _build_band_prompt(lesson, rubric, criterion, src_excerpt),
            f"band-{cid}-{lesson.lesson_id}",
            parse_retries=0,
        )
        b = bdata.get("band")
        if isinstance(b, (int, float)):
            band = max(1, int(b))  # never drop a cited dimension below emerging
        note = (bdata.get("note") or "").strip()
    except Exception as e:  # noqa: BLE001 — keep the grounded band-1 on stage-2 failure
        note = f"stage-2 band error (kept floor band 1): {e}"

    return (
        CriterionResult(cid, label, "band", band=band, evidence=evidence, note=note),
        calls,
    )


def _extractive_result(
    lesson: LessonInput, rubric: dict, scorer_id: str, cfg: dict | None
) -> ScorerResult:
    max_band = max((rubric.get("band_scale") or {0: ""}).keys())
    if cfg is None:
        # Same graceful-offline contract as the shared _band_result.
        res = ScorerResult(
            scorer_id=scorer_id,
            rubric_id=rubric["rubric_id"],
            rubric_version=rubric["version"],
            scoring="band",
            lesson_id=lesson.lesson_id,
            error="no model config (offline) — extractive scorer skipped",
            criteria=[
                CriterionResult(c["id"], c.get("label", c["id"]), "band", note="skipped")
                for c in rubric["criteria"]
            ],
        )
        return res

    crits: list[CriterionResult] = []
    total_calls = 0
    for c in rubric["criteria"]:
        cr, calls = _score_one_criterion(lesson, rubric, c, cfg)
        crits.append(cr)
        total_calls += calls

    return ScorerResult(
        scorer_id=scorer_id,
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["version"],
        scoring="band",
        lesson_id=lesson.lesson_id,
        criteria=crits,
        summary=summarize_bands(crits, max_band=max_band),
        cost={"model_calls": total_calls},
    )


class ExtractiveQualityScorer(Scorer):
    """S4 quality, scored per-dimension with forced verbatim extraction."""

    scorer_id = "s4_quality_extractive"
    name = "S4 quality (extractive-2stage, per-dimension forced citation)"

    def __init__(self) -> None:
        self.rubric = load_rubric(QUALITY_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return _extractive_result(lesson, self.rubric, self.scorer_id, cfg)


class ExtractiveUbdScorer(Scorer):
    """S2 UbD alignment, same extractive-2stage machinery (bonus: the approach is
    rubric-agnostic, so we prove it works on the second banded rubric too)."""

    scorer_id = "s2_ubd_extractive"
    name = "S2 UbD alignment (extractive-2stage, per-dimension forced citation)"

    def __init__(self) -> None:
        self.rubric = load_rubric(UBD_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return _extractive_result(lesson, self.rubric, self.scorer_id, cfg)


# Register under NEW ids only — no shared scorer is touched or overridden.
register_scorer(ExtractiveQualityScorer)
register_scorer(ExtractiveUbdScorer)
