#!/usr/bin/env python3
"""
ingest.py — Documents only in. Models organize units + infer calendars → YAML.

You provide: raw curriculum files in sources/
Models produce: manifest.yaml, units/*/calendar.yaml

Then run_project.py audits and renders PDFs. No manual YAML editing required.

school-calendar.yaml is provided by the human (or shared template), not inferred
by this stage — rollup.py reads it to produce dated pacing plans.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import yaml

from audit_lib import (
    BASE_DIR,
    atomic_write,
    check_coverage,
    covered_chars,
    document_parts,
    record_coverage,
    reset_coverage,
    text_pieces,
    iter_source_files,
    load_config,
    log,
    model_chat,
    parse_model_json,
    project_dir,
    scrub_document,
    validate_slug_id,
)
from schema_validate import raise_on_errors, validate_ingest_plan

ORGANIZER_RULES = """
You are a curriculum document organizer and auditor. READ-ONLY.

Tasks:
1. Identify the instructional units the course teaches.
2. Assign every source file to every unit it serves. No file may be left
   unassigned.
3. Infer the instructional calendar for each unit from document text (days, weeks, phases).
4. Define expected artifact types per day (lesson_content, exit_ticket, etc.).

HOW TO ASSIGN FILES (read this twice):
- A unit is a block of instruction that is taught over days. Units come only
  from the instructional content.
- Most documents serve one unit. List them under that unit only.
- Some documents serve the whole course: syllabi, course pacing guides,
  standards alignments, grading policies, equipment or materials inventories,
  course-wide teacher notes. List each of these under EVERY unit it serves.
  Repeating the same filename under several units is correct and expected.
- NEVER create a unit to hold course-level documents. A unit named "course
  overview", "introduction", "pacing" or "general" is wrong -- those documents
  belong to the real units, all of them.
- NEVER create a unit with no instructional days. If a group of files has no
  days to teach, it is not a unit, and those files are course-level.

Why: each unit is audited on its own. A unit that cannot see the pacing guide
is reported as having no pacing, even though the teacher supplied one. Filing a
course-wide document under one unit therefore invents a gap in every other unit.

RULES:
- Use ONLY evidence from the catalog below. Cite source_file when inferring calendar length.
- NEVER invent lesson content or write curriculum materials.
- unit_id: lowercase slug (e.g. engineering, health-science).
- Calendar days: id d1, d2, ...; label from document headings when available.
- If documents mention "Estimated Day(s): N", use N for unit_length_days.
- If documents mention Day 1, Day 2, Day 3, create that many days.
- unit_supporting: artifact types that span the unit (lesson_plan, quiz, answer_key, rubric, worksheet).
- school_calendar_hint: optional top-level year/semester notes found in documents (or null).
"""

ORGANIZE_SCHEMA = """
Respond with ONLY valid JSON (no markdown fences):
{
  "school_calendar_hint": {
    "school_year": "string or null",
    "notes": "string or null",
    "grading_periods": []
  },
  "units": [
    {
      "unit_id": "slug",
      "title": "Human Title",
      "source_files": ["relative/path/from/sources/filename.ext"],
      "calendar": {
        "unit_length_days": 3,
        "days": [
          {"id": "d1", "label": "Day 1 — topic", "expected": ["lesson_content", "exit_ticket"]}
        ],
        "unit_supporting": ["lesson_plan", "quiz"]
      }
    }
  ]
}
Every catalog file must appear in at least one unit's source_files: once if it
serves one unit, once per unit if it serves several. Never twice in the same
unit's list.

WORKED EXAMPLE. A catalog of five files:
  unit-1-lesson-plan.html, unit-1-quiz.html,
  unit-2-lesson-plan.html, unit-2-quiz.html,
  course-pacing-guide.md

Correct -- two units, and the pacing guide listed under BOTH because it
describes both:
  "units": [
    {"unit_id": "...", "source_files": ["unit-1-lesson-plan.html",
                                        "unit-1-quiz.html",
                                        "course-pacing-guide.md"], ...},
    {"unit_id": "...", "source_files": ["unit-2-lesson-plan.html",
                                        "unit-2-quiz.html",
                                        "course-pacing-guide.md"], ...}
  ]

Wrong -- a third unit invented to hold the pacing guide:
  {"unit_id": "course-overview", "source_files": ["course-pacing-guide.md"]}

