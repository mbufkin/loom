"""Validate model-generated and on-disk YAML/JSON for the crystallization pipeline.

Lightweight structural checks — no external schema library. Fail fast with clear errors.
"""

from __future__ import annotations

import re
from typing import Any

# Artifact roles used in calendars and placement output
ARTIFACT_ROLES = frozenset(
    {
        "lesson_plan",
        "lesson_content",
        "exit_ticket",
        "quiz",
        "answer_key",
        "rubric",
        "worksheet",
        "project_work",
        "presentation",
        "game_activity",
        "lab_activity",
        "flex_day",
        "other",
    }
)

UNIT_ID_RE = re.compile(r"^[a-z0-9.]+(?:-[a-z0-9.]+)*$")
DAY_ID_RE = re.compile(r"^d\d+$")
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})

# Universal instructional-function taxonomy for Layer 0 element decomposition.
# BETS.md Bet 10: working hypothesis, NOT settled — versioned so a future
# retaxonomy is a traceable re-run of Layer 0, not a silent redefinition.
LAYER0_TAXONOMY_VERSION = "v1-hypothesis"
ELEMENT_TYPES = frozenset(
    {
        "hook_engagement",
        "direct_instruction",
        "guided_practice",
        "independent_practice",
        "assessment_checkpoint",
        "reflection_closure",
        "logistics_materials",
        "standards_objectives",
        "unclear",  # first-class "insufficient evidence" answer — Bet 4
    }
)


def raise_on_errors(errors: list[str], context: str) -> None:
    if errors:
        raise ValueError(f"{context}: " + "; ".join(errors))


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_ingest_plan(plan: dict) -> list[str]:
    """Validate Analyst/Verifier JSON before writing manifest + calendars."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be a dict"]

    units = plan.get("units")
    if not isinstance(units, list) or not units:
        errors.append("units must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for i, u in enumerate(units):
        prefix = f"units[{i}]"
        if not isinstance(u, dict):
            errors.append(f"{prefix} must be a dict")
            continue
        uid = u.get("unit_id")
        if not _is_str(uid) or not UNIT_ID_RE.match(uid):
            errors.append(f"{prefix}.unit_id invalid slug: {uid!r}")
        elif uid in seen_ids:
            errors.append(f"duplicate unit_id: {uid}")
        else:
            seen_ids.add(uid)

        files = u.get("source_files")
        if not isinstance(files, list) or not files:
            errors.append(f"{prefix}.source_files must be a non-empty list")
        elif not all(_is_str(f) for f in files):
            errors.append(f"{prefix}.source_files must be strings")

        cal = u.get("calendar")
        if not isinstance(cal, dict):
            errors.append(f"{prefix}.calendar must be a dict")
            continue
        errors.extend(_validate_calendar_body(cal, f"{prefix}.calendar"))

    return errors


def validate_manifest(manifest: dict) -> list[str]:
    """Validate manifest.yaml on disk."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a dict"]

    # Accept either new format (project.id + sources_dir) or flat format (project_id)
    project = manifest.get("project") or {}
    if not _is_str(project.get("id")):
        if not _is_str(manifest.get("project_id")):
            errors.append("project.id (or project_id) required")

    if not _is_str(manifest.get("sources_dir")):
        # sources_dir is optional in flat format — resolve at runtime
        pass

    units = manifest.get("units")
    if not isinstance(units, dict) or not units:
        errors.append("units must be a non-empty mapping")
        return errors

    for uid, entry in units.items():
        prefix = f"units[{uid}]"
        if not UNIT_ID_RE.match(uid):
            errors.append(f"{prefix} key invalid slug")
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a dict")
            continue
        if not _is_str(entry.get("title")):
            errors.append(f"{prefix}.title required")
        if not _is_str(entry.get("calendar")):
            errors.append(f"{prefix}.calendar path required")
        docs = entry.get("documents") or entry.get("source_files")
        if not isinstance(docs, list):
            errors.append(f"{prefix}.documents (or source_files) must be a list")
        elif not all(_is_str(d) for d in docs):
            errors.append(f"{prefix}.documents (or source_files) must be strings")

    # known_overlaps (optional): human-curated pairs of unit ids confirmed to
    # legitimately overlap (docs/BETS.md — the "adjacent discipline, not a filing
    # error" calibration Layer 1's check_placement() consults). Same shallow,
    # shape-only validation discipline as the rest of this function — this only
    # confirms each entry is a real 2-item pair of ids that exist in `units`
    # above, not anything about whether the overlap judgment itself is correct
    # (that's a human call, not something code can validate).
    known_overlaps = manifest.get("known_overlaps")
    if known_overlaps is not None:
        if not isinstance(known_overlaps, list):
            errors.append("known_overlaps must be a list")
        else:
            for i, pair in enumerate(known_overlaps):
                prefix = f"known_overlaps[{i}]"
                if not isinstance(pair, list) or len(pair) != 2:
                    errors.append(f"{prefix} must be a 2-item list of unit ids")
                    continue
                for uid in pair:
                    if not _is_str(uid) or uid not in units:
                        errors.append(f"{prefix} references unknown unit id {uid!r}")

    return errors


