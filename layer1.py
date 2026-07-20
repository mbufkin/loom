#!/usr/bin/env python3
"""
layer1.py — Layer 1: Sort / Bucket / Place.

See docs/BETS.md (Bet 11) and docs/roadmap.md "Layer 1" for the full design and
research this implements. Minimal first build — validated on one small,
already-known unit before any full-corpus run (see roadmap.md's Definition of
Done for Layer 1).

Reads the Layer 0 ledger (element-level, already-cited evidence) and determines
where each element actually belongs, checked against the manifest's own declared
structure — the missing join between "we have 500 cited facts" and "the
GLOBAL-AUDIT-REPORT.pdf actually uses them correctly" (Bet 7).

Three deliberately separate phases (see Bet 11 for why they must not blend):

PHASE 1 ORGANIZE (model, per document, content-only):
  Given one document's elements and the project's CLOSED unit/day vocabulary —
  never which unit THIS document was assigned to — the model independently
  judges whether each element's own text self-identifies with a specific
  unit/day. Resolves to a clean ID from the closed menu, not free text, so
  Phase 2 can compare with true equality instead of fuzzy string-matching.

PHASE 2 CHECK (pure code, zero model calls):
  Join Phase 1's self-declared unit against manifest.yaml's parent-link
  assignment for that document. Set comparison only, never judgment:
  MATCH / MISMATCH / ORPHAN / UNVERIFIED (no self-declaration to compare).

PHASE 3 FULFILL (model, narrow, per day-slot):
  For each unit-day's expected artifact-kind roles, check whether any element
  routed into that slot (by Phase 2) actually functions as that role. A slot
  with no fulfilling element is MISSING. No static mapping table between Layer
  0's element_type taxonomy and the calendar's artifact-kind roles (Bet 0
  correction, see Bet 11) — spend a cheap, narrow, cited model call instead.

Auditor-only: places existing evidence into buckets; never invents or fixes content.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from audit_lib import (
    CONCENTRATION_MIN_COUNT,
    atomic_write,
    doc_id_from_filename,
    is_corroborated,
    load_config,
    load_manifest,
    load_unit_calendar,
    log,
    model_chat,
    normalize_ws,
    parse_model_json,
    project_dir,
    validate_slug_id,
)
from schema_validate import (
    CONFIDENCE_LEVELS,
    raise_on_errors,
    validate_layer1_fulfillment,
    validate_layer1_placements,
)

UNIT_SUPPORTING_SLOT = (
    "unit_supporting"  # pseudo-day-id for calendar.yaml's unit_supporting list
)

# Phase 1 ORGANIZE batch ceiling (roadmap §13 / Bluebonnet validation).
# One call per source file is correct for Dallas-shaped packs (~tens of
# elements) and wrong for TE/CED-sized ledgers (195–507 elements): the model
# either times out, emits truncated JSON, or overflows context. Split above
# this size into independent batches with the same closed vocab, merge by
# element_id; one batch fail must not discard the others (Layer 0 chunk
# isolation discipline).
ORGANIZE_BATCH_SIZE = 40

# Longer wall-clock for multi-element ORGANIZE batches (and Layer 0 chunks via
# the same constant). Global config stays at 300s for small calls.
LARGE_CALL_TIMEOUT_SECONDS = 900


def model_call(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    # 16384, not 8192: Phase 1 batches a whole document's elements and Phase 3
    # batches a whole day-slot's candidates into one JSON response — the same
    # content-dense-output shape that hit layer0.py's old 8192 ceiling and caused
    # deterministic "Expecting ',' delimiter" parse failures (see docs/roadmap.md,
    # "max_tokens ceiling"). Reusing the lower value here would just reintroduce
    # a bug this project already paid to find and fix once.
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


# Map the confidence tokens a model actually emits (which drift once you swap the
# underlying model — Nemotron-3, for one, likes "placeholder"/"n/a" on empty slots
# and "very high"/"certain" when emphatic) onto the closed high|medium|low enum the
# schema requires. Unknown/empty -> "low" is the conservative choice: it means "we
# do not assert this role is fulfilled", which is exactly the safe reading when the
# model gave us a word we don't recognize. This keeps one stray enum token from
# discarding an otherwise-good multi-role Phase 3 judgment (the CHECK_FAILED class of
# regressions we saw on the model swap), while never *upgrading* a weak claim.
_CONFIDENCE_SYNONYMS = {
    "very high": "high",
    "certain": "high",
    "strong": "high",
    "moderate": "medium",
    "med": "medium",
    "partial": "medium",
    "very low": "low",
    "weak": "low",
    "none": "low",
    "n/a": "low",
    "na": "low",
    "placeholder": "low",
    "unknown": "low",
    "unsure": "low",
}


def normalize_confidence(value: object) -> str:
    """Coerce a model's confidence token to the high|medium|low enum (see comment
    above for why). Anything unrecognized becomes 'low'."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in CONFIDENCE_LEVELS:
            return v
        if v in _CONFIDENCE_SYNONYMS:
            return _CONFIDENCE_SYNONYMS[v]
    return "low"


_CANDIDATE_PREFIX_RE = re.compile(r"^\s*candidate\s+", re.IGNORECASE)


def _clean_element_id(eid: object) -> str:
    """Strip a leading 'CANDIDATE ' label the model sometimes echoes verbatim into
    fulfilled_by. build_phase3_prompt()'s candidate block literally reads
    'CANDIDATE <element_id> (Layer 0 type: ...): "..."' — on a live run the model
    occasionally copies that whole label into fulfilled_by instead of just the id
    (confirmed on dallas-career-2026/financial-literacy, Day 3 exit_ticket:
    fulfilled_by came back as ["CANDIDATE 54aff8cc2360-e12"]). An uncleaned id like
    that matches nothing in bucket_rows_by_id, which silently breaks TWO things
    downstream: is_true_duplicate()'s root lookup fails to find the row and treats
    the empty result as 0 roots < 1 item -> a real FULFILLED slot is mis-scored as
    DUPLICATE; and the fulfills_role/fulfillment_confidence backfill onto the
    bucket-ledger row never happens for that element. Fixing the id at the source
    (here, before either consumer runs) fixes both."""
    return _CANDIDATE_PREFIX_RE.sub("", str(eid)).strip()


def _normalize_fulfillment(data: dict) -> None:
    """In-place normalizer for a Phase 3 payload: fix each role_fulfillment entry's
    confidence to the enum before the schema validator runs, so benign token drift
    doesn't nuke the whole slot's worth of judgments. Also cleans fulfilled_by ids
    (see _clean_element_id) for the same reason."""
    entries = data.get("role_fulfillment")
    if isinstance(entries, list):
        for f in entries:
            if isinstance(f, dict) and "confidence" in f:
                f["confidence"] = normalize_confidence(f.get("confidence"))
            if isinstance(f, dict) and isinstance(f.get("fulfilled_by"), list):
                f["fulfilled_by"] = [
                    _clean_element_id(e) for e in f["fulfilled_by"]
                ]


