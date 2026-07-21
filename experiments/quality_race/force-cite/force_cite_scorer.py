#!/usr/bin/env python3
"""
force_cite_scorer.py — "force-cite" band scorer for the quality-race experiment.

PROBLEM (why this module exists)
--------------------------------
The shared band scorers (S2 UbD, S4 quality in lesson_scorers.py) make ONE model
call per lesson and ask the local model (Nemotron nano 30B on llama.cpp :8080) to
assign a 0-3 band per dimension AND cite a verbatim excerpt from the lesson's own
elements. On this model the citations come back WRONG — hallucinated ids or quotes
that appear nowhere in the lesson — so the auditor guard in `_band_result`
downgrades them to "[unevidenced band — needs review]". Net: quality scoring is
untrusted and the locked rung (lesson_rung.LOCKED_SCORERS) deliberately excludes
S2/S4.

APPROACH: "force-cite" (keep it to ~one call/lesson, but make citation MANDATORY
and self-healing)
------------------------------------------------------------------------------
1. TIGHTEN THE PROMPT. Every candidate element is shown with a short synthetic id
   like [E0] (type) followed by its text. A short id is far easier for a small
   model to copy exactly than the real, long Layer-0 ids (e.g.
   "<file>-chunk13of23-e7"), so we present E-ids and map them back to real ids
   after parsing. The model may NOT assign band>0 without copying an EXACT verbatim
   quote from a cited E-id.
2. CONSTRAIN WITH GBNF GRAMMAR. The llama.cpp server honours a `grammar` field
   (verified live). We generate a grammar that forces valid JSON AND restricts
   `evidence_element_id` to the real candidate id set (plus ""). That structurally
   eliminates the "cited a non-existent id" failure mode. Grammar can NOT enforce
   that a free-text quote is a real substring, so:
3. VALIDATE + SELF-HEAL. After parsing, every band>0 is validated: its quote must
   be a verbatim (whitespace-normalized) substring of the cited element, and the
   id must be a real candidate. Failing dimensions are RE-PROMPTED alone (grammar
   restricted to just those criteria), up to 2 retries.
4. HONEST FALLBACK. If a dimension still has no verifiable citation after the
   retries, it is forced to band 0 / needs-review — never a trusted uncited band.

ADDITIVE-ONLY: this file lives entirely under experiments/quality_race/force-cite/
and only IMPORTS from the shared stack. It registers NEW scorer ids
(`s4_quality_forcecite`, `s2_ubd_forcecite`) via the shared registry; it never
edits lesson_scorers.py, lesson_scoring.py, lesson_rung.py, the rubrics, or config.
"""

from __future__ import annotations

import time

import requests

# --- reuse the shared stack (never re-implement its schema or helpers) --------
from audit_lib import excerpt_cited_in, log, parse_model_json
from layer1 import extract_content
from lesson_scorers import _band_candidates  # candidate-element selection (reused)
from lesson_scoring import (
    CriterionResult,
    Evidence,
    LessonInput,
    Scorer,
    ScorerResult,
    register_scorer,
    summarize_bands,
)
from rubrics import QUALITY_RUBRIC, UBD_RUBRIC, load_rubric

# How many times we re-ask ONLY the dimensions whose citation failed validation.
MAX_HEAL_RETRIES = 2

# A stricter, more directive preamble than the shared AUDITOR_PREAMBLE: the single
# biggest lever on a small model is telling it, unambiguously, that a band without
# a copied quote is invalid and it should prefer an honest 0.
FORCE_CITE_PREAMBLE = (
    "You are a READ-ONLY curriculum audit scorer. You judge ONLY the lesson's own "
    "words; you never write, rewrite, or invent content. For EVERY dimension you "
    "assign a band greater than 0 you MUST copy an EXACT, VERBATIM span of text from "
    "ONE cited element and put its id in evidence_element_id. The quote must be a "
    "character-for-character substring of that element — do NOT paraphrase, summarize, "
    "or combine elements. If you cannot find a verbatim span that supports a "
    "dimension, assign band 0 with an empty quote. An honest 0 is CORRECT; a band "
    "without a real quote is WRONG."
)


# --- synthetic id mapping ----------------------------------------------------