def validate_unit_calendar(cal: dict) -> list[str]:
    """Validate units/<id>/calendar.yaml."""
    errors: list[str] = []
    if not isinstance(cal, dict):
        return ["calendar must be a dict"]
    if not _is_str(cal.get("unit_id")):
        errors.append("unit_id required")
    errors.extend(_validate_calendar_body(cal, "calendar"))
    return errors


def _validate_calendar_body(cal: dict, prefix: str) -> list[str]:
    errors: list[str] = []
    days = cal.get("days")
    if not isinstance(days, list) or not days:
        errors.append(f"{prefix}.days must be a non-empty list")
        return errors

    day_ids: set[str] = set()
    for j, day in enumerate(days):
        dp = f"{prefix}.days[{j}]"
        if not isinstance(day, dict):
            errors.append(f"{dp} must be a dict")
            continue
        did = day.get("id")
        if not _is_str(did) or not DAY_ID_RE.match(did):
            errors.append(f"{dp}.id must match d<N>, got {did!r}")
        elif did in day_ids:
            errors.append(f"duplicate day id {did}")
        else:
            day_ids.add(did)

        expected = day.get("expected", [])
        if not isinstance(expected, list):
            errors.append(f"{dp}.expected must be a list")
        else:
            for role in expected:
                if role not in ARTIFACT_ROLES:
                    errors.append(f"{dp}.expected unknown role {role!r}")

    supporting = cal.get("unit_supporting", [])
    if not isinstance(supporting, list):
        errors.append(f"{prefix}.unit_supporting must be a list")
    else:
        for role in supporting:
            if role not in ARTIFACT_ROLES:
                errors.append(f"{prefix}.unit_supporting unknown role {role!r}")

    length = cal.get("unit_length_days")
    if length is not None and (not isinstance(length, int) or length < 1):
        errors.append(f"{prefix}.unit_length_days must be positive int")

    return errors