Wrong -- the pacing guide filed under only the first unit, leaving unit 2
looking as though it has no pacing.
"""


def model_call(
    cfg: dict, role: str, messages: list, step: str, temperature: float = 0.1
) -> dict:
    # enable_thinking=False for the same reason as layer0.model_call and
    # layer1: both organize steps want a JSON object matching ORGANIZE_SCHEMA,
    # not an argument for one. A reasoning model left to think spends the whole
    # output budget on monologue and returns that instead of the plan -- and on
    # NVIDIA's gateway the request does not merely come back wrong, it times out
    # at 504. Observed live on the first in-app organise run: the analyst
    # answered, the verifier retried 504s until it was killed.
    #
    # max_tokens is explicit because this reply scales with the corpus: one
    # object per unit, each listing its files and a day-by-day calendar. The
    # default ceiling is comfortable for six documents and not for sixty, and a
    # plan truncated mid-array fails validate_coverage as "file not assigned",
    # which reads as a model mistake rather than a budget that ran out.
    return model_chat(
        cfg,
        role,
        messages,
        step,
        temperature=temperature,
        max_tokens=16384,
        enable_thinking=False,
    )


def parse_json(text: str, *, step: str = "ingest") -> dict:
    return parse_model_json(text, context=step)


def extract_content(response: dict) -> str:
    return response["choices"][0]["message"]["content"]


def build_catalog(sources: Path) -> tuple[list[dict], list[Path]]:
    paths = iter_source_files(sources)
    if not paths:
        raise FileNotFoundError(
            f"No curriculum files in {sources}. "
            f"Supported: pdf, docx, pptx, xlsx, odt, txt, md, html, rtf, doc (with antiword)"
        )
    records = []
    failed = []
    for p in paths:
        rel = p.relative_to(sources).as_posix()
        ev = scrub_document(p)
        ev["source_file"] = rel  # preserve subfolder path for manifest
        if ev.get("extraction_error"):
            failed.append(f"{p.name}: {ev['extraction_error']}")
        records.append(ev)
    if failed:
        log(f"WARN: {len(failed)} file(s) could not be extracted:")
        for f in failed[:10]:
            log(f"  - {f}")
    usable = [r for r in records if r.get("char_count_clean", 0) > 0]
    if not usable:
        raise FileNotFoundError("No documents produced extractable text")
    return usable, paths


# --- Map: one "document card" per document, read from its FULL text ---------
# Grouping used to see ~200 characters per document, so a unit was decided
# from a title and an opening line. Now every document is read in full first
# (parts above layer0's threshold, merged) into a compact card, and the
# grouping prompt below sees the cards. Cards are cached by content hash so a
# re-organise only re-reads documents that changed.
CARD_VERSION = 1

CARD_ROLES = (
    "lesson_plan", "slides", "student_handout", "student_practice", "assessment",
    "answer_key", "rubric", "project", "syllabus", "pacing_guide",
    "standards_alignment", "teacher_notes", "reference", "other",
)

CARD_RULES = """You are reading ONE curriculum document in full so a course organizer
can group it with the right unit. READ-ONLY: describe only what the text shows;
never invent or write curriculum content.