def call_and_parse_with_retry(
    cfg: dict,
    role: str,
    prompt: str,
    step: str,
    raw_path: Path | None = None,
    parse_retries: int = 1,
    validator=None,
    normalizer=None,
    timeout_seconds: float | None = None,
) -> dict:
    """Call a model and parse its JSON, retrying on PARSE *or schema* failure (not
    just the transient HTTP/connection retry model_chat() already does). Same
    rationale as layer0.py's _decompose_text_with_retry(): a 200 OK response that
    comes back truncated, malformed, or structurally wrong mid-generation is a
    distinct failure mode that a single attempt cannot distinguish from "the model
    was simply wrong" — one flaky generation should not permanently drop a
    document's worth of judgments.

    validator, if given, is one of schema_validate.py's validate_layer1_* functions
    (list[str] of errors, empty = valid) — treated as part of "did this attempt
    succeed", same as layer0.py's raise_on_errors(validate_layer0_elements(...))
    gate before trusting a decompose response.

    If raw_path is given, the LAST attempt's raw response is saved there (matches
    layer0.py's .raw/ debugging convention) — earlier failed attempts are only
    logged, not kept, since they're by definition not what the ledger used.
    """
    last_err: Exception | None = None
    resp: dict = {}
    for attempt in range(parse_retries + 1):
        resp = model_call(
            cfg,
            role,
            [{"role": "user", "content": prompt}],
            step,
            timeout_seconds=timeout_seconds,
        )
        try:
            data = parse_model_json(extract_content(resp), context=step)
            if normalizer is not None:
                normalizer(data)
            if validator is not None:
                raise_on_errors(validator(data), step)
            if raw_path is not None:
                raw_path.write_text(json.dumps(resp, indent=2))
            return data
        except ValueError as e:
            last_err = e
            if attempt < parse_retries:
                log(
                    f"WARN: {step} parse/schema failure (attempt {attempt + 1}), retrying: {e}"
                )
    if raw_path is not None:
        raw_path.write_text(json.dumps(resp, indent=2))
    raise ValueError(
        f"{step}: parse/schema failed after {parse_retries + 1} attempts: {last_err}"
    )


def _organize_element_batches(
    elements: list[dict], batch_size: int = ORGANIZE_BATCH_SIZE
) -> list[list[dict]]:
    """Split a document's elements into ORGANIZE prompt batches.

    Educational note: keep batch boundaries contiguous in ledger order so
    near-neighbor elements (same lesson section) stay in one prompt — that
    preserves the "concept clustering" consistency Bet 11 wanted from
    per-document batching, just at a size the model can finish.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if not elements:
        return []
    return [
        elements[i : i + batch_size] for i in range(0, len(elements), batch_size)
    ]


# --- Load Layer 0 + manifest + calendars -------------------------------------


def load_ledger(project_id: str) -> list[dict]:
    path = project_dir(project_id) / "layer0" / "ledger.json"
    if not path.is_file():
        raise FileNotFoundError(f"No Layer 0 ledger at {path} — run layer0.py first")
    return json.loads(path.read_text())


def build_parent_link_map(manifest: dict) -> dict[str, str]:
    """doc_id -> unit_id, derived the same way Layer 0 derives doc_id from filename
    (basename, strip extension / doc_ hash prefix). This is the ONE place the
    manifest's "answer" lives — Phase 1 must never see this map."""
    mapping: dict[str, str] = {}
    for unit_id, unit in manifest["units"].items():
        for doc_path in unit.get("documents", unit.get("source_files", [])):
            mapping[doc_id_from_filename(doc_path)] = unit_id
    return mapping


def build_unit_vocab(manifest: dict) -> list[dict]:
    """Closed vocabulary of every unit in the project: id + title. Shown to Phase 1
    as a multiple-choice menu (same safe pattern as Tier 1's closed element_type
    list) — never as "here's which unit YOUR document is filed under."."""
    return [
        {"unit_id": uid, "title": u.get("title", uid)}
        for uid, u in manifest["units"].items()
    ]


def build_overview_unit_set(manifest: dict) -> set[str]:
    """Unit ids tagged `kind: overview` in manifest.yaml — hub/survey units whose
    own documents exist to introduce and cross-reference every OTHER unit (e.g. a
    "Career Clusters" slide deck, a district-wide "High School Options" overview),
    as opposed to content units that actually deliver one subject's lessons.

    Found live on the Dallas corpus (docs/BETS.md Bet 12): treating every unit the
    same in Phase 2's equality check meant a hub document's own element correctly
    naming a specific unit ("Agriculture, Food & Natural Resources") was flagged
    MISMATCH — which isn't a filing error, it's the hub doing its job. This is the
    same "ontological class overlap" Northcutt et al.'s Confident Learning paper
    describes for parent/child classes (their example: ImageNet "missile" images
    mislabeled as parent class "projectile") — some class pairs are structurally
    more confusable than others and need a class-aware rule, not a flat one.
    Never used as a hint for Phase 1 (Bet 11) — only Phase 2's pure-code check
    reads this."""
    return {uid for uid, u in manifest["units"].items() if u.get("kind") == "overview"}


def build_known_overlap_set(manifest: dict) -> set[frozenset]:
    """Human-confirmed pairs of unit ids that legitimately, expectedly overlap —
    e.g. `[architecture-construction, engineering]` after a human reviewer
    confirmed a "STEM Tallest Paper Tower" activity inside an Architecture &
    Construction lesson plan is on-topic (Texas CTE's own Architecture &
    Construction TEKS explicitly include engineering design methodologies), not a
    filing error.

    Corroboration count alone (CONCENTRATION_MIN_COUNT/FRACTION) cannot tell this
    apart from a genuine misfile — both look identically "concentrated" whether a
    document's own elements agree because it's ACTUALLY about the other unit
    (wrong filing) or because it's teaching an adjacent discipline's skill that
    genuinely belongs alongside its own unit's content (expected overlap).
    Distinguishing them requires curriculum domain knowledge a model reading the
    excerpt alone does not have and should not guess at — a human reviewer
    (see `layer1/REVIEW-QUEUE.md`) makes this call once per unit-pair, and it's
    captured here so it's never re-litigated document-by-document on future runs.
    Read as unordered pairs (frozenset) since "A overlaps B" and "B overlaps A"
    are the same fact. Same never-shown-to-Phase-1 discipline as
    build_overview_unit_set() — this is Phase 2-only, pure code, zero model calls."""
    return {frozenset(pair) for pair in manifest.get("known_overlaps") or []}


def build_module_internal_numbering_flag(manifest: dict) -> bool:
    """True when this project's units number their lessons 1..N INTERNALLY (e.g.
    Bluebonnet/Eureka math modules each restart at Lesson 1), set in manifest.yaml
    as `placement: {lesson_numbering_is_module_internal: true}`.

    When set, check_placement will NOT reassign an element across two content units
    on the strength of a bare lesson number or a cross-unit topic alone: the same
    "Lesson 30" legitimately exists inside several modules, so a Module 2 Teacher
    Edition chunk reading "Lesson 30" is NOT evidence it belongs to Module 3 — that
    inference is the single biggest source of false MISMATCH on module-structured
    corpora. Off by default so subject-cluster corpora (e.g. Dallas CTE), where a
    cross-unit topic IS a real filing signal, keep their existing behavior."""
    return bool((manifest.get("placement") or {}).get("lesson_numbering_is_module_internal"))


def quote_names_a_module(supporting_quote: str | None) -> bool:
    """Does the verbatim evidence explicitly name a module (e.g. "Module 3",
    "the focus of Module 6")? Only an explicit module name — not a bare lesson
    number or a topic — is strong enough to reassign across content modules when
    module-internal lesson numbering is in effect."""
    return bool(re.search(r"\bmodule\s*\d", supporting_quote or "", re.IGNORECASE))


def build_day_vocab(project_id: str, manifest: dict) -> list[dict]:
    """Closed vocabulary of every (unit_id, day_id, day_label) in the project,
    loaded straight from each unit's calendar.yaml, plus one unit_supporting
    pseudo-day per unit for content that isn't tied to a specific day slot."""
    root = project_dir(project_id)
    vocab: list[dict] = []
    for unit_id, unit in manifest["units"].items():
        cal_path = root / unit["calendar"]
        if not cal_path.is_file():
            continue
        cal = load_unit_calendar(cal_path)
        for day in cal.get("days", []):
            vocab.append(
                {
                    "unit_id": unit_id,
                    "day_id": day["id"],
                    "day_label": day.get("label", day["id"]),
                }
            )
        if cal.get("unit_supporting"):
            vocab.append(
                {
                    "unit_id": unit_id,
                    "day_id": UNIT_SUPPORTING_SLOT,
                    "day_label": "Unit-supporting material (not tied to one specific day)",
                }
            )
    return vocab