def _synthetic_map(candidates: list) -> dict[str, object]:
    """Map short, copy-friendly ids (E0, E1, ...) to the real candidate elements.

    Small models reliably copy `E7`; they mangle `<file>-chunk13of23-e7`. We do the
    hard id-matching ourselves and only ask the model for the easy token."""
    return {f"E{i}": el for i, el in enumerate(candidates)}


def _present_elements(cand_map: dict[str, object]) -> str:
    if not cand_map:
        return "(no candidate elements for this lesson)"
    return "\n\n".join(
        f'[{sid}] ({el.element_type})\n"""\n{(el.excerpt or "")[:600]}\n"""'
        for sid, el in cand_map.items()
    )


# --- GBNF grammar generation (single-line rules; the server rejects multi-line) --


def _lit(s: str) -> str:
    r"""A GBNF terminal for the JSON string literal "s" (with its surrounding JSON
    quotes). In-grammar this must read `"\"s\""`, so we emit exactly those chars."""
    return '"\\"' + s + '\\""'


def _build_grammar(crit_ids: list[str], synth_ids: list[str], max_band: int) -> str:
    """Generate a GBNF grammar that forces:
      - a top-level {"scores": [ ... ]} object of well-formed JSON,
      - each entry's criterion_id ∈ crit_ids,
      - band ∈ 0..max_band,
      - evidence_element_id ∈ synth_ids ∪ {""}  (kills the bogus-id failure mode),
      - evidence_quote / note as ordinary JSON strings.
    The quote's *verbatimness* can't be expressed in GBNF, so we still validate it
    in code and self-heal (that is the point of this experiment)."""
    critid = " | ".join(_lit(c) for c in crit_ids)
    elemid = " | ".join(_lit(s) for s in synth_ids) + " | " + _lit("")
    band = " | ".join(f'"{i}"' for i in range(max_band + 1))
    entry = (
        '"{" ws '
        '"\\"criterion_id\\"" ws ":" ws critid ws "," ws '
        '"\\"band\\"" ws ":" ws band ws "," ws '
        '"\\"evidence_element_id\\"" ws ":" ws elemid ws "," ws '
        '"\\"evidence_quote\\"" ws ":" ws string ws "," ws '
        '"\\"note\\"" ws ":" ws string ws "}"'
    )
    return "\n".join(
        [
            'root ::= "{" ws "\\"scores\\"" ws ":" ws "[" ws entry (ws "," ws entry)* ws "]" ws "}" ws',
            f"entry ::= {entry}",
            f"critid ::= {critid}",
            f"band ::= {band}",
            f"elemid ::= {elemid}",
            'string ::= "\\"" char* "\\""',
            'char ::= [^"\\\\] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
            'ws ::= [ \\t\\n]*',
        ]
    )


# --- prompt building ---------------------------------------------------------


def _build_prompt(
    rubric: dict,
    lesson: LessonInput,
    cand_map: dict[str, object],
    crit_ids: list[str],
    retry_reasons: dict[str, str] | None = None,
) -> str:
    """Build the scoring prompt. On a heal-retry we pass `retry_reasons` so the
    model is told exactly WHICH dimensions failed and WHY (e.g. "quote not found")
    and is re-shown the allowed element ids — a targeted second look, not a reroll."""
    scale = "\n".join(
        f"  {k}: {v}" for k, v in (rubric.get("band_scale") or {}).items()
    )
    by_id = {c["id"]: c for c in rubric["criteria"]}
    crit_block = "\n".join(
        f"- {cid}: {by_id[cid].get('label', cid)} — "
        f"{by_id[cid].get('description', '').strip()}"
        for cid in crit_ids
    )
    ids = ", ".join(crit_ids)
    header = FORCE_CITE_PREAMBLE
    if retry_reasons:
        fixes = "\n".join(f"  - {cid}: {why}" for cid, why in retry_reasons.items())
        header += (
            "\n\nTHIS IS A CORRECTION PASS. Your previous answer for these dimensions "
            "had citations that could NOT be found verbatim in the cited element:\n"
            f"{fixes}\n"
            "Re-score ONLY the dimensions listed below. For each, either copy an EXACT "
            "substring from one of the elements shown, or assign band 0 with an empty "
            "quote."
        )
    return f"""{header}

RUBRIC: {rubric.get('title', rubric['rubric_id'])}
BAND SCALE:
{scale}

CRITERIA to score (one band each):
{crit_block}

LESSON: {lesson.title}
CANDIDATE ELEMENTS (cite by the bracketed id, e.g. E0):
{_present_elements(cand_map)}

Respond with ONLY valid JSON (no markdown, no prose):
{{"scores": [{{"criterion_id": "<one of: {ids}>", "band": <0-{max((rubric.get('band_scale') or {{0: ''}}).keys())}>, "evidence_element_id": "<E-id from the candidates, or empty>", "evidence_quote": "<verbatim substring of that element, or empty>", "note": "<one short sentence>"}}]}}
One entry per criterion listed above."""