Read every numbered paragraph ([P<N>]) start to finish. Unit, lesson and day
numbering is often deep in the body, not in the opening -- report it wherever
it appears.
"""

CARD_SCHEMA = """Respond with ONLY valid JSON (no markdown fences):
{
  "topic": "one sentence: what this document teaches or is for",
  "skills": ["main skills or concepts, most important first"],
  "unit_cues": ["unit/module/chapter names or numbers the text states"],
  "sequence_cues": ["lesson/day/week/period markers exactly as written, e.g. 'Day 3'"],
  "day_numbers": [1, 2],
  "lesson_numbers": [4],
  "standards": ["standard codes the text cites"],
  "role": "%s",
  "course_wide": false,
  "references": ["other documents, files or resources the text names"],
  "evidence": [{"claim": "short claim from above", "paragraph": 12}]
}
Keep each list to the items that matter for grouping (about a dozen at most).
course_wide is true only for documents that serve the whole course (syllabus,
pacing guide, standards alignment, policies, inventories).
""" % "|".join(CARD_ROLES)


def _card_prompt(source_file: str, numbered: str, part: int, parts: int) -> str:
    where = (
        f"\nThis is PART {part} of {parts} of the document (it is long, so it is read "
        f"in parts and every part is read). Describe only what is in THIS part.\n"
        if parts > 1
        else ""
    )
    return (
        f"{CARD_RULES}{where}\nSOURCE_FILE: {source_file}\n\nDOCUMENT TEXT:\n"
        f"{numbered}\n\n{CARD_SCHEMA}"
    )


def _uniq(seq) -> list:
    out, seen = [], set()
    for x in seq:
        key = json.dumps(x, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def _ints(raw) -> list[int]:
    out = set()
    for x in raw or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def merge_cards(cards: list[dict]) -> dict:
    """One card from per-part cards: lists unioned in order, numbers unioned,
    role by majority (a specific role beats 'other'), course_wide if any part
    says so. Evidence keeps which part it came from."""
    if len(cards) == 1:
        card = dict(cards[0])
    else:
        roles = [c.get("role") for c in cards if c.get("role") in CARD_ROLES]
        specific = [r for r in roles if r != "other"] or roles or ["other"]
        role = max(dict.fromkeys(specific), key=specific.count)
        topics = _uniq(str(c.get("topic") or "").strip() for c in cards)
        card = {
            "topic": " / ".join(t for t in topics if t),
            "role": role,
            "course_wide": any(bool(c.get("course_wide")) for c in cards),
        }
        for key in ("skills", "unit_cues", "sequence_cues", "standards", "references", "evidence"):
            card[key] = _uniq(x for c in cards for x in (c.get(key) or []))
    for key in ("day_numbers", "lesson_numbers"):
        card[key] = _ints(x for c in cards for x in (c.get(key) or []))
    if card.get("role") not in CARD_ROLES:
        card["role"] = "other"
    return card


def _card_cache_path(cards_dir: Path, text: str) -> Path:
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return cards_dir / f"{digest}-v{CARD_VERSION}.json"


def build_card(cfg: dict, record: dict, root: Path, project_id: str) -> dict:
    """Read one document in full into a card, or reuse its cached card.

    Records coverage for the 'organise' stage from the prompts actually sent:
    every paragraph of the cleaned text must appear in one of them.
    """
    from layer0 import number_paragraphs

    text = record.get("content_clean") or ""
    name = record["source_file"]
    cards_dir = root / "ingest" / "cards"
    cache = _card_cache_path(cards_dir, text)
    if cache.is_file():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
        if cached and cached.get("sent") == cached.get("available"):
            log(f"organise: {name}: read {len(text)} chars in {cached['parts']} part(s) (unchanged, card reused)")
            record_coverage(
                project_id, "organise", name, available=cached["available"],
                sent=cached["sent"], parts=cached["parts"], note="reused", root=root,
            )
            return cached["card"]

    parts = document_parts(text)
    prompts: list[str] = []
    part_cards: list[dict] = []
    for i, part in enumerate(parts, start=1):
        numbered, _ = number_paragraphs(part)
        prompt = _card_prompt(name, numbered, i, len(parts))
        prompts.append(prompt)
        step = f"organise-card-{Path(name).stem}" + (f"-part{i}of{len(parts)}" if len(parts) > 1 else "")
        resp = model_call(cfg, "analyst", [{"role": "user", "content": prompt}], step)
        card = parse_json(extract_content(resp), step=step)
        if not isinstance(card, dict):
            raise ValueError(f"{name}: document card for part {i} was not a JSON object")
        for ev in card.get("evidence") or []:
            if isinstance(ev, dict) and len(parts) > 1:
                ev["part"] = i
        part_cards.append(card)
    card = merge_cards(part_cards)

    available = sum(len(p) for p in text_pieces(text))
    sent = covered_chars(text_pieces(text), prompts)
    log(f"organise: {name}: read {len(text)} chars in {len(parts)} part(s)")
    record_coverage(
        project_id, "organise", name, available=available, sent=sent, parts=len(parts), root=root
    )
    if sent == available:
        cards_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(cache, json.dumps(
            {"source_file": name, "parts": len(parts), "available": available,
             "sent": sent, "card": card}, indent=2, ensure_ascii=False))
    return card


def build_cards(cfg: dict, records: list[dict], root: Path, project_id: str) -> None:
    """Attach a full-text card to every record (record['card'])."""
    reset_coverage(project_id, "organise", root=root)
    for r in records:
        r["card"] = build_card(cfg, r, root, project_id)
    check_coverage(project_id, "organise", "organise", root=root)


# --- Reduce: the grouping prompts read the cards ----------------------------


def catalog_block(records: list[dict]) -> str:
    lines = []
    for r in records:
        line = (
            f"- {r['source_file']} | fmt={r.get('source_format','?')} | type={r['doc_type']} | "
            f"days={r['day_hints']} | len_hint={r.get('unit_length_days_hint')} | "
            f"title={r['title']!r}"
        )
        if r.get("card"):
            line += "\n  card: " + json.dumps(r["card"], ensure_ascii=False, separators=(",", ":"))
        lines.append(line)
    return "\n".join(lines)


def analyst_organize(cfg: dict, records: list[dict]) -> dict:
    prompt = f"""{ORGANIZER_RULES}