def load_calendars(project_id: str, manifest: dict) -> dict[str, dict]:
    root = project_dir(project_id)
    out = {}
    for unit_id, unit in manifest["units"].items():
        cal_path = root / unit["calendar"]
        if cal_path.is_file():
            out[unit_id] = load_unit_calendar(cal_path)
    return out


# --- PHASE 1: ORGANIZE (model, content-only, closed vocabulary) -------------

PHASE1_RULES = """You are a curriculum audit Analyst performing Layer 1 placement inference. READ-ONLY.

TASK: for each instructional element below (already extracted and cited by Layer 0),
decide, using ONLY the element's own excerpt text, whether it explicitly self-identifies
with one specific unit and/or one specific day/milestone from the CLOSED lists provided.

RULES (mandatory):
- You are NOT told which unit or day this document was actually filed under anywhere
  in this system. Do not guess based on document order, filename, or anything except
  the excerpt text itself. If the text is silent, say so — "not stated" is a valid,
  expected, honorable answer (never invent a match to avoid an empty answer).
- Only pick a unit_id/day_id from the CLOSED LISTS below — never invent a new id or
  reword one. If the excerpt clearly refers to a unit/day but you are unsure exactly
  which item in the list it matches, say "not stated" rather than guessing.
- matched_unit_id and matched_day_id are independent: an excerpt can name its unit
  without naming a day (very common), or vice versa (rare). Each is null on its own
  if not explicitly supported by the text.
- matched_day_id must belong to the SAME unit_id you matched (or unit-supporting for
  that unit) — never mix a day from one unit with a different unit_id.
- matched_day_id must be ONLY the short id shown after "day_id=" below (e.g. "d1" or
  "unit_supporting") — NEVER the unit_id, NEVER the label text, NEVER any combination
  of them. Copying anything other than the bare short id is treated as invalid.
- A standards code citation (e.g. TEKS/TEA text like "(7) The student uses engineering
  design methodologies") is NOT a self-identification, even if its wording happens to
  name a different unit's subject. Standards citations describe a skill being taught or
  assessed — they are not the document declaring what unit it belongs to. Only count
  self_identifies_with_a_unit as true when the excerpt is describing THIS document's own
  lesson/activity content in its own words (e.g. "Lesson – Careers in Hospitality &
  Tourism"), never when it is quoting a standards code that merely mentions a term.
- supporting_quote must be copied verbatim from the excerpt you were given below —
  never paraphrase, never invent.
- reasoning is your ONE-sentence explanation of WHY the excerpt reads as matched_unit_id:
  name the concrete topic, skill, or term in the text that ties it to that unit, so a
  human reviewer can judge your call without re-reading the whole document. Ground it in
  the excerpt's own words — e.g. "describes knife cuts and basic knife skills, which are
  culinary techniques central to Hospitality & Tourism" or "the header reads 'Business,
  Marketing & Finance Project Rubric', naming that unit directly." This is an explanation
  of evidence already present, NOT a suggestion, correction, or new content. Set it to
  null whenever matched_unit_id is null (no match = nothing to explain).
- NEVER write, invent, or suggest curriculum content. You are an auditor, not an author.

CLOSED UNIT LIST (pick matched_unit_id from here, or null):
{unit_list}

CLOSED DAY LIST, grouped by the unit_id each day belongs to (pick matched_day_id as
ONLY the value after "day_id=" on one line, e.g. "d1" — never the unit_id heading
above it, never the label text after the colon):
{day_list}
"""

PHASE1_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "placements": [
    {
      "element_id": "<copy exactly from the element below>",
      "self_identifies_with_a_unit": true,
      "matched_unit_id": "<a unit_id from the CLOSED UNIT LIST, or null>",
      "matched_day_id": "<a day_id from the CLOSED DAY LIST for that same unit, or null>",
      "supporting_quote": "<verbatim quote from the excerpt proving the match, or null>",
      "reasoning": "<one sentence: the specific topic/skill/term in the excerpt that makes it matched_unit_id, or null if matched_unit_id is null>"
    }
  ]
}
One entry per element, in the same order given below."""


def build_phase1_prompt(
    elements: list[dict], unit_vocab: list[dict], day_vocab: list[dict]
) -> str:
    unit_list = "\n".join(f"- {u['unit_id']}: {u['title']}" for u in unit_vocab)
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for d in day_vocab:
        by_unit[d["unit_id"]].append(d)
    day_list = "\n".join(
        f"unit_id: {uid}\n"
        + "\n".join(f'  - day_id={d["day_id"]}: {d["day_label"]}' for d in days)
        for uid, days in by_unit.items()
    )
    rules = PHASE1_RULES.format(unit_list=unit_list, day_list=day_list)
    elements_block = "\n\n".join(
        f"ELEMENT {el['element_id']} (type: {el['element_type']}):\n\"\"\"\n{el['excerpt']}\n\"\"\""
        for el in elements
    )
    return f"""{rules}

ELEMENTS TO JUDGE (from ONE source document — its own doc_id/filename is deliberately
not shown, since that could hint at the answer this call is meant to check against):
{elements_block}

{PHASE1_SCHEMA}
"""


def validate_judgment(
    judgment: dict, unit_ids: set[str], valid_days: dict[str, set[str]], step: str
) -> dict:
    """Defensive guard, same discipline as Layer 0's resolve_excerpt() bounds-check:
    never trust a model's closed-vocabulary pick blindly — a value outside the menu
    it was given (e.g. a combined "unit_id / day_id" string, a reworded label, an
    invented id) is nulled out and logged rather than silently accepted as real,
    which would otherwise corrupt Phase 2's equality check into a false negative
    or false MATCH on a value that was never actually a valid choice."""
    matched_unit_id = judgment.get("matched_unit_id")
    if matched_unit_id is not None and matched_unit_id not in unit_ids:
        log(
            f"WARN: {step}: matched_unit_id {matched_unit_id!r} not in closed vocabulary, nulling"
        )
        matched_unit_id = None
        judgment["matched_day_id"] = (
            None  # a day for an invalid unit can't be trusted either
        )

    matched_day_id = judgment.get("matched_day_id")
    if matched_day_id is not None:
        allowed_days = (
            valid_days.get(matched_unit_id, set()) if matched_unit_id else set()
        )
        if matched_day_id not in allowed_days:
            log(
                f"WARN: {step}: matched_day_id {matched_day_id!r} not valid for unit {matched_unit_id!r}, nulling"
            )
            matched_day_id = None

    judgment["matched_unit_id"] = matched_unit_id
    judgment["matched_day_id"] = matched_day_id
    return judgment


def _placements_from_organize_payload(
    data: dict,
    unit_ids: set[str],
    valid_days: dict[str, set[str]],
    step: str,
) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for p in data.get("placements", []):
        eid = p.get("element_id")
        if eid:
            by_id[eid] = validate_judgment(p, unit_ids, valid_days, f"{step}:{eid}")
    return by_id


def organize_document(
    cfg: dict,
    doc_id: str,
    elements: list[dict],
    unit_vocab: list[dict],
    day_vocab: list[dict],
    raw_dir: Path,
    *,
    batch_size: int = ORGANIZE_BATCH_SIZE,
) -> dict[str, dict]:
    """Phase 1 for one document's elements. Returns {element_id: placement_judgment}.

    Documents with more than ``batch_size`` elements are split into independent
    ORGANIZE calls (roadmap §13). Small docs stay one call — Dallas happy path.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    unit_ids = {u["unit_id"] for u in unit_vocab}
    valid_days: dict[str, set[str]] = defaultdict(set)
    for d in day_vocab:
        valid_days[d["unit_id"]].add(d["day_id"])

    batches = _organize_element_batches(elements, batch_size=batch_size)
    if not batches:
        return {}

    # Single-batch path: identical artifacts/names to pre-§13 runs.
    if len(batches) == 1:
        step = f"layer1-organize-{doc_id}"
        data = call_and_parse_with_retry(
            cfg,
            "analyst",
            build_phase1_prompt(batches[0], unit_vocab, day_vocab),
            step,
            raw_path=raw_dir / f"{doc_id}-phase1.json",
            validator=validate_layer1_placements,
            timeout_seconds=(
                LARGE_CALL_TIMEOUT_SECONDS
                if len(batches[0]) > batch_size // 2
                else None
            ),
        )
        return _placements_from_organize_payload(data, unit_ids, valid_days, step)

    by_id: dict[str, dict] = {}
    n = len(batches)
    for idx, batch in enumerate(batches, start=1):
        step = f"layer1-organize-{doc_id}-batch{idx}of{n}"
        log(
            f"  Phase 1 (ORGANIZE): {doc_id} batch {idx}/{n} "
            f"({len(batch)} elements)"
        )
        try:
            data = call_and_parse_with_retry(
                cfg,
                "analyst",
                build_phase1_prompt(batch, unit_vocab, day_vocab),
                step,
                raw_path=raw_dir / f"{doc_id}-phase1-batch{idx}of{n}.json",
                validator=validate_layer1_placements,
                timeout_seconds=LARGE_CALL_TIMEOUT_SECONDS,
            )
        except (RuntimeError, ValueError) as e:
            # Mirror Layer 0 chunk isolation: one batch must not wipe the rest.
            log(
                f"  ERROR: Phase 1 batch {idx}/{n} failed for {doc_id}, "
                f"leaving those elements unjudged: {e}"
            )
            continue
        by_id.update(
            _placements_from_organize_payload(data, unit_ids, valid_days, step)
        )
    return by_id


