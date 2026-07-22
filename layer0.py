#!/usr/bin/env python3
"""
layer0.py — Layer 0: Document Ingestion & Evidence Extraction.

See docs/BETS.md (Bet 9, Bet 10) and docs/roadmap.md for the design this implements.

Runs BEFORE any unit organization (ingest.py). Reads the
raw sources/ directory directly, one document at a time, and produces a shared
evidence ledger — one flat row per instructional element, across every document —
that downstream layers read instead of each re-deriving their own interpretation
of the source text.

EXTRACT   — deterministic, per file (scrub_document(), full text, never truncated — Bet 1)
DECOMPOSE — model, one document at a time (narrow task — Bet 3). ONE strong model
            (Qwen3-32B dense) reads every document once; only an uncertain result
            (explicit escalate flag, any low-confidence element, or invalid schema)
            triggers a single on-demand recheck — the SAME model, independent
            deeper-read pass — whose output is then taken. This replaced the old
            Gemma-Tier1 -> Qwen-Tier2 escalation between two DIFFERENT weaker models
            (docs/BETS.md Bets 5 & 9, 2026-07-08 revision). No cheap triage tier.
LEDGER    — one flat JSON file, one row per element, with citations (Bet 4)

Auditor-only: extracts and classifies; never generates or fixes curriculum content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from audit_lib import (
    atomic_write,
    doc_id_from_filename,
    excerpt_cited_in,
    iter_source_files,
    load_config,
    log,
    model_chat,
    normalize_ws,
    parse_model_json,
    project_dir,
    scrub_document,
    validate_slug_id,
)
from schema_validate import (
    ELEMENT_TYPES,
    LAYER0_TAXONOMY_VERSION,
    normalize_element_type,
    raise_on_errors,
    validate_layer0_elements,
)

# Full document text up to this many characters is sent as one prompt (Bet 1: never
# truncate). Above this, real map/reduce chunking kicks in (see split_into_chunks):
# separate primary/recheck calls per chunk, then a reduce/dedup merge — NOT a single
# oversized prompt. (v1 history: this replaced an earlier "reassemble with part
# markers into one giant prompt" approach that was proven, live, against the 843K-char
# AP CSP CED framework doc, to silently under-extract — 13 elements from 266 pages —
# because the model quietly sampled rather than exhaustively covering a prompt that
# size. See docs/roadmap.md "Large single-document chunking" for the full writeup.)
# Bluebonnet TE/Learn SE validation (2026-07-18): 60k chunks + 16k max_tokens
# repeatedly truncated mid-JSON array ("Expecting ',' delimiter" ~54k chars of
# output). Smaller chunks → fewer elements per call → JSON fits. Docs in the
# 40–100k band (many Learn/Succeed SEs) must also chunk, not take the single-
# prompt path that was failing wholesale.
CHUNK_THRESHOLD_CHARS = 40_000
CHUNK_SIZE_CHARS = 30_000
OVERLAP_PARAGRAPHS = 2  # trailing paragraphs repeated at the start of the next chunk

# Overnight TE runs: give decompose more wall-clock without raising the global
# config timeout for small Dallas-shaped calls elsewhere.
LARGE_CALL_TIMEOUT_SECONDS = 900
DECOMPOSE_PARSE_RETRIES = 2  # was 1; Bluebonnet truncations often succeed on retry

# --- Citation mechanism: pointers, not generated text -----------------------
# Earlier versions asked the model to *retype* a verbatim excerpt, then verified it
# post-hoc with excerpt_cited_in() (fuzzy whitespace-normalized substring match).
# That caught outright fabrication, but three rounds of live testing (Dallas corpus,
# AP CSP CED, region10 corpus — see docs/roadmap.md #4-#8) showed prompt rules alone
# cannot fully stop a generator from truncating, ellipsis-splicing two non-adjacent
# spans together, or silently dropping a clause mid-quote: the failure lives in the
# act of generating quote text at all, and no amount of "don't do that" instruction
# closes 100% of that gap.
#
# Researched how others solved this (docs/BETS.md has the full citation trail):
# Anthropic's Citations API computes start_char/end_char positions at the API layer
# instead of having the model generate quote text ("the model can't fabricate
# citations — every citation maps to a real position"); the instructor-ai and
# verbatim-rag projects converge on the same idea — force the model to emit a
# *pointer* into source text, then have YOUR code slice the actual excerpt, never
# the model. A pointer can't be truncated, spliced, or paraphrased: it's just an
# integer, and it either resolves to real text or it's an obviously invalid index.
#
# Our version of the same idea, sized for a local model without a dedicated
# citations feature: number the paragraphs of whatever text span the model is
# reading, ask it to cite by PARAGRAPH NUMBER(S) instead of retyping words, and
# resolve the real excerpt from our own already-known paragraph list afterward.
# Trade-off, stated honestly: excerpts are now whole-paragraph granularity, not a
# hand-picked <=50-word sentence — coarser, but every excerpt is now verbatim BY
# CONSTRUCTION, not by post-hoc verification. For an evidence ledger whose whole
# job is faithful citation, that trade is worth it.
#
# --- 2026-07-08 update: flat list -> start/end RANGE ------------------------
# The first version of this asked for a FLAT LIST of paragraph numbers, e.g.
# [4, 5] or [16, 22], on the theory that the model would only ever list the
# numbers of one truly contiguous run. Live hand-check of every
# excerpt_noncontiguous=True row from a full region10 run (docs/roadmap.md
# item #10) found this doesn't hold: on long real spans (a multi-day activity
# block, a multi-paragraph task description), the model very consistently
# listed only the FIRST and LAST paragraph of the span and silently dropped
# everything in between — e.g. [16, 22] instead of [16, 17, 18, 19, 20, 21, 22]
# — despite an explicit rule against exactly that. This is not our prompt being
# sloppy: it's the documented "lost-in-the-middle" effect (Liu et al. 2023,
# TACL 2024) — LLMs show a U-shaped attention bias toward the start/end of
# whatever they're reading or generating and under-attend to the middle, a
# side effect of RoPE positional decay and causal masking, not a fixable
# instruction-following gap. A minority of the same flagged rows were a
# different, real problem: genuine conflation of two unrelated paragraphs
# (e.g. a "Time Frame: 10 days" fact + an unrelated resource-link list) into
# one citation.
#
# The flat-list format made the first (much more common) failure possible by
# construction: a list of individual integers has no concept of "everything
# between these two." Switching to an explicit inclusive RANGE
# (excerpt_start_paragraph, excerpt_end_paragraph) removes that degree of
# freedom entirely for the common case — the model states where its evidence
# begins and ends, and our code (never the model) walks every paragraph in
# between, so a skipped middle is now structurally impossible, the same way
# the original list-of-pointers redesign made fabrication structurally
# impossible. It does NOT fix the second failure mode (a model choosing a
# genuinely too-wide start/end that sweeps in unrelated content) — that
# trades "silently missing a paragraph" for "visibly, checkably including a
# too-wide span," which is a strictly easier problem: we can catch it with a
# cheap width-outlier heuristic (see WIDE_SPAN_PARAGRAPHS below) instead of
# needing fuzzy semantic judgment to notice a *silent* gap.


def number_paragraphs(text: str) -> tuple[str, list[str]]:
    """Split text into paragraphs and render a numbered list for the prompt.

    Returns (numbered_text_for_prompt, paragraphs) where paragraphs[i] is the raw
    verbatim text for paragraph number i+1 (1-indexed to match what we show the
    model) — this list is what excerpt_start_paragraph/excerpt_end_paragraph get
    resolved against later, so the model is never trusted to reproduce the text
    itself.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text] if text.strip() else []
    numbered = "\n\n".join(f"[P{i}] {p}" for i, p in enumerate(paragraphs, start=1))
    return numbered, paragraphs