DOCUMENT CATALOG ({len(records)} files):
{catalog_block(records)}

{ORGANIZE_SCHEMA}
"""
    resp = model_call(
        cfg, "analyst", [{"role": "user", "content": prompt}], "ingest-analyst"
    )
    return parse_json(extract_content(resp), step="ingest-analyst")


def verifier_organize(cfg: dict, records: list[dict], draft: dict) -> dict:
    prompt = f"""{ORGANIZER_RULES}

Verify and correct the Analyst's organization. Every catalog file must be assigned once.
Remove calendar days not supported by the document cards. Fix unit groupings if wrong.

CATALOG:
{catalog_block(records)}

ANALYST OUTPUT:
{json.dumps(draft, indent=2)}

{ORGANIZE_SCHEMA}
"""
    resp = model_call(
        cfg,
        "verifier",
        [{"role": "user", "content": prompt}],
        "ingest-verifier",
        temperature=0.0,
    )
    return parse_json(extract_content(resp), step="ingest-verifier")


def _filename_key(name: str) -> str:
    """Collapse a filename to what survives a model retyping it."""
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _digits(name: str) -> list[str]:
    """Every run of digits in a filename, in order.

    Module and volume numbers live here, and they are the one part of a
    curriculum filename that must never be matched approximately: "Volume 1
    Module 1" and "Volume 1 Module 2" differ by a single character in forty and
    score 0.98 on any string similarity worth using. Requiring the digits to be
    identical is what separates a dropped word from a different module.
    """
    return re.findall(r"\d+", name)


def reconcile_source_files(records: list[dict], plan: dict) -> list[str]:
    """Snap the plan's filenames back onto the real ones, and say what moved.

    The organiser is handed a catalog of filenames and asked to group them, so
    every name in its reply should be a name it was given. In practice it
    retypes them, and a retyped identifier drifts: on the Bluebonnet Algebra I
    corpus it returned "150-Day_Topic_Pacing_Guides" for a file called
    "150-day_Topic_Pacing_Guides", and dropped a word from
    "Student_Edition_Course_Guide". Both documents exist and both were correctly
    grouped -- the plan was rejected over capitalisation and a missing word.

    This is the same stance Layer 0 takes on citations: when the authoritative
    list is already in hand, never let a model's transcription of it be the
    thing that decides. Matching goes exact, then case- and
    punctuation-insensitive, then near-miss for a dropped or added word -- and
    anything still unmatched is left untouched so validate_coverage reports it
    as the real problem it may be.

    Every tier refuses to guess. A near-miss is accepted only when it is the
    single candidate above the threshold and its module and volume numbers match
    exactly, because the cost of being wrong here is evidence attributed to the
    wrong unit, which no later stage can detect.
    """
    catalog = [r["source_file"] for r in records]
    exact = set(catalog)
    folded: dict[str, list[str]] = {}
    for name in catalog:
        folded.setdefault(_filename_key(name), []).append(name)

    corrections: list[str] = []
    for unit in plan.get("units", []):
        files = unit.get("source_files") or []
        for i, given in enumerate(files):
            if given in exact:
                continue
            match = _resolve_filename(given, folded)
            if match:
                files[i] = match
                corrections.append(f"{given} -> {match}")
    return corrections


# How close a retyped filename must be to the real one. 0.85 admits a dropped
# word such as "Student_Course_Guide" for "Student_Edition_Course_Guide" (0.90)
# while excluding documents that merely share a long prefix.
FILENAME_MATCH_CUTOFF = 0.85


def _resolve_filename(given: str, folded: dict[str, list[str]]) -> str | None:
    """The one real filename `given` refers to, or None if that is not certain."""
    key = _filename_key(given)

    # Case and punctuation only: the plan said 150-Day, the file says 150-day.
    candidates = folded.get(key, [])
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return None  # two files differing only in punctuation: show the human

    near = difflib.get_close_matches(
        key, list(folded), n=3, cutoff=FILENAME_MATCH_CUTOFF
    )
    if len(near) != 1:
        return None
    hits = folded[near[0]]
    if len(hits) != 1:
        return None
    if _digits(given) != _digits(hits[0]):
        return None
    return hits[0]


def dedupe_source_files(plan: dict) -> list[str]:
    """Collapse a document listed more than once inside one unit, and say which.

    Listing a file twice under the same unit carries no information that listing
    it once does not -- the unit either draws on that document or it does not.
    So this is a transcription artifact, and the right response is to repair it
    rather than to stop the run, which is what validate_coverage would do.

    Note the deliberate narrowness: this only touches repeats *within* one unit.
    The same document appearing under several units is the normal and intended
    way a course-level pacing guide or standards alignment is represented, and
    collapsing that would destroy real structure.
    """
    collapsed: list[str] = []
    for unit in plan.get("units", []):
        files = unit.get("source_files") or []
        # dict.fromkeys keeps first-seen order, so the plan stays in the sequence
        # the organiser chose instead of being silently re-sorted.
        unique = list(dict.fromkeys(files))
        if len(unique) != len(files):
            collapsed.extend(f for f in unique if files.count(f) > 1)
            unit["source_files"] = unique
    return sorted(set(collapsed))


def validate_coverage(records: list[dict], plan: dict) -> list[str]:
    """Deterministic check: every file assigned at least once, and no file listed
    twice within the same unit.

    "At least once" rather than "exactly once" because a document can serve more
    than one unit, and the same file appearing under two units is how the plan
    says so. Repeating it inside ONE unit still means nothing and is still
    rejected -- that is either a model slip or a truncated reply, and letting it
    through would double-count the document's evidence for that unit.
    """
    errors = []
    catalog = {r["source_file"] for r in records}
    assigned: list[str] = []
    repeated_in_one_unit: set[str] = set()
    for u in plan.get("units", []):
        files = u.get("source_files") or []
        assigned.extend(files)
        repeated_in_one_unit |= {f for f in files if files.count(f) > 1}

    missing = catalog - set(assigned)
    extra = set(assigned) - catalog

    if missing:
        shown = sorted(missing)[:5]
        errors.append(
            f"unassigned files: {shown}{'...' if len(missing) > 5 else ''}. "
            "Every document must be listed under at least one unit. A document "
            "that serves the whole course -- a syllabus, pacing guide, standards "
            "alignment or equipment list -- goes under every unit it serves"
        )
    if extra:
        errors.append(f"unknown files in plan: {sorted(extra)[:5]}")
    if repeated_in_one_unit:
        errors.append(
            f"listed twice in the same unit: {sorted(repeated_in_one_unit)[:5]}"
        )
    if not plan.get("units"):
        errors.append("no units in plan")
    return errors


def share_unplaced_documents(records: list[dict], plan: dict) -> list[str]:
    """Place any document the organiser left out under every unit, and say which.

    A document the organiser finished its plan without putting in any unit is,
    by that fact alone, not specific to a unit -- which is the definition of a
    course-level document. Sharing it across every unit is what the plan should
    have said, so this fills it in rather than stopping the audit.

    This is safe to do deterministically because a short reply cannot reach
    here. model_chat rejects a reply whose finish_reason is "length" and retries
    with a larger ceiling (see _unusable_reply), so a plan arriving at this
    point is one the model chose to end. Leftovers are its judgment, not a
    truncated tail -- which matters, because silently spreading the missing half
    of a cut-off plan across two surviving units would corrupt the organisation
    while looking orderly.

    Prompt instructions alone did not achieve this. Told plainly to list
    course-wide documents under every unit, with a worked example, a capable
    hosted model still shared a pacing guide and teacher notes correctly while
    refusing to place a shop equipment inventory anywhere -- it does not read an
    asset register as instructional material. Failing the whole run over that
    one file is the dead end this replaces: the inventory is exactly the kind of
    course-level document a unit's audit should see, since it is what says
    whether the unit can be taught at all.
    """
    units = plan.get("units") or []
    if not units:
        return []
    assigned = {f for u in units for f in (u.get("source_files") or [])}
    unplaced = sorted({r["source_file"] for r in records} - assigned)
    if not unplaced:
        return []
    for unit in units:
        unit["source_files"] = list(unit.get("source_files") or []) + unplaced
    return unplaced


# --- repair, then deterministic cleanup ---------------------------------------
#
# Observed live on a course of 18 documents: the verifier wrote documents'
# in-file *titles* where their filenames belonged ("Unit Overview.docx" for a
# file called "Unit Overview Lesson Plan.docx"), and gave one unit no days. The near-miss matcher rightly refused to guess those
# names, and the whole organise failed on validation.
#
# The response is in two layers. First one repair round: the same verifier is
# shown the exact catalog filenames and the exact errors, and asked to fix only
# that. Then a deterministic cleanup that never guesses -- it removes what is
# still wrong and says so in the run log -- so a single bad unit no longer sinks
# a whole curriculum. Only a plan with nothing usable left fails.

# What a unit gets when the organiser gave it documents but no days. The same
# shape _deterministic_plan uses, so it audits like any one-day unit.
DEFAULT_DAY = {"id": "d1", "label": "Day 1", "expected": ["lesson_content", "exit_ticket"]}


def _unknown_files(records: list[dict], plan: dict) -> list[str]:
    catalog = {r["source_file"] for r in records}
    named = {
        f for u in plan.get("units") or [] for f in (u.get("source_files") or [])
        if isinstance(f, str)
    }
    return sorted(named - catalog)


def plan_problems(records: list[dict], plan: dict) -> list[str]:
    """What a repair round should be asked to fix: invented filenames and
    structural errors.

    Unplaced documents are deliberately not in this list: share_unplaced_documents
    already turns those into course-level documents, which is the intended
    behaviour, not a mistake to send back to the model.
    """
    problems: list[str] = []
    unknown = _unknown_files(records, plan)
    if unknown:
        problems.append(f"unknown files in plan (not in the catalog): {unknown}")
    problems.extend(validate_ingest_plan(plan))
    return problems


def repair_prompt(records: list[dict], plan: dict, problems: list[str]) -> str:
    """The one repair request. Exact names and exact errors, nothing vaguer:
    "use the catalog filenames" was already in the first prompt and not enough."""
    names = "\n".join(f"  {r['source_file']}" for r in records)
    errors = "\n".join(f"  - {p}" for p in problems)
    return f"""{ORGANIZER_RULES}