def recheck_mismatches(
    cfg: dict,
    bucket_rows: list[dict],
    ledger_by_id: dict[str, dict],
    unit_vocab: list[dict],
    day_vocab: list[dict],
    raw_dir: Path,
) -> None:
    """On-demand independent recheck of MISMATCH candidates (docs/BETS.md Bet 5,
    2026-07-08 revision). This is the redundancy that used to come from a SECOND,
    WEAKER model; now it comes from a second pass of the SAME strong model.

    Before any MISMATCH reaches the report, re-run the model once more, independently,
    on JUST that one element (not the whole document, so nothing else biases it), and
    record whether the second read reproduces the same alternate unit. Disagreement is
    FLAGGED, never silently resolved (Bet 5's "flag both, human decides"): the row keeps
    its MISMATCH status but carries recheck_agreed=False, and synthesize.py treats a
    non-reproduced MISMATCH as low-confidence so a human adjudicates it (Bet 12) rather
    than the pipeline quietly promoting or dropping it.

    Mutates bucket_rows in place (adds recheck_* fields to MISMATCH rows only)."""
    unit_ids = {u["unit_id"] for u in unit_vocab}
    valid_days: dict[str, set[str]] = defaultdict(set)
    for d in day_vocab:
        valid_days[d["unit_id"]].add(d["day_id"])

    mismatch_rows = [r for r in bucket_rows if r["match_status"] == "MISMATCH"]
    if not mismatch_rows:
        return
    log(
        f"  Recheck: independent second pass on {len(mismatch_rows)} MISMATCH candidate(s)"
    )
    agreed = 0
    for r in mismatch_rows:
        el = ledger_by_id.get(r["element_id"])
        r["recheck_performed"] = True
        r["recheck_matched_unit_id"] = None
        r["recheck_agreed"] = None
        if not el:
            continue
        step = f"layer1-recheck-{r['element_id']}"
        try:
            # "verifier" role = same model as "analyst" under the single-model config;
            # the independence comes from re-sampling on the isolated element, not from
            # a different model.
            data = call_and_parse_with_retry(
                cfg,
                "verifier",
                build_phase1_prompt([el], unit_vocab, day_vocab),
                step,
                raw_path=raw_dir / f"{r['element_id']}-recheck.json",
                validator=validate_layer1_placements,
            )
        except ValueError as e:
            log(
                f"    WARN: recheck failed for {r['element_id']} (leaving flagged, unverified): {e}"
            )
            continue
        placements = data.get("placements", [])
        judged = (
            validate_judgment(placements[0], unit_ids, valid_days, step)
            if placements
            else {}
        )
        rematch = judged.get("matched_unit_id")
        r["recheck_matched_unit_id"] = rematch
        r["recheck_agreed"] = rematch == r["matched_unit_id"]
        if r["recheck_agreed"]:
            agreed += 1
    log(
        f"  Recheck: {agreed}/{len(mismatch_rows)} reproduced on the independent second pass"
    )


# --- PHASE 2: CHECK (pure code, zero model calls) ---------------------------

# Secondary to CONCENTRATION_MIN_COUNT (in audit_lib): fraction of a document's
# non-hub self-declarations that agree on one alternate unit. Count is primary;
# this fraction is a secondary check in check_placement only. Tune only against
# a hand-checked sample (docs/BETS.md Bet 12 — Carrasco_Brainstorm.txt set both).
CONCENTRATION_MIN_FRACTION = 0.7


def compute_document_target_counts(
    elements: list[dict], judgments: dict[str, dict], overview_unit_ids: set[str]
) -> Counter:
    """One document's self-declared matched_unit_id values, tallied — EXCLUDING
    hub/overview targets (check_placement discounts those unconditionally as
    non-evidence; see its docstring rule 1). This must exclude them here too, not
    just at the final status decision: a document with 3 genuine
    "hospitality-tourism" declarations and 8 repeated "dallas-isd" boilerplate
    declarations must not have its concentration fraction computed as 3/11 (27%,
    below CONCENTRATION_MIN_FRACTION) when the real, relevant fraction — once the
    boilerplate is correctly excluded as non-evidence — is 3/3 (100%). Counting
    boilerplate in the denominator would let it dilute a genuine corroborated
    signal into looking unconvincing.

    Also runs BEFORE the hub-unit suppression decision in check_placement, not
    after — suppressing every disagreement from a hub/overview document
    unconditionally would hide exactly the Carrasco_Brainstorm.txt case (10/10 of
    its own elements independently self-declaring "hospitality-tourism") inside
    the noise this whole mechanism exists to filter out."""
    counts: Counter = Counter()
    for el in elements:
        j = judgments.get(el["element_id"])
        matched = j.get("matched_unit_id") if j else None
        if matched and matched not in overview_unit_ids:
            counts[matched] += 1
    return counts