TIER1_RULES = """You are a curriculum audit Analyst performing Layer 0 evidence extraction. READ-ONLY.

TASK: decompose ONE document into its distinct instructional elements. A document is
NOT necessarily one atomic unit of evidence — e.g. a 5E lesson plan bundles Engage /
Explore / Explain / Elaborate / Evaluate segments, each with its own timing, in one
file. A simple exit ticket or worksheet may be exactly one element.

RULES (mandatory):
- Read the FULL document text below, start to finish. Do not guess from the filename.
  The text is shown as a numbered list of paragraphs, like "[P3] some paragraph text".
  Those [P<N>] numbers are not part of the document — they're reference labels so you
  can cite by number instead of retyping text (see CITATION below).
- Classify each element by UNIVERSAL INSTRUCTIONAL FUNCTION, not by the curriculum's
  own framework-specific phase name. Do not say "Explore" — say what that phase
  functions AS: hook_engagement, direct_instruction, guided_practice,
  independent_practice, assessment_checkpoint, reflection_closure,
  logistics_materials, or standards_objectives.
- If you cannot confidently determine an element's function, position, or timing,
  answer "unclear" / "unknown" and set confidence "low". An honest "unknown" is a
  valid, expected answer — never invent structure that is not in the text.
- CITATION: every element MUST carry "excerpt_start_paragraph" and
  "excerpt_end_paragraph" — PLAIN INTEGERS marking the first and last paragraph
  of ONE CONTIGUOUS span. Do NOT retype or quote any text yourself; just point
  at where the evidence starts and ends. Our code will automatically include
  EVERY paragraph from start to end, inclusive — you cannot "skip" the middle
  ones, so choose the tightest true boundaries, not just two representative
  points. Exact format rules:
  - Bare integers only: write 4, never "P4" or "[P4]" — the "[P<N>]" label in the
    text below is a label for YOU to read, not part of the JSON value you write.
  - One paragraph of evidence: set start and end to the SAME number, e.g.
    excerpt_start_paragraph=4, excerpt_end_paragraph=4.
  - A real multi-paragraph span (a multi-day activity block, a multi-part task
    description): set start to its first paragraph and end to its true LAST
    paragraph — do not shortcut to "first and last mention," walk to where the
    span actually ends. Every paragraph in between will be pulled in
    automatically, so an end set too far past the real boundary will visibly
    drag in unrelated content — read to the actual end, not past it.
  - One element, ONE contiguous location: if the same idea appears in several
    unrelated places in the document, pick the single best/clearest occurrence,
    or (if they are genuinely separate instructional elements) list them as
    separate elements each with their own start/end. Never stretch a range to
    "cover" two unrelated mentions far apart — that pulls in everything between
    them as if it were all evidence, which is worse than picking one clean spot.
- Regex/filename hints given below are PRIORS ONLY. Cross-check them against your
  own reading. Disagreement with a prior is a useful finding, not an error to hide.
- NEVER write, invent, or suggest curriculum content. You are an auditor, not an author.
"""

TIER1_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "elements": [
    {
      "element_type": "hook_engagement|direct_instruction|guided_practice|independent_practice|assessment_checkpoint|reflection_closure|logistics_materials|standards_objectives|unclear",
      "excerpt_start_paragraph": <plain integer, first paragraph of this element's evidence>,
      "excerpt_end_paragraph": <plain integer, LAST paragraph of this element's evidence -- same as start if only one paragraph>,
      "inferred_position": "<e.g. 'Day 2', 'early in unit', or 'unknown'>",
      "inferred_timing": "<e.g. '10-15 minutes', or 'unknown'>",
      "confidence": "high|medium|low"
    }
  ],
  "document_confidence": "high|medium|low",
  "escalate_to_tier2": true,
  "notes": ["optional auditor notes — findings only, never fixes"]
}
Set "escalate_to_tier2": true if ANY element has confidence "low", or if you are not
sure how many distinct elements this document actually contains."""

TIER2_RULES = """You are a curriculum audit Verifier performing a Tier 2 deep read. READ-ONLY.

Tier 1 flagged this document as ambiguous. Your job is to INDEPENDENTLY decompose it
again from the full text below — do not assume Tier 1's element count or boundaries
were correct. Read slower and more carefully than a first pass would.

RULES (mandatory):
- Read the FULL document text below, start to finish. The text is shown as a numbered
  list of paragraphs, like "[P3] some paragraph text" — those [P<N>] labels are not
  part of the document, they're reference numbers for CITATION below.
- Classify each element by UNIVERSAL INSTRUCTIONAL FUNCTION (see list in the schema),
  not the curriculum's own framework-specific phase name.
- If you genuinely cannot determine something, answer "unclear" / "unknown" with
  confidence "low" — do not force a confident answer just because this is the deep pass.
- CITATION: every element MUST carry "excerpt_start_paragraph" and
  "excerpt_end_paragraph" — PLAIN INTEGERS marking the first and last paragraph
  of ONE CONTIGUOUS span. Do NOT retype or quote any text yourself; just point
  at where the evidence starts and ends. Our code will automatically include
  EVERY paragraph from start to end, inclusive — you cannot "skip" the middle
  ones, so choose the tightest true boundaries, not just two representative
  points. Exact format rules:
  - Bare integers only: write 4, never "P4" or "[P4]" — the "[P<N>]" label in the
    text below is a label for YOU to read, not part of the JSON value you write.
  - One paragraph of evidence: set start and end to the SAME number.
  - A real multi-paragraph span: set start to its first paragraph and end to its
    true LAST paragraph — walk to where the span actually ends, don't shortcut
    to "first and last mention." Everything in between is pulled in
    automatically, so an end set too far past the real boundary will visibly
    drag in unrelated content.
  - One element, ONE contiguous location: if the same idea appears in several
    unrelated places, pick the single best/clearest occurrence, or (if genuinely
    separate instructional elements) list them as separate elements. Never
    stretch a range to "cover" two unrelated mentions far apart.
- NEVER write, invent, or suggest curriculum content.
"""

TIER2_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "elements": [
    {
      "element_type": "hook_engagement|direct_instruction|guided_practice|independent_practice|assessment_checkpoint|reflection_closure|logistics_materials|standards_objectives|unclear",
      "excerpt_start_paragraph": <plain integer, first paragraph of this element's evidence>,
      "excerpt_end_paragraph": <plain integer, LAST paragraph of this element's evidence -- same as start if only one paragraph>,
      "inferred_position": "<e.g. 'Day 2', 'early in unit', or 'unknown'>",
      "inferred_timing": "<e.g. '10-15 minutes', or 'unknown'>",
      "confidence": "high|medium|low"
    }
  ],
  "document_confidence": "high|medium|low",
  "escalate_to_tier2": false,
  "notes": ["optional auditor notes — what made this document ambiguous"]
}
"escalate_to_tier2" is always false here — Tier 2 is the deep pass, there is no Tier 3
re-decompose (Tier 3 is the separate Analyst/Verifier conformance cross-check, later)."""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def build_priors_block(record: dict) -> str:
    return (
        f"filename: {record['source_file']}\n"
        f"regex-guessed doc_type (PRIOR ONLY, not authoritative): {record['doc_type']}\n"
        f"regex day_hints (PRIOR ONLY): {record.get('day_hints', [])}\n"
        f"regex unit_length_days_hint (PRIOR ONLY): {record.get('unit_length_days_hint')}\n"
        f"regex standards_refs (PRIOR ONLY): {record.get('standards_refs', [])}"
    )


# How much of the document's opening text to show every chunk as orientation.
# Kept small (~1 paragraph of context, not a full summary) so it doesn't eat into
# the token budget that should go to the chunk's own content.
ORIENTATION_CHARS = 600


def needs_chunking(record: dict) -> bool:
    return record["char_count_clean"] > CHUNK_THRESHOLD_CHARS


def build_doc_orientation(full_text: str) -> str:
    """Cheap, zero-extra-model-call stand-in for Anthropic's "Contextual Retrieval"
    chunk-context-prefix technique (github.com/anthropics/claude-cookbooks,
    "contextual-embeddings"; Anthropic eng blog, Sept 2024). That technique has an
    LLM write a short blurb situating each chunk within the whole document before
    it's embedded, because chunks read in isolation lose document-level context.

    We adapt the PRINCIPLE, not the mechanism: Anthropic pays an LLM call per chunk
    to *generate* orientation text; we can't afford that here (a 15-chunk document
    would mean 15 extra decompose-sized calls), and their own follow-up finding
    (arXiv 2602.16974, RQ3) shows LLM-generated context can even *hurt* when the
    task is "distinguish content within one document" rather than "rank chunks
    against a query" — which is closer to our in-document decompose task than
    their in-corpus retrieval setting. So instead we slice the document's own
    opening text (title, header, framing paragraph) verbatim and hand every chunk
    that same short orientation block for free. It's weaker than an LLM summary,
    but it's zero-cost, has zero hallucination risk, and directly targets the
    failure mode we saw in the AP CSP CED run: a model with no idea what larger
    document it's looking at fell back on memorized training data instead of the
    (garbled) chunk in front of it.
    """
    opening = full_text[:ORIENTATION_CHARS].strip()
    if not opening:
        return ""
    return (
        f"\nDOCUMENT ORIENTATION (the opening of the FULL document, shown for context "
        f"only). This block has NO [P<N>] numbers and is not part of the numbered "
        f"chunk text below — since citation is by paragraph NUMBER now, not text, it "
        f"is structurally impossible to cite anything from this block; it can only "
        f"inform how you classify what's actually below it:\n"
        f'"""\n{opening}\n"""\n'
    )