def validate_placements(data: dict) -> list[str]:
    """Validate place.py model JSON output."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["placements payload must be a dict"]

    # calendar_corrections is optional
    corrections = data.get("calendar_corrections")
    if corrections is not None:
        if not isinstance(corrections, list):
            errors.append("calendar_corrections must be a list")
        else:
            for i, c in enumerate(corrections):
                cp = f"calendar_corrections[{i}]"
                if not isinstance(c, dict):
                    errors.append(f"{cp} must be a dict")
                    continue
                if not _is_str(c.get("type")):
                    errors.append(
                        f"{cp}.type required (add_day|change_role|expand_unit)"
                    )
                if not _is_str(c.get("detail")):
                    errors.append(f"{cp}.detail required (explanation)")

    items = data.get("placements")
    if not isinstance(items, list):
        errors.append("placements must be a list")
        return errors

    for i, p in enumerate(items):
        pp = f"placements[{i}]"
        if not isinstance(p, dict):
            errors.append(f"{pp} must be a dict")
            continue
        if not _is_str(p.get("doc_id")):
            errors.append(f"{pp}.doc_id required")
        slot = p.get("slot")
        if not _is_str(slot):
            errors.append(f"{pp}.slot required")
        elif slot != "unit_supporting" and not DAY_ID_RE.match(slot):
            errors.append(f"{pp}.slot must be d<N> or unit_supporting, got {slot!r}")
        role = p.get("role")
        if role not in ARTIFACT_ROLES:
            errors.append(f"{pp}.role unknown: {role!r}")
        conf = p.get("confidence")
        if conf not in CONFIDENCE_LEVELS:
            errors.append(f"{pp}.confidence must be high|medium|low")
        if not _is_str(p.get("excerpt")):
            errors.append(f"{pp}.excerpt required (citation)")

    notes = data.get("notes", [])
    if notes is not None and not isinstance(notes, list):
        errors.append("notes must be a list")

    return errors


def validate_layer0_elements(data: dict) -> list[str]:
    """Validate a Tier 1/Tier 2 decompose response from layer0.py."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["decompose payload must be a dict"]

    elements = data.get("elements")
    if not isinstance(elements, list):
        errors.append("elements must be a list")
        return errors
    if not elements:
        errors.append(
            "elements must be non-empty — a document with zero elements is a bug, not a valid answer"
        )

    for i, el in enumerate(elements):
        ep = f"elements[{i}]"
        if not isinstance(el, dict):
            errors.append(f"{ep} must be a dict")
            continue
        etype = el.get("element_type")
        if etype not in ELEMENT_TYPES:
            errors.append(f"{ep}.element_type unknown: {etype!r}")
        # Citation is a paragraph RANGE pointer, not generated text — see the
        # "Citation mechanism" / "2026-07-08 update" comments in layer0.py above
        # TIER1_RULES for why a range (not a flat list of numbers) is what's asked
        # for. Schema-level check here is deliberately shallow (both bounds present
        # and are ints); whether the range is actually IN RANGE and non-inverted is
        # checked later in resolve_excerpt(), which has the actual paragraph count
        # and can tell a genuinely invalid range from a valid one.
        start_p, end_p = el.get("excerpt_start_paragraph"), el.get(
            "excerpt_end_paragraph"
        )
        for name, val in (
            ("excerpt_start_paragraph", start_p),
            ("excerpt_end_paragraph", end_p),
        ):
            if not isinstance(val, int) or isinstance(val, bool):
                errors.append(
                    f"{ep}.{name} required (integer paragraph number) — Bet 4"
                )
        if not _is_str(el.get("inferred_position")):
            errors.append(
                f"{ep}.inferred_position required (use 'unknown' if not inferable)"
            )
        if not _is_str(el.get("inferred_timing")):
            errors.append(
                f"{ep}.inferred_timing required (use 'unknown' if not inferable)"
            )
        conf = el.get("confidence")
        if conf not in CONFIDENCE_LEVELS:
            errors.append(f"{ep}.confidence must be high|medium|low")

    doc_conf = data.get("document_confidence")
    if doc_conf not in CONFIDENCE_LEVELS:
        errors.append("document_confidence must be high|medium|low")
    if not isinstance(data.get("escalate_to_tier2"), bool):
        errors.append("escalate_to_tier2 must be a bool")

    return errors


def validate_layer1_placements(data: dict) -> list[str]:
    """Validate a Phase 1 (ORGANIZE) response from layer1.py.

    Deliberately shallow, same division of labor as validate_layer0_elements():
    this only checks the SHAPE (right types, right keys). Whether matched_unit_id/
    matched_day_id are actually in the project's closed vocabulary is a Layer 1-
    specific check (validate_judgment() in layer1.py needs the project's own
    manifest/calendar to know that, which this generic validator doesn't have).
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Phase 1 payload must be a dict"]

    placements = data.get("placements")
    if not isinstance(placements, list):
        errors.append("placements must be a list")
        return errors

    for i, p in enumerate(placements):
        pp = f"placements[{i}]"
        if not isinstance(p, dict):
            errors.append(f"{pp} must be a dict")
            continue
        if not _is_str(p.get("element_id")):
            errors.append(f"{pp}.element_id required (non-empty string)")
        for name in (
            "matched_unit_id",
            "matched_day_id",
            "supporting_quote",
            "reasoning",
        ):
            val = p.get(name)
            if val is not None and not _is_str(val):
                errors.append(
                    f"{pp}.{name} must be a string or null — Bet 4 ('not stated' is valid)"
                )

    return errors


def validate_layer1_fulfillment(data: dict) -> list[str]:
    """Validate a Phase 3 (FULFILL) response from layer1.py."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Phase 3 payload must be a dict"]

    entries = data.get("role_fulfillment")
    if not isinstance(entries, list):
        errors.append("role_fulfillment must be a list")
        return errors

    for i, f in enumerate(entries):
        fp = f"role_fulfillment[{i}]"
        if not isinstance(f, dict):
            errors.append(f"{fp} must be a dict")
            continue
        if not _is_str(f.get("role")):
            errors.append(f"{fp}.role required (non-empty string)")
        fulfilled_by = f.get("fulfilled_by")
        if not isinstance(fulfilled_by, list) or not all(
            _is_str(e) for e in fulfilled_by
        ):
            errors.append(
                f"{fp}.fulfilled_by must be a list of element_id strings (may be empty)"
            )
        if f.get("confidence") not in CONFIDENCE_LEVELS:
            errors.append(f"{fp}.confidence must be high|medium|low")
        if not _is_str(f.get("reasoning")):
            errors.append(f"{fp}.reasoning required (non-empty string)")

    return errors