def check_placement(
    element: dict,
    judgment: dict | None,
    parent_link_map: dict[str, str],
    overview_unit_ids: set[str],
    target_counts: Counter,
    known_overlap_pairs: set[frozenset],
    module_internal_numbering: bool = False,
) -> dict:
    """Pure code join: Phase 1's self-declared unit vs manifest's parent-link unit.
    No fuzzy string matching anywhere — Phase 1 already resolved to a clean ID from
    the closed vocabulary, so this is true equality, nothing more.

    Two hub-unit-aware refinements on top of plain equality (docs/BETS.md Bet 12,
    found live hand-checking the Dallas corpus's 143 raw MISMATCH rows):

    1. matched_unit_id itself names a hub/overview unit (e.g. a "Connect with
       Dallas ISD CTE" footer line, or a "Dallas ISD CTE" branding/URL line
       repeated across split elements) — never specific enough to be real
       placement evidence, discounted unconditionally regardless of how many
       times it repeats, same as if Phase 1 found nothing. Checked BEFORE rule 2
       and regardless of what parent_unit_id is: a hand-check of the validation
       run caught this firing even when parent_unit_id was ALSO a hub unit
       (f3e58b61782a, filed under the "career-cluster" hub, had 8 "MISMATCH"
       rows that were just a repeated branding URL self-declaring the "dallas-isd"
       hub — boilerplate, not a real corroborated signal, even though it was
       "concentrated" by the same-count rule below). Two hub units both being
       involved doesn't make a branding line meaningful; checking this rule
       unconditionally, before rule 2 ever runs, closes that gap.
    2. parent_unit_id is a hub/overview unit and the disagreement is NOT the
       corroborated case in CONCENTRATION_MIN_COUNT/FRACTION above — a hub
       document's element naming one specific other unit is that hub doing its
       job (a "Career Clusters" slide covering Agriculture is not a filing
       error), recorded as CROSS_REFERENCE rather than MISMATCH.
    3. (parent_unit_id, matched_unit_id) is a human-confirmed known_overlaps pair
       (build_known_overlap_set()) — corroboration count alone can't tell a real
       misfile apart from a document genuinely, on-topic, teaching an adjacent
       discipline's skill (e.g. "engineering design" content inside an
       Architecture & Construction lesson plan, confirmed by a human reviewer via
       layer1/REVIEW-QUEUE.md as expected, not wrong). Recorded as
       EXPECTED_OVERLAP, checked only AFTER rules 1-2 (a hub-unit disagreement
       stays governed by the hub rules regardless of whether it also happens to
       be a listed overlap pair).
    4. module_internal_numbering is on (build_module_internal_numbering_flag) and
       the disagreement between two CONTENT units rests only on a lesson number or
       a shared topic — the quote never names a module explicitly. On corpora where
       each module restarts lesson numbering at 1 (Bluebonnet/Eureka math), "Lesson
       30" inside a Module 2 doc is NOT evidence it belongs to Module 3; that
       inference is the dominant false-MISMATCH source. Recorded UNVERIFIED, not
       MISMATCH. An explicit "Module 3" in the quote still falls through to MISMATCH.
    """
    doc_id = element["doc_id"]
    parent_unit_id = parent_link_map.get(doc_id)
    matched_unit_id = (judgment or {}).get("matched_unit_id")
    matched_day_id = (judgment or {}).get("matched_day_id")
    supporting_quote = (judgment or {}).get("supporting_quote")
    reasoning = (judgment or {}).get("reasoning")

    total_declared = sum(target_counts.values())
    dominant_target, dominant_count = (
        target_counts.most_common(1)[0] if target_counts else (None, 0)
    )
    concentrated = (
        dominant_count >= CONCENTRATION_MIN_COUNT
        and total_declared > 0
        and dominant_count / total_declared >= CONCENTRATION_MIN_FRACTION
    )

    cross_reference_note = None

    if parent_unit_id is None:
        match_status = "ORPHAN"
        final_unit_id = matched_unit_id
        placement_basis = "self_declared" if matched_unit_id else "none"
    elif matched_unit_id is None:
        match_status = "UNVERIFIED"
        final_unit_id = parent_unit_id
        placement_basis = "parent_link_only"
    elif matched_unit_id == parent_unit_id:
        match_status = "MATCH"
        final_unit_id = matched_unit_id
        placement_basis = "self_declared"
    elif matched_unit_id in overview_unit_ids:
        # Checked unconditionally, regardless of parent_unit_id's own kind (see
        # docstring rule 1) — a hub-unit self-declaration is never specific
        # placement evidence even when the parent is itself another hub.
        match_status = "UNVERIFIED"
        final_unit_id = parent_unit_id
        placement_basis = "parent_link_only"
        cross_reference_note = (
            f"discounted self-declaration of hub unit '{matched_unit_id}' "
            "(not specific enough to be placement evidence, e.g. boilerplate branding)"
        )
    elif parent_unit_id in overview_unit_ids and not (
        concentrated and matched_unit_id == dominant_target
    ):
        match_status = "CROSS_REFERENCE"
        final_unit_id = parent_unit_id
        placement_basis = "self_declared"
        cross_reference_note = (
            f"hub unit '{parent_unit_id}' element references '{matched_unit_id}' "
            "— expected overview behavior, not a misfile"
        )
    elif frozenset((parent_unit_id, matched_unit_id)) in known_overlap_pairs:
        match_status = "EXPECTED_OVERLAP"
        final_unit_id = parent_unit_id
        placement_basis = "self_declared"
        cross_reference_note = (
            f"'{parent_unit_id}' and '{matched_unit_id}' are a human-confirmed "
            "legitimate overlap pair, not a filing error"
        )
    elif (
        module_internal_numbering
        and matched_unit_id not in overview_unit_ids
        and not quote_names_a_module(supporting_quote)
    ):
        # docstring rule 4 (module-internal lesson numbering) — a cross-content-unit
        # self-declaration whose only evidence is a bare lesson number or a shared
        # topic (the quote never names a module) cannot reassign the element: the
        # same "Lesson 30" exists inside several modules. Downgrade to UNVERIFIED
        # rather than assert a misfile. Explicit module naming in the quote still
        # produces a MISMATCH below. (parent-is-overview cases were already handled.)
        match_status = "UNVERIFIED"
        final_unit_id = parent_unit_id
        placement_basis = "parent_link_only"
        cross_reference_note = (
            f"self-declaration of '{matched_unit_id}' rests on module-internal lesson "
            "numbering / a shared topic, not an explicit module name — not strong "
            "enough to reassign across content units"
        )
    else:
        match_status = "MISMATCH"
        final_unit_id = parent_unit_id  # code never picks a winner for downstream routing; report both
        placement_basis = "self_declared"

    corroboration = None
    if match_status == "MISMATCH":
        corroboration = {
            "same_target_count": target_counts.get(matched_unit_id, 0),
            "total_self_declarations_in_doc": total_declared,
        }

    return {
        "element_id": element["element_id"],
        "doc_id": doc_id,
        "element_type": element["element_type"],
        "excerpt": element["excerpt"],
        "matched_unit_id": matched_unit_id,
        "matched_day_id": matched_day_id,
        "supporting_quote": supporting_quote,
        "reasoning": reasoning,
        "parent_link_unit_id": parent_unit_id,
        "final_unit_id": final_unit_id,
        "final_day_id": matched_day_id,  # Phase 1 is the only source of day info; null if not stated
        "match_status": match_status,
        "placement_basis": placement_basis,
        "cross_reference_note": cross_reference_note,
        "mismatch_corroboration": corroboration,
        "confidence": element.get("confidence"),
        "tier": element.get("tier"),
        # Filled in later by Phase 3 (see run_layer1) if this element ends up in a
        # role's fulfilled_by list — kept here, not only in findings.json, per the
        # design's row schema (docs/roadmap.md "Layer 1"): a reader looking at ONE
        # element's row should be able to tell whether it fulfilled anything without
        # cross-referencing a second file.
        "fulfills_role": None,
        "fulfillment_confidence": None,
    }


def find_near_duplicates(rows: list[dict]) -> None:
    """Cheap code-level near-duplicate/threading check (Bet 11 practice #4): two
    elements with near-identical excerpt text land in the same bucket via
    duplicate_of, so they don't silently double-count as two separate fulfillments.
    Mutates rows in place, adding duplicate_of (nullable)."""
    seen: dict[str, str] = {}
    for row in rows:
        row["duplicate_of"] = None
    for row in rows:
        key = normalize_ws(row["excerpt"])[:200]
        if key in seen:
            row["duplicate_of"] = seen[key]
        else:
            seen[key] = row["element_id"]


# --- PHASE 3: FULFILL (model, narrow, per day-slot) -------------------------

PHASE3_RULES = """You are a curriculum audit Verifier performing a Layer 1 role-fulfillment check. READ-ONLY.

TASK: for this one day/slot, you are given the artifact-kind roles it is EXPECTED to
have (from the unit's own calendar), and the candidate elements already routed here.
For each expected role, decide which (if any) candidate elements actually FUNCTION as
that role — regardless of what type their own source document was labeled as.

RULES (mandatory):
- Judge by what the excerpt itself DOES, not by any label attached to its source file.
  A file typed "lesson_plan" can still contain a passage that functions as a worksheet.
- A role with no genuinely fulfilling candidate must be left with an empty list — do
  not force a weak match just to avoid reporting a gap. An honest "nothing fulfills
  this" is the actual finding this audit exists to produce.
- fulfilled_by must list element_id values ONLY from the candidates given below.
- confidence reflects how clearly the candidate(s) function as the role — "low" is a
  valid, expected answer for a borderline call, not something to avoid.
- NEVER write, invent, or suggest curriculum content. You are an auditor, not an author.
"""