# --- the constrained model call ---------------------------------------------


def _grammar_call(
    cfg: dict, prompt: str, grammar: str | None, step: str, retries: int = 2
) -> dict:
    """POST to the analyst endpoint with an optional GBNF `grammar` field, reusing
    the project's cfg (url/model/timeout) and JSON parser. We call the endpoint
    directly (rather than layer1.model_chat) ONLY because model_chat does not plumb
    a `grammar` field through — everything else is reused. Transient errors retry
    with backoff; a 400 with a grammar transparently falls back to no-grammar so a
    grammar hiccup never hard-fails the scorer."""
    url = cfg["models"]["analyst_url"]
    model = cfg["models"]["analyst_model"]
    timeout = cfg["models"].get("timeout_seconds", 300)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
        "repeat_penalty": 1.15,  # same anti-repetition guard model_chat uses
    }
    if grammar:
        payload["grammar"] = grammar

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 400 and "grammar" in payload:
                # Grammar rejected for this input — drop it and let validate+retry
                # carry the correctness load instead of failing the whole lesson.
                log(f"WARN: {step} grammar rejected (400); retrying without grammar")
                payload.pop("grammar", None)
                continue
            resp.raise_for_status()
            return parse_model_json(extract_content(resp.json()), context=step)
        except (requests.ConnectionError, requests.Timeout, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(2**attempt)
        except requests.HTTPError as e:
            last_err = e
            break
    raise RuntimeError(f"{step}: model call failed: {last_err}")


# --- validation --------------------------------------------------------------


def _validate(
    entry: dict, cand_map: dict[str, object], max_band: int
) -> tuple[int | None, Evidence | None, str | None]:
    """Validate one scored dimension.

    Returns (band, evidence_or_None, failure_reason_or_None). A band>0 is only
    accepted when it cites a real E-id AND its quote is a verbatim (whitespace-
    normalized) substring of that element. band==0 needs no evidence."""
    band = entry.get("band")
    band = int(band) if isinstance(band, (int, float)) else None
    if band is None:
        return None, None, "no band returned"
    band = max(0, min(band, max_band))
    if band == 0:
        return 0, None, None
    sid = (entry.get("evidence_element_id") or "").strip()
    quote = (entry.get("evidence_quote") or "").strip()
    el = cand_map.get(sid)
    if el is None:
        return band, None, f"cited id {sid!r} is not a candidate element"
    if not quote:
        return band, None, "band>0 but empty quote"
    if not excerpt_cited_in(quote, el.excerpt or ""):
        return band, None, "quote is not a verbatim substring of the cited element"
    # Store the REAL element id (map back from the synthetic E-id) so the artifact
    # matches every other scorer's evidence shape.
    return band, Evidence(el.element_id, quote), None


# --- the core force-cite band routine ---------------------------------------


def force_cite_band_result(
    lesson: LessonInput,
    rubric: dict,
    scorer_id: str,
    cfg: dict | None,
    use_grammar: bool = True,
) -> ScorerResult:
    """Score every criterion of a band rubric for one lesson with the force-cite
    loop: one grammared call, then heal-retries for only the dimensions whose
    citation failed validation, then honest band-0 fallback for the incurable."""
    max_band = max((rubric.get("band_scale") or {0: ""}).keys())
    result = ScorerResult(
        scorer_id=scorer_id,
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["version"],
        scoring="band",
        lesson_id=lesson.lesson_id,
    )
    all_crit_ids = [c["id"] for c in rubric["criteria"]]
    labels = {c["id"]: c.get("label", c["id"]) for c in rubric["criteria"]}

    if cfg is None:
        result.error = "no model config (offline) — band scorer skipped"
        result.criteria = [
            CriterionResult(cid, labels[cid], "band", note="skipped")
            for cid in all_crit_ids
        ]
        return result

    candidates = _band_candidates(lesson, rubric)
    cand_map = _synthetic_map(candidates)
    synth_ids = list(cand_map.keys())

    # Accumulators across the initial pass + heal retries.
    accepted: dict[str, tuple[int, Evidence | None]] = {}
    reasons: dict[str, str] = {}
    pending = list(all_crit_ids)
    n_calls = 0

    # Pass 0 scores all criteria; each subsequent pass re-asks only what failed.
    for attempt in range(MAX_HEAL_RETRIES + 1):
        if not pending:
            break
        grammar = (
            _build_grammar(pending, synth_ids, max_band) if use_grammar else None
        )
        prompt = _build_prompt(
            rubric,
            lesson,
            cand_map,
            pending,
            retry_reasons={c: reasons[c] for c in pending if c in reasons}
            if attempt > 0
            else None,
        )
        step = f"forcecite-{scorer_id}-{lesson.lesson_id}-p{attempt}"
        try:
            data = _grammar_call(cfg, prompt, grammar, step)
        except Exception as e:  # noqa: BLE001 — degrade cleanly like the shared scorer
            n_calls += 1
            if not accepted:  # total failure on the very first call
                result.error = f"model call failed: {e}"
                result.criteria = [
                    CriterionResult(cid, labels[cid], "band", note="error")
                    for cid in all_crit_ids
                ]
                result.cost = {"model_calls": n_calls}
                return result
            break  # keep whatever we already validated; stop retrying
        n_calls += 1

        scored = {s.get("criterion_id"): s for s in (data.get("scores") or [])}
        still_pending: list[str] = []
        for cid in pending:
            band, ev, why = _validate(scored.get(cid) or {}, cand_map, max_band)
            if why is None:
                accepted[cid] = (band if band is not None else 0, ev)
                reasons.pop(cid, None)
            else:
                reasons[cid] = why
                still_pending.append(cid)
        pending = still_pending

    # Anything still unhealed after the retries is forced to an honest band 0.
    crits: list[CriterionResult] = []
    heal_retries_used = 0
    for cid in all_crit_ids:
        if cid in accepted:
            band, ev = accepted[cid]
            crits.append(
                CriterionResult(
                    cid,
                    labels[cid],
                    "band",
                    band=band,
                    evidence=[ev] if ev else [],
                    note="" if (band == 0 or ev) else "",
                )
            )
        else:
            heal_retries_used += 1
            crits.append(
                CriterionResult(
                    cid,
                    labels[cid],
                    "band",
                    band=0,
                    evidence=[],
                    note=(
                        "[forced band 0 — no verbatim citation after "
                        f"{MAX_HEAL_RETRIES} retries: {reasons.get(cid, 'unknown')}]"
                    ),
                )
            )

    summary = summarize_bands(crits, max_band=max_band)
    summary["forced_zero"] = heal_retries_used  # transparency, not hidden
    result.criteria = crits
    result.summary = summary
    result.cost = {"model_calls": n_calls}
    return result


# --- registered scorers ------------------------------------------------------


class QualityForceCiteScorer(Scorer):
    scorer_id = "s4_quality_forcecite"
    name = "S4 quality (force-cite: grammar + validate + self-heal)"

    def __init__(self) -> None:
        self.rubric = load_rubric(QUALITY_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return force_cite_band_result(lesson, self.rubric, self.scorer_id, cfg)


class UbdForceCiteScorer(Scorer):
    scorer_id = "s2_ubd_forcecite"
    name = "S2 UbD (force-cite: grammar + validate + self-heal)"

    def __init__(self) -> None:
        self.rubric = load_rubric(UBD_RUBRIC)

    def score(self, lesson: LessonInput, cfg: dict | None = None) -> ScorerResult:
        return force_cite_band_result(lesson, self.rubric, self.scorer_id, cfg)


register_scorer(QualityForceCiteScorer)
register_scorer(UbdForceCiteScorer)