Your organization below failed validation. Fix ONLY these problems:
{errors}

The ONLY valid filenames are these {len(records)}, character for character.
Use them exactly as written. Do not use a document's title as its filename, and
do not shorten, retype or invent a name. A file you cannot place in a unit may be
left out; it will be shared with every unit as a course-level document.
{names}

Every unit must have at least one calendar day. A group of files with no days to
teach is not a unit: remove that unit and leave its files out.

CATALOG (titles and document cards, for context only -- filenames come from the list
above):
{catalog_block(records)}

YOUR PREVIOUS OUTPUT:
{json.dumps(plan, indent=2)}

{ORGANIZE_SCHEMA}
"""


def verifier_repair(
    cfg: dict, records: list[dict], plan: dict, problems: list[str]
) -> dict:
    """Ask the verifier, with the same settings, to fix the listed problems."""
    resp = model_call(
        cfg,
        "verifier",
        [{"role": "user", "content": repair_prompt(records, plan, problems)}],
        "ingest-repair",
        temperature=0.0,
    )
    return parse_json(extract_content(resp), step="ingest-repair")


def clean_plan(records: list[dict], plan: dict) -> list[str]:
    """Remove what is still wrong after repair, and return a WARN line for each
    change. Never maps a name to a file: guessing which document an invented
    name meant would attribute evidence to the wrong unit, invisibly.

    - a filename not in the catalog is dropped from its unit;
    - a unit with documents but no days gets one default day;
    - a unit with no documents left is removed. Its days alone are nothing to
      audit, and any real files it lost are still shared below as course-level
      documents, so no evidence is lost by removing it.
    """
    catalog = {r["source_file"] for r in records}
    warnings: list[str] = []
    kept: list[dict] = []
    for unit in plan.get("units") or []:
        if not isinstance(unit, dict):
            warnings.append(f"removed a unit that was not an object: {unit!r:.80}")
            continue
        uid = unit.get("unit_id") or "(no id)"
        files = unit.get("source_files") or []
        if not isinstance(files, list):
            files = []
        good = []
        for f in files:
            if f in catalog:
                good.append(f)
            else:
                warnings.append(
                    f"dropped {f!r} from unit {uid}: no document by that name "
                    f"in this curriculum"
                )
        unit["source_files"] = good

        cal = unit.get("calendar")
        if not isinstance(cal, dict):
            cal = {}
            unit["calendar"] = cal
        has_days = isinstance(cal.get("days"), list) and bool(cal["days"])

        if not good:
            warnings.append(
                f"removed unit {uid}: none of its documents are in this "
                f"curriculum" + (" (it had days but nothing to audit)" if has_days else "")
            )
            continue
        if not has_days:
            cal["days"] = [dict(DEFAULT_DAY)]
            length = cal.get("unit_length_days")
            if not isinstance(length, int) or length < 1:
                cal["unit_length_days"] = 1
            warnings.append(
                f"unit {uid} had no calendar days; gave it one default day (d1)"
            )
        kept.append(unit)
    plan["units"] = kept
    return warnings


def _match_names(records: list[dict], plan: dict) -> None:
    """Snap retyped filenames onto real ones, then collapse in-unit repeats."""
    # Before anything reasons about which files are missing: a mistyped name
    # looks exactly like an unplaced document, and share_unplaced_documents
    # would then "helpfully" share a file that was already correctly grouped.
    corrected = reconcile_source_files(records, plan)
    if corrected:
        log(f"filename match: {', '.join(corrected)}")

    # After matching, not before: two mistyped spellings of one filename become
    # a duplicate only once they have both been snapped onto the real name.
    collapsed = dedupe_source_files(plan)
    if collapsed:
        log(f"listed more than once in a unit, collapsed: {', '.join(collapsed)}")


def settle_plan(records: list[dict], plan: dict, repair=None) -> dict:
    """Take the organiser's plan to one that validates, or fail saying why.

    `repair(plan, problems) -> plan` is called at most once, and only when
    matching leaves invented filenames or structural errors. None skips it (the
    offline --skip-models path, and tests that want cleanup alone).
    """
    _match_names(records, plan)

    problems = plan_problems(records, plan)
    if problems and repair is not None:
        log(
            "WARN: the organisation has problems; asking the verifier once "
            f"to fix: {'; '.join(problems)}"
        )
        try:
            repaired = repair(plan, problems)
        except Exception as e:  # noqa: BLE001 - any failure here falls back to cleanup
            # A failed repair is not a failed organise: the cleanup below can
            # still salvage the original plan, so carry on with that.
            log(
                f"WARN: the repair attempt failed ({e}); cleaning up the "
                "original organisation instead"
            )
        else:
            # A reply with no units would only make things worse; keep the
            # original, whose good units cleanup can still save.
            if isinstance(repaired, dict) and isinstance(repaired.get("units"), list) and repaired["units"]:
                plan = repaired
                _match_names(records, plan)
            else:
                log(
                    "WARN: the repair attempt returned no units; cleaning up "
                    "the original organisation instead"
                )

    for line in clean_plan(records, plan):
        log(f"WARN: {line}")

    if not plan.get("units"):
        raise ValueError(
            "Organising found no usable units: every unit the organiser proposed "
            "named documents that are not in this curriculum. The WARN lines "
            "above list each name it used. Organising again often works; if it "
            "keeps happening, check the documents open and have readable text."
        )

    shared = share_unplaced_documents(records, plan)
    if shared:
        # ASCII only: the logging handler on Windows encodes as cp1252 and
        # raises on an em-dash, which turns an informational line into a stack
        # trace in the run log.
        log(
            f"course-level: {', '.join(shared)} - placed in no unit by the "
            "organiser, so shared across all of them"
        )

    errors = validate_coverage(records, plan)
    errors.extend(validate_ingest_plan(plan))
    raise_on_errors(errors, "Ingest validation")
    return plan


def write_yaml_files(project_id: str, sources: Path, plan: dict) -> None:
    root = project_dir(project_id)
    units_dir = root / "units"
    units_dir.mkdir(parents=True, exist_ok=True)

    manifest_units = {}
    for u in plan["units"]:
        uid = u["unit_id"]
        cal = u["calendar"]
        cal_doc = {
            "unit_id": uid,
            "title": u.get("title", uid),
            "unit_length_days": cal.get("unit_length_days", len(cal.get("days", []))),
            "days": cal.get("days", []),
            "unit_supporting": cal.get("unit_supporting", []),
        }
        cal_path = units_dir / uid / "calendar.yaml"
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cal_path, "w") as f:
            yaml.dump(cal_doc, f, default_flow_style=False, sort_keys=False)
        manifest_units[uid] = {
            "title": u.get("title", uid),
            "calendar": f"units/{uid}/calendar.yaml",
            "documents": sorted(u.get("source_files", [])),
        }

    manifest = {
        "project": {"id": project_id, "name": plan.get("project_name", project_id)},
        "sources_dir": str(sources.resolve()),
        "units": manifest_units,
        "generated_by": "ingest.py",
    }
    with open(root / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    hint = plan.get("school_calendar_hint") or {}
    school_cal = {
        "school_year": hint.get("school_year"),
        "notes": hint.get("notes"),
        "grading_periods": hint.get("grading_periods", []),
        "units": [
            {"unit_id": u["unit_id"], "title": u.get("title")} for u in plan["units"]
        ],
    }
    with open(root / "school-calendar.yaml", "w") as f:
        yaml.dump(school_cal, f, default_flow_style=False, sort_keys=False)


def ingest(project_id: str, sources: Path, skip_models: bool = False) -> Path:
    root = project_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    ingest_dir = root / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = ingest_dir / ".raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    records, _paths = build_catalog(sources)
    atomic_write(ingest_dir / "catalog.json", json.dumps(records, indent=2))
    log(f"catalog: {len(records)} documents from {sources}")

    repair = None
    if skip_models:
        # Deterministic fallback: one unit per unique top-level token in filename
        plan = _deterministic_plan(records)
    else:
        cfg = load_config()
        log(f"Reading all {len(records)} documents in full...")
        build_cards(cfg, records, root, project_id)
        atomic_write(ingest_dir / "cards.json", json.dumps(
            {r["source_file"]: r["card"] for r in records}, indent=2, ensure_ascii=False))
        log("Analyst organizing documents + inferring calendars...")
        draft = analyst_organize(cfg, records)
        atomic_write(raw_dir / "organize-analyst.json", json.dumps(draft, indent=2))
        log("Verifier validating organization...")
        final = verifier_organize(cfg, records, draft)
        atomic_write(raw_dir / "organize-verifier.json", json.dumps(final, indent=2))
        plan = final

        def repair(bad: dict, problems: list[str]) -> dict:
            fixed = verifier_repair(cfg, records, bad, problems)
            atomic_write(raw_dir / "organize-repair.json", json.dumps(fixed, indent=2))
            return fixed

    plan = settle_plan(records, plan, repair=repair)

    write_yaml_files(project_id, sources, plan)
    log(f"wrote manifest.yaml + {len(plan['units'])} unit calendars → {root}")
    return root


def _deterministic_plan(records: list[dict]) -> dict:
    """Offline fallback: one unit 'curriculum' with all docs, calendar from day hints."""
    max_day = 1
    for r in records:
        if r.get("day_hints"):
            max_day = max(max_day, max(r["day_hints"]))
        if r.get("unit_length_days_hint"):
            max_day = max(max_day, r["unit_length_days_hint"])
    days = [
        {
            "id": f"d{d}",
            "label": f"Day {d}",
            "expected": ["lesson_content", "exit_ticket"],
        }
        for d in range(1, max_day + 1)
    ]
    return {
        "school_calendar_hint": None,
        "units": [
            {
                "unit_id": "curriculum",
                "title": "Curriculum",
                "source_files": [r["source_file"] for r in records],
                "calendar": {
                    "unit_length_days": max_day,
                    "days": days,
                    "unit_supporting": [
                        "lesson_plan",
                        "quiz",
                        "answer_key",
                        "rubric",
                        "worksheet",
                    ],
                },
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Organize docs + infer calendars → YAML"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--sources", type=Path, help="Folder of curriculum files (any supported type)"
    )
    parser.add_argument("--skip-models", action="store_true")
    args = parser.parse_args()

    sources = args.sources or (project_dir(args.project) / "sources")
    if not sources.is_dir():
        log(f"ERROR: sources not found: {sources}")
        log("Create projects/<id>/sources/ and drop curriculum documents there.")
        return 2

    try:
        validate_slug_id(args.project, "project id")
        ingest(args.project, sources, skip_models=args.skip_models)
    except ValueError as e:
        log(f"ERROR: {e}")
        return 2
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