PHASE3_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "role_fulfillment": [
    {
      "role": "<one of the expected roles below>",
      "fulfilled_by": ["<element_id>", "..."],
      "confidence": "high|medium|low",
      "reasoning": "<one sentence, citing what in the excerpt makes this a match, or why nothing does>"
    }
  ]
}
One entry per expected role, even if fulfilled_by ends up empty. confidence only
matters when fulfilled_by is non-empty; use "high" as a placeholder otherwise."""


def build_phase3_prompt(expected_roles: list[str], candidates: list[dict]) -> str:
    roles_block = ", ".join(expected_roles)
    candidates_block = "\n\n".join(
        f"CANDIDATE {c['element_id']} (Layer 0 type: {c['element_type']}):\n\"\"\"\n{c['excerpt']}\n\"\"\""
        for c in candidates
    )
    return f"""{PHASE3_RULES}

EXPECTED ROLES for this slot: {roles_block}

CANDIDATE ELEMENTS routed to this slot:
{candidates_block if candidates else "(none — no elements were routed to this slot at all)"}

{PHASE3_SCHEMA}
"""


def is_true_duplicate(
    fulfilled_by: list[str], bucket_rows_by_id: dict[str, dict]
) -> bool:
    """A role fulfilled by 2+ elements is NOT automatically a DUPLICATE finding —
    confirmed live on unit-1-fundamentals-leadership: 3 distinct planning-guide
    documents each independently containing their own genuine day-by-day sequence
    all satisfied "lesson_plan", and treating that as DUPLICATE was actively wrong
    (each is real, separate evidence, none a restatement of another — confirmed
    by checking their own duplicate_of links, all None). Multiple legitimate,
    non-duplicate sources satisfying one role is a GOOD finding, not a problem to
    flag. True DUPLICATE (Bet 11 practice #4: same underlying claim recognized
    twice, not double-counted) only applies when 2+ of the fulfilling elements are
    themselves linked via the near-duplicate check in find_near_duplicates() —
    i.e. Phase 3 was independently handed the same claim's text more than once."""
    roots = set()
    for eid in fulfilled_by:
        row = bucket_rows_by_id.get(eid)
        if not row:
            continue
        roots.add(row["duplicate_of"] or eid)
    return len(roots) < len(fulfilled_by)


def fulfill_slot(
    cfg: dict,
    unit_id: str,
    day_id: str,
    expected_roles: list[str],
    candidates: list[dict],
    raw_dir: Path,
) -> list[dict]:
    if not expected_roles:
        return []
    if not candidates:
        # No model call needed — an empty candidate list can only produce empty
        # fulfilled_by for every role; this is Bet 0 in reverse, don't spend a
        # call when the deterministic answer is already known.
        return [
            {
                "role": r,
                "fulfilled_by": [],
                "confidence": "high",
                "reasoning": "no candidate elements were routed to this slot",
            }
            for r in expected_roles
        ]
    step = f"layer1-fulfill-{unit_id}-{day_id}"
    prompt = build_phase3_prompt(expected_roles, candidates)
    raw_dir.mkdir(parents=True, exist_ok=True)
    data = call_and_parse_with_retry(
        cfg,
        "verifier",
        prompt,
        step,
        raw_path=raw_dir / f"{unit_id}-{day_id}-phase3.json",
        validator=validate_layer1_fulfillment,
        normalizer=_normalize_fulfillment,
    )
    return data.get("role_fulfillment", [])


def build_review_queue_md(bucket_rows: list[dict], manifest: dict) -> str:
    """Human-in-the-loop calibration queue (docs/BETS.md Bet 12): every remaining
    MISMATCH, grouped by (parent_unit_id, matched_unit_id) PAIR rather than by
    individual document. The pair is the reusable unit of decision here — once a
    human confirms "architecture-construction and engineering legitimately
    overlap," that fact applies to every future document in that pair, not just
    the one that surfaced it first (see build_known_overlap_set()). An individual
    document being wrong (e.g. Carrasco_Brainstorm.txt) doesn't generalize the
    same way and needs no entry here beyond what REPORT.md already shows — this
    queue exists specifically to shrink itself over time as pairs get resolved
    into manifest.yaml's known_overlaps, self-cleaning on the next run."""
    mismatch_rows = [r for r in bucket_rows if r["match_status"] == "MISMATCH"]
    by_pair: dict[frozenset, list[dict]] = defaultdict(list)
    for r in mismatch_rows:
        by_pair[frozenset((r["parent_link_unit_id"], r["matched_unit_id"]))].append(r)

    titles = {uid: u.get("title", uid) for uid, u in manifest["units"].items()}

    def _pair_section(pair: frozenset, rows: list[dict]) -> str:
        a, b = sorted(pair)
        docs = sorted({r["doc_id"] for r in rows})
        sample = sorted(
            rows,
            key=lambda r: -(r["mismatch_corroboration"] or {}).get(
                "same_target_count", 0
            ),
        )[:2]
        excerpts = "\n".join(
            f"  - `{r['element_id']}` (doc {r['doc_id']}, filed under '{r['parent_link_unit_id']}', "
            f"self-declares '{r['matched_unit_id']}'): \"{r['excerpt'][:200].strip()}\""
            + (
                f"\n    - why: {r['reasoning'].strip()}"
                if (r.get("reasoning") or "").strip()
                else ""
            )
            for r in sample
        )
        return f"""### {titles.get(a, a)} <-> {titles.get(b, b)} ({a} / {b})

**{len(rows)} element(s) across {len(docs)} document(s)** disagree on this pair. Sample excerpt(s):
{excerpts}

**Decision:** if this is a genuine, expected overlap between these two units (not a filing
error), add `[{a}, {b}]` to this project's `manifest.yaml` under `known_overlaps` and re-run
Layer 1 — every element with this pair will be reclassified EXPECTED_OVERLAP, no model calls
needed. If this is a real error, no action needed here — it's already captured as a MISMATCH
finding in `REPORT.md`.
"""

    if not by_pair:
        body = "(no MISMATCH findings to review — either none exist, or all known overlap pairs are already resolved)"
    else:
        ordered_pairs = sorted(by_pair.items(), key=lambda kv: -len(kv[1]))
        body = "\n".join(_pair_section(pair, rows) for pair, rows in ordered_pairs)

    return f"""# Layer 1 Human Review Queue

Every current MISMATCH finding, grouped by unit-pair (not by individual document — the
pair is the reusable decision: one human verdict per pair applies to every document that
pair ever shows up on again, not just the one below). See docs/BETS.md Bet 12.

For each pair: read the excerpt(s), decide whether this is a genuine filing error or an
expected, on-topic overlap between two related disciplines (e.g. Architecture & Construction
legitimately teaching engineering design methodologies, per Texas CTE's own TEKS).

{body}
"""


# --- Orchestration -----------------------------------------------------------