def split_into_chunks(
    text: str,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap_paragraphs: int = OVERLAP_PARAGRAPHS,
) -> list[str]:
    """Heading-aware map/reduce chunking (Bet 1): split on blank-line paragraph
    boundaries so a heading is never severed from its body, with trailing paragraphs
    repeated at the start of the next chunk so an element split across a boundary
    still appears whole in at least one chunk. Each chunk gets its own model call —
    this is real chunking, not a single oversized reassembled prompt.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []

    # Guard: a single paragraph bigger than chunk_size (e.g. PDF extraction with no
    # blank lines at all) must still be split, or chunking silently does nothing.
    safe_paragraphs: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            safe_paragraphs.append(para)
        else:
            for i in range(0, len(para), chunk_size):
                safe_paragraphs.append(para[i : i + chunk_size])

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in safe_paragraphs:
        if current_len + len(para) > chunk_size and current:
            chunks.append("\n\n".join(current))
            overlap_start = max(0, len(current) - overlap_paragraphs)
            current = current[overlap_start:]
            current_len = sum(len(p) for p in current)
        current.append(para)
        current_len += len(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def dedup_elements(elements: list[dict]) -> list[dict]:
    """Reduce step: drop elements whose (type, resolved excerpt) already appeared —
    overlap paragraphs between adjacent chunks otherwise produce exact duplicates.
    Dedup key is the RESOLVED excerpt text (built in build_ledger_rows from the
    paragraph range), not the model's own excerpt_start_paragraph/excerpt_end_paragraph
    numbers — two chunks number the same overlapping paragraph differently (it's
    index 1 in the next chunk, wasn't index 1 in the previous one), so comparing
    ranges directly would never match; comparing the resolved text is what
    actually catches the overlap duplicate.
    Near-duplicates with reworded excerpts are NOT caught by this — known limitation.
    """
    seen: set[tuple[str, str]] = set()
    deduped = []
    for el in elements:
        key = (el.get("element_type"), normalize_ws(el.get("excerpt", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(el)
    return deduped


def model_call(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    # 16384 (was 8192): content-dense chunks were hitting the 8192 ceiling mid-array,
    # producing a deterministic "Expecting ',' delimiter" JSON parse failure that a
    # retry cannot fix (observed live against the AP CSP framework — see roadmap.md).
    return model_chat(
        cfg,
        role,
        messages,
        step,
        temperature=0.1,
        max_tokens=16384,
        timeout_seconds=timeout_seconds,
    )


def extract_content(response: dict) -> str:
    return response["choices"][0]["message"]["content"]


def _decompose_text_with_retry(
    cfg: dict,
    role: str,
    rules: str,
    schema: str,
    priors_block: str,
    text: str,
    char_label: str,
    step: str,
    chunk_note: str = "",
    parse_retries: int = DECOMPOSE_PARSE_RETRIES,
    timeout_seconds: float | None = None,
) -> tuple[dict, list[str]]:
    """Call a model to decompose one span of text, retrying on PARSE failure (not
    just HTTP failure). Works identically for a whole document or a single chunk.

    model_chat() already retries transient HTTP/connection errors. But a 200 OK response
    that comes back truncated or malformed mid-generation is a distinct failure mode
    (observed live: a response cut off mid-string, no HTTP error at all) — this must be
    retried too, or one flaky generation silently drops a whole document from the ledger.

    Returns (data, paragraphs): paragraphs is the same numbered list shown to the
    model, needed by the caller to resolve "excerpt_start_paragraph"/
    "excerpt_end_paragraph" back to real text — the model only ever sees/returns
    paragraph numbers, never the text itself (see the "Citation mechanism"
    comment above TIER1_RULES for why).
    """
    numbered_text, paragraphs = number_paragraphs(text)
    prompt = f"""{rules}
{chunk_note}
{priors_block}

DOCUMENT TEXT ({char_label}, shown as numbered paragraphs):
{numbered_text}

{schema}
"""
    last_err: Exception | None = None
    for attempt in range(parse_retries + 1):
        resp = model_call(
            cfg,
            role,
            [{"role": "user", "content": prompt}],
            step,
            timeout_seconds=timeout_seconds,
        )
        try:
            return parse_model_json(extract_content(resp), context=step), paragraphs
        except ValueError as e:
            last_err = e
            if attempt < parse_retries:
                log(
                    f"WARN: {step} parse failure (attempt {attempt + 1}), retrying: {e}"
                )
    # Bluebonnet Practice/Succeed-class failures: leave a one-line operator hint.
    hint = (
        " — if this keeps failing, check .raw/ for truncated JSON; "
        "force re-chunk with a smaller CHUNK_SIZE_CHARS or re-run this doc alone"
    )
    raise ValueError(
        f"{step}: parse failed after {parse_retries + 1} attempts: {last_err}{hint}"
    )


def decompose_text(
    cfg: dict,
    priors_block: str,
    text: str,
    char_label: str,
    step: str,
    chunk_note: str = "",
    timeout_seconds: float | None = None,
) -> tuple[dict, list[str]]:
    """Primary decomposition pass — the one strong model reads the span. (The
    "analyst" role now resolves to the same single model as "verifier"; see config.yaml.)
    """
    return _decompose_text_with_retry(
        cfg,
        "analyst",
        TIER1_RULES,
        TIER1_SCHEMA,
        priors_block,
        text,
        char_label,
        step,
        chunk_note,
        timeout_seconds=timeout_seconds,
    )


def recheck_text(
    cfg: dict,
    priors_block: str,
    text: str,
    char_label: str,
    step: str,
    chunk_note: str = "",
    timeout_seconds: float | None = None,
) -> tuple[dict, list[str]]:
    """On-demand recheck pass — the SAME strong model re-reads the span independently
    with deeper-read framing (docs/BETS.md Bet 5). Not a different/stronger model:
    the "verifier" role points at the same endpoint as "analyst" in config.yaml."""
    return _decompose_text_with_retry(
        cfg,
        "verifier",
        TIER2_RULES,
        TIER2_SCHEMA,
        priors_block,
        text,
        char_label,
        step,
        chunk_note,
        timeout_seconds=timeout_seconds,
    )


# A legitimate single-span citation on real region10/AP-CSP documents topped out
# around 7-10 paragraphs (e.g. a full "Day 1...Day 10" pacing block). Set the
# outlier threshold comfortably above that so normal wide-but-real spans don't
# trip it, while a span that sweeps in unrelated document sections (the old
# conflation failure, e.g. [4, 27] stretched into a 24-paragraph range) does.
WIDE_SPAN_PARAGRAPHS = 12

# Found live (2026-07-09, docs/BETS.md Bet 14 incident writeup): a citation range
# is validated for TYPE (both bounds are ints) by validate_layer0_elements() before
# the escalation decision, but not for being IN RANGE — that only happens later in
# resolve_excerpt(), by which point the primary-vs-recheck choice has already been
# made blind to it. Consequence, found on the live Dallas corpus: a recheck pass
# can confidently hallucinate paragraph numbers far past the document's real length
# (one 40-paragraph document got citations up to paragraph 2163) and, because the
# old logic unconditionally preferred a schema-valid recheck over the primary pass
# with no comparison of which one actually resolved, that garbage silently WON over
# a primary pass whose citations were fine. These two thresholds close that gap:
# resolvability now feeds back into both the escalate decision and the pass choice.
UNCITED_ESCALATION_FRACTION = (
    0.15  # primary this uncited or worse -> treat as uncertain, try a recheck
)
HIGH_UNCITED_FLAG_FRACTION = 0.30  # even the BEST of the two passes this uncited -> flag distinctly, don't hide it


def resolve_excerpt(
    paragraphs: list[str], start: object, end: object
) -> tuple[str, bool, bool]:
    """Turn the model's excerpt_start_paragraph/excerpt_end_paragraph range into
    real, verbatim text spanning EVERY paragraph in between.

    This is the point of the range-based citation redesign (see the "2026-07-08
    update" comment above TIER1_RULES): the model never generates the excerpt
    text and can no longer silently skip paragraphs inside its own cited range
    either — the code always walks the full start..end span. All that's left to
    check is whether the range itself is valid and not suspiciously wide.

    Returns (excerpt_text, valid, wide_span):
    - valid=False means a non-integer, out-of-range, or inverted (end < start)
      bound — the model equivalent of a hallucinated citation, caught as a
      simple bounds check instead of a string search.
    - wide_span=True flags a real (if rarer) remaining concern: the range is
      wide enough (see WIDE_SPAN_PARAGRAPHS) that it may be sweeping in
      unrelated content between two only-loosely-related endpoints — worth a
      human glancing at, even though every word in the excerpt is still 100%
      genuine, contiguous source text.
    """
    try:
        start_n, end_n = int(start), int(end)
    except (TypeError, ValueError):
        return "", False, False
    if start_n < 1 or end_n > len(paragraphs) or end_n < start_n:
        return "", False, False
    excerpt = "\n\n".join(paragraphs[start_n - 1 : end_n])
    wide_span = (end_n - start_n + 1) > WIDE_SPAN_PARAGRAPHS
    return excerpt, True, wide_span


def build_ledger_rows(
    record: dict,
    tier: int,
    chunked: bool,
    data: dict,
    paragraphs: list[str],
    chunk_id: str | None = None,
    errors: list[str] | None = None,
) -> list[dict]:
    rows = []
    suffix = f"-{chunk_id}" if chunk_id else ""
    for i, el in enumerate(data.get("elements", []), start=1):
        excerpt, valid, wide_span = resolve_excerpt(
            paragraphs,
            el.get("excerpt_start_paragraph"),
            el.get("excerpt_end_paragraph"),
        )
        element_id = f"{record['doc_id']}{suffix}-e{i}"
        # validate_layer0_elements() flagged schema errors upstream (which only
        # decides whether to attempt a same-model recheck — see
        # _decompose_with_recheck) but never actually stopped a bad element_type
        # from reaching the ledger; this is the actual enforcement point, same
        # coercion Layer 0-B's split path uses, so the two build paths agree.
        etype = coerce_element_type(
            el.get("element_type"), element_id, errors if errors is not None else []
        )
        rows.append(
            {
                "element_id": element_id,
                "doc_id": record["doc_id"],
                "source_file": record["source_file"],
                "element_type": etype,
                "taxonomy_version": LAYER0_TAXONOMY_VERSION,
                "excerpt": excerpt,
                "excerpt_start_paragraph": el.get("excerpt_start_paragraph"),
                "excerpt_end_paragraph": el.get("excerpt_end_paragraph"),
                # "cited" no longer means "did a string search find this text" — it
                # means "did the model's paragraph range resolve to a real, valid
                # span at all". Structurally, this should almost always be True now;
                # False here is a hallucinated/out-of-range/inverted range, a much
                # rarer and much more clearly a "the model made this up" signal than
                # the old fuzzy text-match misses ever were.
                "cited": valid,
                # Replaces the old excerpt_noncontiguous flag (moot now — a range is
                # contiguous by construction). Flags the ONE failure mode the range
                # redesign does not remove: a validly-resolved but suspiciously wide
                # span that may be sweeping in unrelated content between two only
                # loosely-related endpoints (see WIDE_SPAN_PARAGRAPHS).
                "excerpt_wide_span": wide_span,
                # This should be structurally impossible to fail now — excerpt is
                # sliced directly from the same text the model read, not generated —
                # but a False here would mean number_paragraphs()/resolve_excerpt()
                # itself has a real bug (e.g. a paragraph-splitting mismatch), which
                # is exactly the kind of "trust but verify" check worth keeping
                # cheap and permanent rather than removing once the redesign works.
                "excerpt_sanity_check_passed": (
                    excerpt_cited_in(excerpt, record["content_clean"])
                    if valid
                    else None
                ),
                "inferred_position": el.get("inferred_position"),
                "inferred_timing": el.get("inferred_timing"),
                "confidence": el.get("confidence"),
                "tier": tier,
                "chunked": chunked,
                "chunk_id": chunk_id,
                "regex_doc_type_prior": record["doc_type"],
                "regex_day_hints_prior": record.get("day_hints", []),
                "content_hash": content_hash(record["content_clean"]),
            }
        )
    return rows


def _uncited_fraction(rows: list[dict]) -> float:
    """Share of a pass's OWN rows whose citation range failed to resolve
    (`cited=False` — see resolve_excerpt). The single number this module uses to
    decide both whether a pass is trustworthy enough to skip a recheck, and,
    when two passes exist, which one actually cited real text more often."""
    if not rows:
        return 0.0
    return sum(1 for r in rows if not r["cited"]) / len(rows)


def _decompose_with_recheck(
    cfg: dict,
    record: dict,
    priors_block: str,
    text: str,
    char_label: str,
    step_prefix: str,
    raw_dir: Path,
    chunk_id: str | None,
) -> tuple[list[dict], int, bool, list[str]]:
    """Single strong-model decomposition of one span (whole doc or one chunk), with
    an on-demand SAME-MODEL recheck (docs/BETS.md Bets 5 & 9, 2026-07-08). The model
    reads the span once; only an uncertain primary result — explicit escalate flag,
    any low-confidence element, a schema-invalid result, or a high UNCITED rate
    (Bet 14 addendum, 2026-07-09: a citation range failing to resolve is itself
    uncertainty, just discovered later than schema/confidence are) — triggers a
    second independent pass by the SAME strong model (deeper-read framing).
    Replaces the old Gemma-Tier1 -> Qwen-Tier2 escalation between two DIFFERENT
    weaker models; there is no cheap triage tier anymore.

    Whichever pass ran, ROWS ARE ALREADY RESOLVED (build_ledger_rows) before the
    final choice is made — the pass choice is decided by which one actually cited
    real text more often, not by schema validity alone. This is deliberate: a
    schema-valid-but-wildly-hallucinated recheck (fabricated paragraph numbers far
    past the document's real length, seen live on the Dallas corpus) must never
    silently outrank a primary pass whose citations mostly resolved.

    Returns (rows, pass_used, rechecked, errors) — pass_used is 1 (primary taken) or
    2 (recheck taken), stored in the ledger's "tier" field as extraction provenance."""
    errors: list[str] = []
    # Bluebonnet math PDFs often hang past 300s even under the chunk threshold
    # (Practice/Succeed SE). Use the large timeout for every decompose call;
    # Dallas-sized docs usually finish well under 300s anyway.
    call_timeout = LARGE_CALL_TIMEOUT_SECONDS
    primary, p_paragraphs = decompose_text(
        cfg,
        priors_block,
        text,
        char_label,
        f"{step_prefix}-pass1",
        timeout_seconds=call_timeout,
    )
    atomic_write(raw_dir / f"{step_prefix}-pass1.json", json.dumps(primary, indent=2))
    schema_errors = validate_layer0_elements(primary)
    if schema_errors:
        errors.append(f"primary schema: {'; '.join(schema_errors)}")
    primary_rows = build_ledger_rows(
        record,
        tier=1,
        chunked=bool(chunk_id),
        data=primary,
        paragraphs=p_paragraphs,
        chunk_id=chunk_id,
        errors=errors,
    )
    primary_uncited = _uncited_fraction(primary_rows)

    # "escalate_to_tier2" is the primary prompt's own uncertainty flag (kept under its
    # historical key in the schema); here it just means "the model wasn't sure — take
    # a second look," now with the same model rather than a stronger one.
    uncertain = (
        bool(schema_errors)
        or bool(primary.get("escalate_to_tier2"))
        or any(el.get("confidence") == "low" for el in primary.get("elements", []))
        or primary_uncited > UNCITED_ESCALATION_FRACTION
    )
    if not uncertain:
        return primary_rows, 1, False, errors

    try:
        recheck, r_paragraphs = recheck_text(
            cfg,
            priors_block,
            text,
            char_label,
            f"{step_prefix}-pass2",
            timeout_seconds=call_timeout,
        )
        atomic_write(
            raw_dir / f"{step_prefix}-pass2.json", json.dumps(recheck, indent=2)
        )
        recheck_errors = validate_layer0_elements(recheck)
        if recheck_errors:
            errors.append(f"recheck schema: {'; '.join(recheck_errors)}")
        # If the recheck came back schema-invalid but the primary was schema-valid,
        # keep the primary outright (never let an unparseable second pass discard a
        # good first one) — no citation comparison needed, there's nothing to compare.
        if recheck_errors and not schema_errors:
            errors.append("recheck schema-invalid; keeping primary output")
            chosen_rows, chosen_tier, chosen_uncited = primary_rows, 1, primary_uncited
        else:
            recheck_rows = build_ledger_rows(
                record,
                tier=2,
                chunked=bool(chunk_id),
                data=recheck,
                paragraphs=r_paragraphs,
                chunk_id=chunk_id,
                errors=errors,
            )
            recheck_uncited = _uncited_fraction(recheck_rows)
            # Both schema-valid (or both schema-invalid, nothing better to go on):
            # trust whichever pass actually cited real text more often. Ties favor
            # the recheck (preserves the original "trust the deeper read" default
            # when citation quality doesn't distinguish them).
            if recheck_uncited > primary_uncited:
                errors.append(
                    f"recheck cited less reliably than primary ({recheck_uncited:.0%} vs "
                    f"{primary_uncited:.0%} uncited) — keeping primary output"
                )
                chosen_rows, chosen_tier, chosen_uncited = (
                    primary_rows,
                    1,
                    primary_uncited,
                )
            else:
                chosen_rows, chosen_tier, chosen_uncited = (
                    recheck_rows,
                    2,
                    recheck_uncited,
                )

        if chosen_uncited > HIGH_UNCITED_FLAG_FRACTION:
            errors.append(
                f"high uncited rate even after best-of-two ({chosen_uncited:.0%} of "
                f"{len(chosen_rows)} elements) — citations for this span are unreliable, review by hand"
            )
        return chosen_rows, chosen_tier, True, errors
    except (RuntimeError, ValueError) as e:
        errors.append(f"recheck failed ({e}); keeping primary output")
        return primary_rows, 1, True, errors


def process_document_simple(
    cfg: dict, record: dict, raw_dir: Path
) -> tuple[list[dict], dict]:
    """Single-prompt path for documents within CHUNK_THRESHOLD_CHARS."""
    doc_id = record["doc_id"]
    stats = {
        "doc_id": doc_id,
        "source_file": record["source_file"],
        "tier_used": 1,
        "escalated": False,
        "errors": [],
        "chunks": 1,
    }
    priors_block = build_priors_block(record)
    char_label = f"{record['char_count_clean']} chars"
    rows, pass_used, rechecked, errors = _decompose_with_recheck(
        cfg,
        record,
        priors_block,
        record["content_clean"],
        char_label,
        doc_id,
        raw_dir,
        chunk_id=None,
    )
    stats.update(tier_used=pass_used, escalated=rechecked, errors=errors)
    return rows, stats


def _chunk_resolved_path(raw_dir: Path, step_prefix: str) -> Path:
    """Per-chunk resume cache: resolved ledger rows + content_hash for mid-doc resume."""
    return raw_dir / f"{step_prefix}-resolved-rows.json"


def _load_chunk_resume(
    raw_dir: Path, step_prefix: str, content_hash_value: str, chunk_id: str
) -> tuple[list[dict], int, bool, list[str]] | None:
    """Return cached (rows, pass_used, rechecked, errors) if hash+chunk match."""
    path = _chunk_resolved_path(raw_dir, step_prefix)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("content_hash") != content_hash_value or data.get("chunk_id") != chunk_id:
        return None
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    return (
        rows,
        int(data.get("pass_used") or 1),
        bool(data.get("rechecked")),
        list(data.get("errors") or []),
    )


def _save_chunk_resume(
    raw_dir: Path,
    step_prefix: str,
    content_hash_value: str,
    chunk_id: str,
    rows: list[dict],
    pass_used: int,
    rechecked: bool,
    errors: list[str],
) -> None:
    atomic_write(
        _chunk_resolved_path(raw_dir, step_prefix),
        json.dumps(
            {
                "content_hash": content_hash_value,
                "chunk_id": chunk_id,
                "pass_used": pass_used,
                "rechecked": rechecked,
                "errors": errors,
                "rows": rows,
            },
            indent=2,
        ),
    )


def process_document_chunked(
    cfg: dict, record: dict, raw_dir: Path
) -> tuple[list[dict], dict]:
    """Real map/reduce path for oversized documents (Bet 1): one Tier1/Tier2 call
    PER CHUNK, never one oversized prompt. See CHUNK_THRESHOLD_CHARS comment for why
    this replaced the earlier reassemble-into-one-prompt approach.

    Mid-chunk resume (Bluebonnet overnight): after each successful chunk, write
    ``.raw/{doc}-{chunk}-resolved-rows.json``. On restart with the same
    content_hash, skip model calls for chunks already resolved — crash on chunk
    4/6 must not redo 1–3.
    """
    doc_id = record["doc_id"]
    chash = content_hash(record["content_clean"])
    priors_block = build_priors_block(record)
    chunks = split_into_chunks(record["content_clean"])
    n = len(chunks)
    log(
        f"  {doc_id}: {record['char_count_clean']} chars > threshold, split into {n} chunks"
    )
    orientation = build_doc_orientation(record["content_clean"])

    all_rows: list[dict] = []
    chunks_escalated = 0
    chunks_resumed = 0
    all_errors: list[str] = []

    for idx, chunk_text in enumerate(chunks, start=1):
        chunk_id = f"chunk{idx}of{n}"
        step_prefix = f"{doc_id}-{chunk_id}"
        resumed = _load_chunk_resume(raw_dir, step_prefix, chash, chunk_id)
        if resumed is not None:
            rows, pass_used, rechecked, errors = resumed
            log(
                f"  cache hit  {doc_id} {chunk_id} "
                f"({len(rows)} elements, mid-chunk resume)"
            )
            chunks_resumed += 1
            if rechecked:
                chunks_escalated += 1
            all_errors.extend(f"{chunk_id}: {e}" for e in errors)
            all_errors.append(f"{chunk_id}: (chunk resume cache)")
            all_rows.extend(rows)
            continue

        chunk_note = (
            f"\nIMPORTANT: this is {chunk_id} of a larger document that was too big for a "
            f"single pass (Bet 1: chunked and reassembled, never truncated). Only decompose "
            f"content actually present in THIS chunk. Do not assume or invent content from "
            f"other chunks — a separate merge step handles the full document.\n"
            f"{orientation if idx > 1 else ''}"
        )
        char_label = f"{len(chunk_text)} chars, {chunk_id}"
        try:
            rows, pass_used, rechecked, errors = _decompose_with_recheck(
                cfg,
                record,
                priors_block,
                chunk_text,
                char_label,
                step_prefix,
                raw_dir,
                chunk_id=chunk_id,
            )
        except (RuntimeError, ValueError) as e:
            # One chunk's failure must not lose every other chunk's completed work
            # (Bet 6, applied at chunk granularity) — log it, skip this chunk, continue.
            log(f"ERROR: {doc_id} {chunk_id} failed, skipping this chunk only: {e}")
            all_errors.append(f"{chunk_id}: FAILED, skipped: {e}")
            continue
        _save_chunk_resume(
            raw_dir, step_prefix, chash, chunk_id, rows, pass_used, rechecked, errors
        )
        if rechecked:
            chunks_escalated += 1
        all_errors.extend(f"{chunk_id}: {e}" for e in errors)
        all_rows.extend(rows)

    # Reduce: dedup elements that appear twice due to paragraph overlap between
    # adjacent chunks (exact-match only — see dedup_elements docstring).
    before = len(all_rows)
    deduped = dedup_elements(all_rows)
    removed = before - len(deduped)
    if removed:
        log(
            f"  {doc_id}: reduce step removed {removed} duplicate element(s) from chunk overlap"
        )

    stats = {
        "doc_id": doc_id,
        "source_file": record["source_file"],
        "tier_used": "mixed",
        "escalated": chunks_escalated > 0,
        "errors": all_errors,
        "chunks": n,
        "chunks_escalated": chunks_escalated,
        "chunks_resumed": chunks_resumed,
        "duplicates_removed": removed,
    }
    return deduped, stats


def process_document(cfg: dict, record: dict, raw_dir: Path) -> tuple[list[dict], dict]:
    """Dispatch to the single-prompt or map/reduce path based on document size.

    If the single-prompt path parse-fails on a mid-size doc, fall back to forced
    chunking (Bluebonnet Learn/Succeed SE pattern) instead of dropping the file.
    """
    if needs_chunking(record):
        return process_document_chunked(cfg, record, raw_dir)
    try:
        return process_document_simple(cfg, record, raw_dir)
    except (RuntimeError, ValueError) as e:
        if record["char_count_clean"] < 8_000:
            raise
        log(
            f"  {record['doc_id']}: simple path failed ({e}); "
            f"falling back to forced chunking"
        )
        return process_document_chunked(cfg, record, raw_dir)


# --- Layer 0-B: citation-precision review for excerpt_wide_span rows --------
# The item #10 range redesign (docs/roadmap.md) fixed silent mid-span skipping
# by construction, but relocated rather than eliminated the underlying weakness
# (the model isn't always finding clean element boundaries): it now sometimes
# widens a range to sweep in several genuinely distinct elements instead of
# narrowly skipping the middle of one. `excerpt_wide_span` (span >
# WIDE_SPAN_PARAGRAPHS) already flags every such case for free, with no fuzzy
# semantic judgment needed to notice it (unlike the old silent-skip problem).
# Layer 0-B is the narrow, cheap follow-up that spends a model call ONLY on
# that flagged ~10% of rows — never the whole corpus — to decide whether each
# wide span is genuinely one element or should split into several.
LAYER0B_RULES = """You are a curriculum audit Verifier performing a Layer 0-B citation-precision
review. READ-ONLY.

An earlier decompose pass produced ONE instructional element citing a WIDE paragraph
span as evidence for a single element of type "{element_type}". A wide span is
SOMETIMES correct (one long contiguous activity or task description) but is also a
known failure mode: a model merging several genuinely DISTINCT elements (e.g. several
separate lesson-plan rows, or several unrelated facts) into one citation just because
they sit close together in the document.

Read ONLY the paragraphs below (already exactly the flagged span, nothing outside it)
and decide:
- "keep": this genuinely is ONE coherent instructional element; the wide span is
  correct as written.
- "split": these paragraphs actually contain MULTIPLE distinct instructional elements
  that were wrongly merged into one citation.

RULES (mandatory):
- If "split": every new element's excerpt_start_paragraph/excerpt_end_paragraph MUST
  fall within the original flagged range (you cannot cite outside what you were
  shown). Assign every paragraph in the flagged range to whichever new element it
  actually belongs to — a connective/heading paragraph can join whichever neighbor
  it introduces — but never invent a gap: every paragraph number in the original
  range must end up inside exactly one of your new elements' start-end spans.
- Classify each split element by UNIVERSAL INSTRUCTIONAL FUNCTION (same taxonomy as
  the original pass): hook_engagement, direct_instruction, guided_practice,
  independent_practice, assessment_checkpoint, reflection_closure,
  logistics_materials, standards_objectives, or unclear.
- NEVER write, invent, or suggest curriculum content. You are an auditor, not an author.
"""

LAYER0B_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "decision": "keep|split",
  "elements": [
    {
      "element_type": "hook_engagement|direct_instruction|guided_practice|independent_practice|assessment_checkpoint|reflection_closure|logistics_materials|standards_objectives|unclear",
      "excerpt_start_paragraph": <plain integer, within the original flagged range>,
      "excerpt_end_paragraph": <plain integer, within the original flagged range>,
      "inferred_position": "<e.g. 'Day 2', 'early in unit', or 'unknown'>",
      "inferred_timing": "<e.g. '10-15 minutes', or 'unknown'>",
      "confidence": "high|medium|low"
    }
  ],
  "reasoning": "<one sentence: why keep, or why split this particular way>"
}
If "decision" is "keep", "elements" MUST be an empty list []. If "decision" is
"split", "elements" MUST contain 2 or more entries covering the full original range."""


def get_paragraphs_for_row(record: dict, chunk_id: str | None) -> list[str]:
    """Reconstruct the exact numbered paragraph list a ledger row's citation was
    resolved against, so Layer 0-B can re-examine a flagged span later (a separate
    run, not held in memory from the original decompose pass). Whole-document rows
    (chunk_id=None) just re-number the full clean text; chunked rows must
    regenerate the SAME chunk boundaries via split_into_chunks() — deterministic
    given the same content_clean — and re-number that one chunk, since paragraph
    numbers are chunk-relative, not document-relative, on the chunked path.
    """
    if not chunk_id:
        _, paragraphs = number_paragraphs(record["content_clean"])
        return paragraphs
    chunks = split_into_chunks(record["content_clean"])
    idx = int(chunk_id[len("chunk") :].split("of")[0])
    if idx < 1 or idx > len(chunks):
        raise ValueError(
            f"chunk_id {chunk_id!r} out of range for {len(chunks)} reconstructed chunks"
        )
    _, paragraphs = number_paragraphs(chunks[idx - 1])
    return paragraphs


def _clamp_span(start: int, end: int, n: int) -> tuple[int, int]:
    """Clamp a 1-based inclusive paragraph span to [1, n]. Returns (0, 0) when
    there is nothing to show (no paragraphs, or the whole span sits past the end).

    Why this exists: a stored wide-span row can cite paragraph indices beyond what
    its chunk reconstructs to (upstream re-chunking can change paragraph counts on
    unusual documents — the AP-CSP CED is one). Without clamping, indexing the
    paragraph list raised IndexError and killed the entire run. We degrade to the
    paragraphs we actually have instead."""
    if n <= 0:
        return (0, 0)
    lo = max(1, int(start))
    hi = min(int(end), n)
    if lo > n or hi < lo:
        # Span begins past the last paragraph (or is degenerate) — no overlap.
        return (0, 0)
    return (lo, hi)


def build_flagged_span_text(paragraphs: list[str], start: int, end: int) -> str:
    lo, hi = _clamp_span(start, end, len(paragraphs))
    if lo == 0:
        return ""
    return "\n\n".join(f"[P{i}] {paragraphs[i - 1]}" for i in range(lo, hi + 1))


def resolve_wide_span(cfg: dict, row: dict, paragraphs: list[str]) -> dict:
    start, end = row["excerpt_start_paragraph"], row["excerpt_end_paragraph"]
    lo, hi = _clamp_span(start, end, len(paragraphs))
    if lo == 0:
        # The cited span is entirely outside the reconstructed chunk — there is
        # nothing safe to show the model, so keep the element as-is rather than
        # crash or invite a hallucinated split on absent text.
        return {
            "decision": "keep",
            "reasoning": (
                f"cited span {start}-{end} falls outside the "
                f"{len(paragraphs)} reconstructed paragraph(s); kept unchanged"
            ),
        }
    span_text = build_flagged_span_text(paragraphs, lo, hi)
    rules = LAYER0B_RULES.format(element_type=row["element_type"])
    prompt = f"""{rules}
Original citation: paragraphs {lo}-{hi} ({hi - lo + 1} paragraphs), element_type={row['element_type']!r}

FLAGGED SPAN TEXT (numbered paragraphs {lo}-{hi} only — nothing outside this range
is shown, because nothing outside it may be cited):
{span_text}

{LAYER0B_SCHEMA}
"""
    step = f"{row['element_id']}-layer0b"
    resp = model_chat(
        cfg,
        "verifier",
        [{"role": "user", "content": prompt}],
        step,
        temperature=0.1,
        max_tokens=16384,
    )
    return parse_model_json(extract_content(resp), context=step)


def coerce_element_type(raw: object, element_id: str, errors: list[str]) -> str:
    """Enforce the closed element_type enum (ELEMENT_TYPES) on a Layer 0-B split
    element the same way the Tier 1/Tier 2 decompose path already does via
    validate_layer0_elements() — this path had been skipping that check entirely,
    which is how compound values like "hook_engagement|direct_instruction" (the
    model echoing the pipe-delimited enum LIST from LAYER0B_SCHEMA back as if it
    were itself a value, instead of picking one member) were reaching the ledger
    unvalidated. Falls back to "unclear" rather than raising: Bet 4 already treats
    "unclear" as a first-class valid answer for insufficient classification
    confidence, and one bad sub-element out of a multi-element split shouldn't
    discard the whole split (the OTHER new elements' citations are still real,
    resolved pointers — see the "Citation mechanism" comment above).

    Before coercing, we first NORMALIZE: the model very often tags elements with
    5E phase names (explore_activity, evaluate_activity, …) or compound values;
    normalize_element_type() maps those onto the canonical enum so they are kept
    as the real component type instead of being flattened to 'unclear' (which was
    silently starving the rubrics of the guided-practice / assessment elements
    that were actually present).
    """
    if raw in ELEMENT_TYPES:
        return raw  # type: ignore[return-value]
    normalized = normalize_element_type(raw)
    if normalized is not None:
        log(f"  note: element_type {raw!r} normalized to {normalized!r}")
        return normalized
    msg = f"{element_id}: invalid element_type {raw!r} — coerced to 'unclear'"
    log(f"  WARN: {msg}")
    errors.append(msg)
    return "unclear"


def run_layer0b(project_id: str) -> Path:
    """Layer 0-B pass: re-examine only the excerpt_wide_span=True rows of an
    already-built ledger and split any that turn out to be multiple distinct
    elements wrongly merged into one wide citation. Never touches the other
    ~90% of the corpus — see the module comment above LAYER0B_RULES for why
    that's sufficient (excerpt_wide_span already isolates every candidate)."""
    root = project_dir(project_id)
    l0_dir = root / "layer0"
    ledger_path = l0_dir / "ledger.json"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"no ledger at {ledger_path} — run Layer 0 first")
    rows: list[dict] = json.loads(ledger_path.read_text())

    cfg = load_config()
    sources = root / "sources"
    source_paths = (
        {p.name: p for p in iter_source_files(sources)} if sources.is_dir() else {}
    )

    doc_records: dict[str, dict] = {}
    para_cache: dict[tuple[str, str | None], list[str]] = {}

    def get_paragraphs(row: dict) -> list[str]:
        doc_id = row["doc_id"]
        key = (doc_id, row.get("chunk_id"))
        if key in para_cache:
            return para_cache[key]
        if doc_id not in doc_records:
            path = source_paths.get(row["source_file"])
            if not path:
                raise FileNotFoundError(
                    f"source file not found for {doc_id}: {row['source_file']}"
                )
            doc_records[doc_id] = scrub_document(path)
        paragraphs = get_paragraphs_for_row(doc_records[doc_id], row.get("chunk_id"))
        para_cache[key] = paragraphs
        return paragraphs

    flagged = [r for r in rows if r.get("excerpt_wide_span")]
    log(
        f"Layer 0-B: {len(flagged)} wide_span element(s) to review out of {len(rows)} total"
    )

    new_rows: list[dict] = []
    kept = 0
    split_count = 0
    errors: list[str] = []
    type_coercions: list[str] = []

    for row in rows:
        if not row.get("excerpt_wide_span"):
            new_rows.append(row)
            continue

        try:
            paragraphs = get_paragraphs(row)
            result = resolve_wide_span(cfg, row, paragraphs)
        except (RuntimeError, ValueError, FileNotFoundError, IndexError) as e:
            log(
                f"  WARN: {row['element_id']} Layer 0-B review failed, leaving as-is: {e}"
            )
            errors.append(f"{row['element_id']}: {e}")
            new_rows.append(row)
            continue

        proposed = result.get("elements") or []
        if result.get("decision") != "split" or len(proposed) < 2:
            kept += 1
            new_rows.append(
                {**row, "layer0b_reviewed": True, "layer0b_decision": "keep"}
            )
            log(f"  keep   {row['element_id']} ({result.get('reasoning', '')[:100]})")
            continue

        split_count += 1
        record = doc_records[row["doc_id"]]
        log(
            f"  split  {row['element_id']} -> {len(proposed)} elements ({result.get('reasoning', '')[:100]})"
        )
        for i, el in enumerate(proposed, start=1):
            excerpt, valid, wide_span = resolve_excerpt(
                paragraphs,
                el.get("excerpt_start_paragraph"),
                el.get("excerpt_end_paragraph"),
            )
            etype = coerce_element_type(
                el.get("element_type"), row["element_id"], type_coercions
            )
            new_rows.append(
                {
                    **row,
                    "element_id": f"{row['element_id']}-split{i}",
                    "element_type": etype,
                    "excerpt": excerpt,
                    "excerpt_start_paragraph": el.get("excerpt_start_paragraph"),
                    "excerpt_end_paragraph": el.get("excerpt_end_paragraph"),
                    "cited": valid,
                    "excerpt_wide_span": wide_span,
                    "excerpt_sanity_check_passed": (
                        excerpt_cited_in(excerpt, record["content_clean"])
                        if valid
                        else None
                    ),
                    "inferred_position": el.get("inferred_position"),
                    "inferred_timing": el.get("inferred_timing"),
                    "confidence": el.get("confidence"),
                    "layer0b_reviewed": True,
                    "layer0b_decision": "split",
                    "layer0b_split_from": row["element_id"],
                }
            )

    atomic_write(ledger_path, json.dumps(new_rows, indent=2))

    report = f"""# Layer 0-B Report (citation-precision review)

**Project:** {project_id}
**Wide-span elements reviewed:** {len(flagged)}
**Kept as-is (genuinely one element):** {kept}
**Split into multiple elements:** {split_count}
**Review errors (left unchanged, still flagged):** {len(errors)}
**element_type coerced to 'unclear' (model returned an invalid/compound value):** {len(type_coercions)}
**Elements in ledger before:** {len(rows)}
**Elements in ledger after:** {len(new_rows)}

## Errors
{chr(10).join(f"- {e}" for e in errors) if errors else "- None"}

## element_type coercions
{chr(10).join(f"- {e}" for e in type_coercions) if type_coercions else "- None"}
"""
    atomic_write(l0_dir / "LAYER0B-REPORT.md", report)
    log(
        f"Layer 0-B done: {kept} kept, {split_count} split into "
        f"{sum(1 for r in new_rows if r.get('layer0b_decision') == 'split')} new elements, "
        f"{len(errors)} errors, {len(type_coercions)} type coercions -> {l0_dir}"
    )
    return l0_dir


def load_existing_ledger(ledger_path: Path) -> dict[str, list[dict]]:
    """doc_id -> rows, for resumability (Bet 6): reuse rows whose content_hash matches."""
    if not ledger_path.is_file():
        return {}
    rows = json.loads(ledger_path.read_text())
    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        by_doc.setdefault(r["doc_id"], []).append(r)
    return by_doc


def build_ledger_md(rows: list[dict], run_stats: list[dict]) -> str:
    lines = [
        "# Layer 0 Evidence Ledger",
        "",
        f"**Documents processed:** {len(run_stats)}  ",
        f"**Elements extracted:** {len(rows)}  ",
        f"**Second-pass rechecks:** {sum(1 for s in run_stats if s['escalated'])}  ",
        f"**Uncited excerpts:** {sum(1 for r in rows if not r['cited'])}  ",
        "",
        "| element_id | doc_id | type | pass | position | timing | confidence | cited |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        flag = "" if r["cited"] else "⚠"
        lines.append(
            f"| {r['element_id']} | {r['doc_id']} | {r['element_type']} | {r['tier']} | "
            f"{r['inferred_position']} | {r['inferred_timing']} | {r['confidence']} | {flag} |"
        )
    lines.extend(["", "## Per-document notes", ""])
    for s in run_stats:
        chunk_note = (
            f", chunks={s['chunks']} ({s.get('chunks_escalated', 0)} rechecked)"
            if s.get("chunks", 1) > 1
            else ""
        )
        if s["errors"] or s["escalated"] or s.get("chunks", 1) > 1:
            lines.append(
                f"- `{s['doc_id']}` ({s['source_file']}): pass_used={s['tier_used']}, rechecked={s['escalated']}{chunk_note}"
            )
            for e in s["errors"]:
                lines.append(f"  - {e}")
    return "\n".join(lines) + "\n"


def run_layer0(
    project_id: str,
    sources: Path,
    limit: int | None = None,
    only: str | None = None,
    resume: bool = True,
) -> Path:
    root = project_dir(project_id)
    l0_dir = root / "layer0"
    raw_dir = l0_dir / ".raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    paths = iter_source_files(sources)
    if only:
        paths = [p for p in paths if only.lower() in p.name.lower()]
    if not paths:
        raise FileNotFoundError(f"No source files matched in {sources} (only={only!r})")
    if limit:
        paths = paths[:limit]

    ledger_path = l0_dir / "ledger.json"
    # Loaded UNCONDITIONALLY (not gated on `resume`) — this feeds carry_forward
    # below, which must protect untouched documents regardless of whether THIS
    # run is doing cache-hit resumption. `resume` only controls the separate
    # question of whether an unchanged touched document gets reprocessed
    # (cache-hit skip via content_hash, see the loop below).
    all_existing = load_existing_ledger(ledger_path)
    existing = all_existing if resume else {}
    # --only/--limit restrict which files THIS run touches, for quick targeted
    # tests/fixes — they must never mean "everything else drops out of the
    # ledger." Confirmed live (2026-07-07): re-running with --only to fix one
    # hung document on a 19-document corpus overwrote the ledger down to that
    # one document's 19 rows, silently discarding the other 18 already-good
    # documents' 311 rows. Confirmed AGAIN live (2026-07-08): the first fix for
    # this only read carry-forward source data from `existing`, which is itself
    # forced empty by `--no-resume` — so `--only X --no-resume` together (a
    # completely reasonable combo: "force-refresh doc X, ignore its own cache")
    # silently reintroduced the exact same data-loss bug this comment is about.
    # Carry-forward must be computed from `all_existing` (always loaded),
    # never from `existing` (conditionally emptied by --no-resume), because
    # "should X itself be cache-skipped" and "should every OTHER document's
    # evidence survive this run" are two different questions that must not
    # share one variable. `touched_doc_ids` is the set of doc_ids this run will
    # cover (cheap: doc_id is derived from filename alone, no extraction needed);
    # anything in the old ledger outside that set is carried forward untouched at
    # every checkpoint below, so a filtered run can only ever add/update rows,
    # never silently delete other documents' evidence. When neither flag is set,
    # `paths` already covers every file in `sources`, so nothing needs carrying.
    carry_forward: list[dict] = []
    if only or limit:
        touched_doc_ids = {doc_id_from_filename(p.name) for p in paths}
        carry_forward = [
            row
            for doc_id_, rows_ in all_existing.items()
            if doc_id_ not in touched_doc_ids
            for row in rows_
        ]

    cfg = load_config()
    all_rows: list[dict] = []
    run_stats: list[dict] = []
    skipped_extraction = []

    for p in paths:
        record = scrub_document(p)
        if record.get("extraction_error"):
            skipped_extraction.append(f"{p.name}: {record['extraction_error']}")
            continue
        doc_id = record["doc_id"]
        chash = content_hash(record["content_clean"])

        cached_rows = existing.get(doc_id)
        if resume and cached_rows and cached_rows[0].get("content_hash") == chash:
            log(f"cache hit  {p.name} ({len(cached_rows)} elements, unchanged)")
            all_rows.extend(cached_rows)
            run_stats.append(
                {
                    "doc_id": doc_id,
                    "source_file": record["source_file"],
                    "tier_used": cached_rows[0].get("tier"),
                    "escalated": False,
                    "errors": ["(cached, not re-run)"],
                }
            )
            continue

        log(f"Layer 0: decomposing {p.name} ({record['char_count_clean']} chars)...")
        try:
            rows, stats = process_document(cfg, record, raw_dir)
        except (RuntimeError, ValueError) as e:
            log(f"ERROR: {p.name}: {e}")
            run_stats.append(
                {
                    "doc_id": doc_id,
                    "source_file": record["source_file"],
                    "tier_used": 0,
                    "escalated": False,
                    "errors": [str(e)],
                }
            )
            continue

        chunk_info = (
            f", {stats['chunks']} chunks ({stats.get('chunks_escalated', 0)} rechecked"
            + (
                f", {stats.get('chunks_resumed', 0)} resumed"
                if stats.get("chunks_resumed")
                else ""
            )
            + ")"
            if stats.get("chunks", 1) > 1
            else ""
        )
        log(
            f"  -> {len(rows)} elements, pass {stats['tier_used']}"
            + (" (rechecked)" if stats["escalated"] else "")
            + chunk_info
            + (f", {sum(1 for r in rows if not r['cited'])} uncited" if rows else "")
        )
        all_rows.extend(rows)
        run_stats.append(stats)

        # Checkpoint after every document (Bet 6): a crash/interruption mid-run
        # must not lose already-completed work. atomic_write means the file is
        # always either the previous complete state or the new one, never partial.
        # carry_forward (computed once, above) is empty unless --only/--limit was
        # used, so this is a no-op for a normal full-corpus run.
        atomic_write(ledger_path, json.dumps(all_rows + carry_forward, indent=2))

    all_rows = all_rows + carry_forward

    # Authoritative final ledger write. The in-loop checkpoint (above) only fires
    # AFTER a fresh decompose — cache-hit documents `continue` before reaching it.
    # So on a mostly-cached run, the last checkpoint reflects only the rows
    # accumulated up to the final *fresh* decompose, and every cache hit after it
    # grows `all_rows` in memory but is never persisted. That silently truncated
    # ledger.json (e.g. 1126 elements in memory / REPORT.md, but only ~40 on disk)
    # whenever the last fresh doc sorted before the last cache hit. ledger.md and
    # REPORT.md were unaffected because they are written here, post-loop, from the
    # complete in-memory `all_rows` — which is exactly why the counts disagreed.
    # Writing the full ledger once here guarantees ledger.json always matches the
    # in-memory result regardless of cache-hit ordering.
    atomic_write(ledger_path, json.dumps(all_rows, indent=2))

    atomic_write(l0_dir / "ledger.md", build_ledger_md(all_rows, run_stats))

    uncited = sum(1 for r in all_rows if not r["cited"])
    escalated = sum(1 for s in run_stats if s["escalated"])
    errored = sum(
        1
        for s in run_stats
        if s["errors"] and "(cached, not re-run)" not in s["errors"]
    )
    report = f"""# Layer 0 Report

**Status:** {"SUCCESS" if all_rows else "FAILED"}
**Project:** {project_id}
**Documents scanned:** {len(paths)}
**Documents extracted OK:** {len(run_stats)}
**Documents failed extraction (skipped):** {len(skipped_extraction)}
**Elements in ledger:** {len(all_rows)}
**Second-pass rechecks:** {escalated}
**Documents with schema/model errors:** {errored}
**Uncited excerpts (flagged, not dropped):** {uncited}

## Extraction failures
{chr(10).join(f"- {s}" for s in skipped_extraction) if skipped_extraction else "- None"}

## Artifacts
- `ledger.json` — the shared evidence ledger (one row per element)
- `ledger.md` — human-readable ledger + per-document notes
- `.raw/<doc_id>-pass1.json`, `.raw/<doc_id>-pass2.json` — raw model responses
- `.raw/<doc_id>-chunk<N>of<M>-pass1.json`, `-pass2.json` — oversized docs (map/reduce)
- `.raw/<doc_id>-chunk<N>of<M>-resolved-rows.json` — mid-chunk resume cache (same content_hash)
"""
    atomic_write(l0_dir / "REPORT.md", report)
    log(
        f"Layer 0 done: {len(all_rows)} elements from {len(run_stats)} documents -> {l0_dir}"
    )
    return l0_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 0: decompose documents into a shared evidence ledger"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--sources",
        type=Path,
        help="Folder of curriculum files (defaults to projects/<id>/sources)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N matched files (for quick tests)",
    )
    parser.add_argument(
        "--only", help="Only process files whose name contains this substring"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing ledger cache, reprocess everything",
    )
    parser.add_argument(
        "--resolve-wide-spans",
        action="store_true",
        help="Layer 0-B: review an EXISTING ledger's excerpt_wide_span rows only, splitting "
        "any that are multiple elements wrongly merged into one wide citation. Does not "
        "re-run extraction/decompose; --sources/--limit/--only/--no-resume are ignored.",
    )
    args = parser.parse_args()

    try:
        validate_slug_id(args.project, "project id")
        if args.resolve_wide_spans:
            run_layer0b(args.project)
            return 0

        sources = args.sources or (project_dir(args.project) / "sources")
        if not sources.is_dir():
            log(f"ERROR: sources not found: {sources}")
            return 2
        run_layer0(
            args.project,
            sources,
            limit=args.limit,
            only=args.only,
            resume=not args.no_resume,
        )
    except ValueError as e:
        log(f"ERROR: {e}")
        return 2
    except (KeyError, FileNotFoundError, RuntimeError) as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