def run_layer1(project_id: str, only_units: list[str] | None = None) -> Path:
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    ledger = load_ledger(project_id)
    parent_link_map = build_parent_link_map(manifest)
    unit_vocab = build_unit_vocab(manifest)
    overview_unit_ids = build_overview_unit_set(manifest)
    known_overlap_pairs = build_known_overlap_set(manifest)
    module_internal_numbering = build_module_internal_numbering_flag(manifest)
    day_vocab = build_day_vocab(project_id, manifest)
    calendars = load_calendars(project_id, manifest)

    cfg = load_config()
    l1_dir = root / "layer1"
    raw_dir = l1_dir / ".raw"

    # Scope which ledger elements THIS run touches (--only-unit lets us validate
    # on a small, deliberately chosen set of units first, per roadmap.md's
    # Definition of Done, without needing to process the whole corpus every time).
    if only_units:
        unknown = [u for u in only_units if u not in manifest["units"]]
        if unknown:
            raise KeyError(f"Unknown unit(s) in manifest: {unknown}")
        doc_ids_in_scope = {
            doc_id_from_filename(p)
            for uid in only_units
            for p in manifest["units"][uid].get("documents", [])
        }
        scoped_ledger = [r for r in ledger if r["doc_id"] in doc_ids_in_scope]
    else:
        scoped_ledger = ledger

    # Loom soft gate: only place elements whose documents were routed (Path A/B/C).
    # Unrouted docs are quarantined — never silently dropped without a log.
    route_map_path = root / "layer0" / "route-map.json"
    if route_map_path.is_file():
        from route import routed_doc_ids

        allowed = routed_doc_ids(project_id)
        before = len(scoped_ledger)
        quarantined = sorted(
            {r["doc_id"] for r in scoped_ledger if r.get("doc_id") not in allowed}
        )
        scoped_ledger = [r for r in scoped_ledger if r.get("doc_id") in allowed]
        if quarantined:
            qpath = l1_dir / "unrouted-quarantine.json"
            l1_dir.mkdir(parents=True, exist_ok=True)
            qpath.write_text(
                json.dumps(
                    {
                        "note": "Docs not in layer0/route-map.json — skipped for Layer 1 place",
                        "doc_ids": quarantined,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            log(
                f"Layer 1 soft gate: skipped {before - len(scoped_ledger)} element(s) "
                f"from {len(quarantined)} unrouted doc(s) → {qpath.name}"
            )
    else:
        log("WARN: no layer0/route-map.json — Layer 1 running without Loom route gate")

    scope_label = f" (units={','.join(only_units)})" if only_units else ""
    log(f"Layer 1: {len(scoped_ledger)} element(s) in scope{scope_label}")

    # Carry forward untouched units' already-computed rows, same lesson layer0.py
    # paid to learn twice (docs/roadmap.md "Layer 0" bugs #3 and the --only/--no-
    # resume ledger-wipe): a --only-unit run must be able to ADD/UPDATE the units
    # it touches without silently deleting every other unit's bucket-ledger rows
    # and findings. Loaded unconditionally so a full run (only_units=None) still
    # works identically to before (carry_forward stays empty in that case).
    existing_bucket_rows: list[dict] = []
    existing_findings: list[dict] = []
    bucket_ledger_path = l1_dir / "bucket-ledger.json"
    findings_path = l1_dir / "findings.json"
    if bucket_ledger_path.is_file():
        existing_bucket_rows = json.loads(bucket_ledger_path.read_text())
    if findings_path.is_file():
        existing_findings = json.loads(findings_path.read_text())

    carry_forward_bucket_rows: list[dict] = []
    carry_forward_findings: list[dict] = []
    if only_units:
        touched_doc_ids = {r["doc_id"] for r in scoped_ledger}
        carry_forward_bucket_rows = [
            r for r in existing_bucket_rows if r["doc_id"] not in touched_doc_ids
        ]
        carry_forward_findings = [
            f for f in existing_findings if f["unit_id"] not in set(only_units)
        ]

    # PHASE 1 — ORGANIZE, batched per source document (Bet 11 practice #3:
    # concept-clustering-for-consistency, applied as "batch by shared parent doc").
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for row in scoped_ledger:
        by_doc[row["doc_id"]].append(row)

    all_judgments: dict[str, dict] = {}
    for doc_id, elements in by_doc.items():
        log(f"  Phase 1 (ORGANIZE): {doc_id} ({len(elements)} elements)")
        try:
            judgments = organize_document(
                cfg, doc_id, elements, unit_vocab, day_vocab, raw_dir
            )
        except Exception as e:
            log(f"  ERROR: Phase 1 failed for {doc_id}, leaving unjudged: {e}")
            judgments = {}
        all_judgments.update(judgments)

    # PHASE 2 — CHECK, pure code. Target counts are computed per-document BEFORE
    # the per-element check (multi-instance-learning "bag" aggregation — see
    # check_placement's docstring) so a hub unit's suppression rule can tell a
    # genuinely corroborated misfile apart from ordinary cross-referencing.
    doc_target_counts = {
        doc_id: compute_document_target_counts(
            elements, all_judgments, overview_unit_ids
        )
        for doc_id, elements in by_doc.items()
    }
    bucket_rows = [
        check_placement(
            el,
            all_judgments.get(el["element_id"]),
            parent_link_map,
            overview_unit_ids,
            doc_target_counts.get(el["doc_id"], Counter()),
            known_overlap_pairs,
            module_internal_numbering,
        )
        for el in scoped_ledger
    ]
    find_near_duplicates(bucket_rows)

    # On-demand recheck (Bet 5): a MISMATCH is the audit's strongest claim about a
    # document, so spend one more independent same-model pass to confirm it before it
    # reaches the report. Disagreement is flagged on the row, not silently resolved.
    ledger_by_id = {el["element_id"]: el for el in scoped_ledger}
    recheck_mismatches(cfg, bucket_rows, ledger_by_id, unit_vocab, day_vocab, raw_dir)

    high_conf_mismatch = sum(
        1
        for r in bucket_rows
        if r["match_status"] == "MISMATCH"
        and (r["mismatch_corroboration"] or {}).get("same_target_count", 0)
        >= CONCENTRATION_MIN_COUNT
    )
    log(
        f"  Phase 2 (CHECK): "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'MATCH')} MATCH, "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'MISMATCH')} MISMATCH "
        f"({high_conf_mismatch} corroborated by {CONCENTRATION_MIN_COUNT}+ elements of the same doc), "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'CROSS_REFERENCE')} CROSS_REFERENCE (hub unit, not a misfile), "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'EXPECTED_OVERLAP')} EXPECTED_OVERLAP (human-confirmed, not a misfile), "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'ORPHAN')} ORPHAN, "
        f"{sum(1 for r in bucket_rows if r['match_status'] == 'UNVERIFIED')} UNVERIFIED"
    )

    # Checkpoint immediately after Phase 2, BEFORE Phase 3 spends any more model
    # calls (Bet 6: unattended operation must survive a mid-run failure). Phase 1+2
    # are pure-CPU-cheap to redo from a cached Layer 0 ledger, but on a full corpus
    # Phase 3 is the most model-call-heavy stage and the most likely place a long
    # run gets interrupted — without this, a Phase 3 failure on unit N would throw
    # away Phase 1/2 results for ALL units, not just the ones already checked.
    l1_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        l1_dir / "bucket-ledger.json",
        json.dumps(bucket_rows + carry_forward_bucket_rows, indent=2),
    )
    log(
        f"  Checkpointed {len(bucket_rows)} bucket rows before Phase 3"
        + (
            f" (+{len(carry_forward_bucket_rows)} carried forward from other units)"
            if carry_forward_bucket_rows
            else ""
        )
    )

    # PHASE 3 — FULFILL, one call per (unit, day-slot) actually in scope.
    units_in_scope = set(only_units) if only_units else set(calendars.keys())
    bucket_rows_by_id = {r["element_id"]: r for r in bucket_rows}
    findings: list[dict] = []
    for unit_id in sorted(units_in_scope):
        cal = calendars.get(unit_id)
        if not cal:
            continue
        slots: list[tuple[str, list[str]]] = [
            (d["id"], d.get("expected", [])) for d in cal.get("days", [])
        ]
        if cal.get("unit_supporting"):
            slots.append((UNIT_SUPPORTING_SLOT, cal["unit_supporting"]))

        for day_id, expected_roles in slots:
            if day_id == UNIT_SUPPORTING_SLOT:
                # unit_supporting is explicitly NOT day-specific (calendar.yaml keeps
                # it separate from the days list), so any element confirmed to belong
                # to this unit is a fair candidate here even with no self-declared day
                # at all — excluding UNVERIFIED (parent-link-only, no day stated)
                # elements would silently throw away most of a unit's evidence for
                # exactly the slot that doesn't need day precision in the first place.
                candidates = [
                    r
                    for r in bucket_rows
                    if r["final_unit_id"] == unit_id
                    and r["final_day_id"] in (None, UNIT_SUPPORTING_SLOT)
                ]
            else:
                candidates = [
                    r
                    for r in bucket_rows
                    if r["final_unit_id"] == unit_id and r["final_day_id"] == day_id
                ]
            # Isolate one slot's failure from every other slot (same lesson as
            # layer0.py's per-chunk try/except: a single failed chunk must not
            # discard results for chunks that already succeeded). CHECK_FAILED is
            # deliberately distinct from MISSING — a failed model call is not
            # evidence of an actual gap, and must never be silently reported as one.
            try:
                fulfillment = fulfill_slot(
                    cfg, unit_id, day_id, expected_roles, candidates, raw_dir
                )
            except Exception as e:
                log(
                    f"  ERROR: Phase 3 failed for {unit_id}/{day_id}, marking CHECK_FAILED: {e}"
                )
                fulfillment = [
                    {
                        "role": r,
                        "fulfilled_by": [],
                        "confidence": None,
                        "reasoning": str(e),
                        "_check_failed": True,
                    }
                    for r in expected_roles
                ]

            for f in fulfillment:
                fulfilled_by = f.get("fulfilled_by", [])
                if f.get("_check_failed"):
                    status = "CHECK_FAILED"
                elif not fulfilled_by:
                    status = "MISSING"
                elif is_true_duplicate(fulfilled_by, bucket_rows_by_id):
                    status = "DUPLICATE"
                else:
                    status = "FULFILLED"
                findings.append(
                    {
                        "unit_id": unit_id,
                        "day_id": day_id,
                        "role": f.get("role"),
                        "fulfilled_by": fulfilled_by,
                        "reasoning": f.get("reasoning"),
                        "status": status,
                    }
                )
                # Backfill onto the element's own bucket_ledger row (design spec's
                # row schema), not just findings.json — bucket_rows_by_id holds the
                # SAME dict objects as bucket_rows, so mutating here is reflected in
                # the bucket-ledger.json written at the end of this function.
                if status in ("FULFILLED", "DUPLICATE"):
                    for eid in fulfilled_by:
                        row = bucket_rows_by_id.get(eid)
                        if row is not None:
                            row["fulfills_role"] = f.get("role")
                            row["fulfillment_confidence"] = f.get("confidence")

        # Checkpoint after each unit's slots complete — Phase 3 is the model-call-
        # heavy stage on a full corpus; losing only the in-progress unit (not every
        # unit already finished) on a crash is the whole point of checkpointing here.
        atomic_write(
            l1_dir / "findings.json",
            json.dumps(findings + carry_forward_findings, indent=2),
        )

    all_bucket_rows = bucket_rows + carry_forward_bucket_rows
    all_findings = findings + carry_forward_findings

    l1_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(l1_dir / "bucket-ledger.json", json.dumps(all_bucket_rows, indent=2))
    atomic_write(l1_dir / "findings.json", json.dumps(all_findings, indent=2))

    missing = sum(1 for f in all_findings if f["status"] == "MISSING")
    duplicate = sum(1 for f in all_findings if f["status"] == "DUPLICATE")
    check_failed = sum(1 for f in all_findings if f["status"] == "CHECK_FAILED")
    mismatch_rows = [r for r in all_bucket_rows if r["match_status"] == "MISMATCH"]
    cross_reference = sum(
        1 for r in all_bucket_rows if r["match_status"] == "CROSS_REFERENCE"
    )
    expected_overlap = sum(
        1 for r in all_bucket_rows if r["match_status"] == "EXPECTED_OVERLAP"
    )
    orphan = sum(1 for r in all_bucket_rows if r["match_status"] == "ORPHAN")

    # Shared with synthesize.py via audit_lib.is_corroborated (includes recheck
    # demotion) so Layer 1 REPORT.md and GLOBAL-AUDIT.md never disagree on HIGH.
    high_conf = [r for r in mismatch_rows if is_corroborated(r)]
    low_conf = [r for r in mismatch_rows if not is_corroborated(r)]

    report = f"""# Layer 1 Report

**Status:** {"SUCCESS" if check_failed == 0 else "SUCCESS WITH CHECK FAILURES"}
**Project:** {project_id}
**Scope:** {','.join(only_units) if only_units else "all units"}
**Elements judged:** {len(all_bucket_rows)}{f" ({len(bucket_rows)} newly judged this run, {len(carry_forward_bucket_rows)} carried forward from other units)" if carry_forward_bucket_rows else ""}
**MATCH:** {sum(1 for r in all_bucket_rows if r['match_status'] == 'MATCH')}
**MISMATCH:** {len(mismatch_rows)}
  - corroborated ({CONCENTRATION_MIN_COUNT}+ elements of the same document agree): {len(high_conf)} — high-confidence, likely real misfiles
  - single/low-corroboration: {len(low_conf)} — needs individual review, not yet strong enough to act on alone
**CROSS_REFERENCE (hub/overview unit's own element names another unit — expected, not a misfile):** {cross_reference}
**EXPECTED_OVERLAP (human-confirmed legitimate overlap pair, see manifest.yaml known_overlaps — not a misfile):** {expected_overlap}
**ORPHAN:** {orphan}
**UNVERIFIED (no self-declaration, parent-link only, or a discounted hub-unit self-declaration):** {sum(1 for r in all_bucket_rows if r['match_status'] == 'UNVERIFIED')}
**MISSING role findings:** {missing}
**DUPLICATE role findings:** {duplicate}
**CHECK_FAILED role findings (Phase 3 model call failed — NOT a real finding, needs re-run):** {check_failed}

## Artifacts
- `bucket-ledger.json` — one row per Layer 0 element, with Phase 1-2 placement judgment
  (plus `fulfills_role`/`fulfillment_confidence` backfilled from Phase 3, if any)
- `findings.json` — one row per (unit, day, expected role), with Phase 3 fulfillment judgment
- `REVIEW-QUEUE.md` — remaining MISMATCH findings grouped by unit-pair, for a human to
  confirm as either a genuine error or an expected overlap (see manifest.yaml known_overlaps)
- `.raw/<doc_id>-phase1.json` — raw Phase 1 model responses
- `.raw/<unit_id>-<day_id>-phase3.json` — raw Phase 3 model responses

## MISMATCH detail (sorted by corroboration strength)
{chr(10).join(
    f"- [{'HIGH' if is_corroborated(r) else 'low'}] {r['element_id']} (doc {r['doc_id']}): "
    f"filed under '{r['parent_link_unit_id']}', self-declares '{r['matched_unit_id']}' "
    f"({(r['mismatch_corroboration'] or {}).get('same_target_count', 0)}/"
    f"{(r['mismatch_corroboration'] or {}).get('total_self_declarations_in_doc', 0)} of this doc's own elements agree)"
    for r in sorted(mismatch_rows, key=lambda r: -(r['mismatch_corroboration'] or {}).get('same_target_count', 0))
) if mismatch_rows else "(none)"}
"""
    atomic_write(l1_dir / "REPORT.md", report)
    atomic_write(
        l1_dir / "REVIEW-QUEUE.md", build_review_queue_md(all_bucket_rows, manifest)
    )
    log(
        f"Layer 1 done: {len(all_bucket_rows)} elements judged, {len(all_findings)} role findings -> {l1_dir}"
    )
    return l1_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 1: sort Layer 0 ledger elements into buckets, check against manifest"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--only-unit",
        help="Restrict this run to one or more units' documents, comma-separated (for small-set validation)",
    )
    args = parser.parse_args()

    try:
        validate_slug_id(args.project, "project id")
        only_units = None
        if args.only_unit:
            only_units = [u.strip() for u in args.only_unit.split(",") if u.strip()]
            for u in only_units:
                validate_slug_id(u, "unit id")
        run_layer1(args.project, only_units=only_units)
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
