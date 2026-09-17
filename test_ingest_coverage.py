#!/usr/bin/env python3
"""Tests for ingest's deterministic coverage check.

This check is the gate between the organiser's plan and the rest of the audit.
It has to catch a plan that quietly lost a document -- a reply truncated
mid-array looks exactly like a model that chose to leave a file out -- without
rejecting the plans that are correct.

The rule it enforces is "every document appears under at least one unit, and
never twice under the same one". It used to be "exactly once", which made
course-level documents impossible to express: a pacing guide covering two units
had to be filed under one of them, and the other unit then reported its pacing
as missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from ingest import share_unplaced_documents, validate_coverage

CORPUS = [
    "unit-1-smaw-lesson-plan.html",
    "unit-2-oxyfuel-lesson-plan.html",
    "course-pacing-guide.md",
]
RECORDS = [{"source_file": name} for name in CORPUS]


def _plan(*units: list[str]) -> dict:
    return {
        "units": [
            {"unit_id": f"u{i}", "title": f"Unit {i}", "source_files": files}
            for i, files in enumerate(units, start=1)
        ]
    }


def test_a_document_in_one_unit_each_is_accepted() -> None:
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )
    assert validate_coverage(RECORDS, plan) == []


def test_a_course_level_document_may_be_shared_by_every_unit() -> None:
    """
    The case the old "exactly once" rule made impossible. A pacing guide that
    describes both units belongs to both, because each unit's audit has to be
    able to see its own pacing.
    """
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html", "course-pacing-guide.md"],
    )
    assert validate_coverage(RECORDS, plan) == []


def test_a_document_left_out_entirely_is_still_refused() -> None:
    """
    Sharing widens what a valid plan looks like; it does not stop the check
    noticing a lost document. This is the truncated-reply case, and silently
    dropping the file would mean auditing a curriculum without it.
    """
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html"], ["unit-2-oxyfuel-lesson-plan.html"]
    )
    errors = validate_coverage(RECORDS, plan)
    assert len(errors) == 1
    assert "course-pacing-guide.md" in errors[0]
    # The message has to say what to do about it. "unassigned files: [...]" on
    # its own is a dead end for whoever reads the run log.
    assert "at least one unit" in errors[0]
    assert "every unit it serves" in errors[0]


def test_the_same_document_twice_in_one_unit_is_refused() -> None:
    """
    Repeating a file inside a single unit says nothing, and would double-count
    that document's evidence for the unit. Sharing across units is the only
    repetition that carries meaning.
    """
    plan = _plan(
        [
            "unit-1-smaw-lesson-plan.html",
            "unit-1-smaw-lesson-plan.html",
            "course-pacing-guide.md",
        ],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )
    errors = validate_coverage(RECORDS, plan)
    assert len(errors) == 1
    assert "listed twice in the same unit" in errors[0]
    assert "unit-1-smaw-lesson-plan.html" in errors[0]


def test_a_file_the_catalog_never_had_is_refused() -> None:
    """Guards against an invented filename, which would cite evidence that does
    not exist."""
    plan = _plan(
        [
            "unit-1-smaw-lesson-plan.html",
            "course-pacing-guide.md",
            "unit-3-brazing-lesson-plan.html",
        ],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )
    errors = validate_coverage(RECORDS, plan)
    assert any("unknown files in plan" in e for e in errors)
    assert any("unit-3-brazing-lesson-plan.html" in e for e in errors)


def test_a_plan_with_no_units_is_refused() -> None:
    assert any("no units" in e for e in validate_coverage(RECORDS, {"units": []}))


def test_a_unit_with_no_files_does_not_crash_the_check() -> None:
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html"],
        [],
    )
    assert validate_coverage(RECORDS, plan) == []


def test_a_null_file_list_is_treated_as_empty() -> None:
    plan = {
        "units": [
            {"unit_id": "u1", "source_files": CORPUS},
            {"unit_id": "u2", "source_files": None},
        ]
    }
    assert validate_coverage(RECORDS, plan) == []


# --- the backstop for documents the organiser would not place ---------------


def test_a_document_placed_nowhere_is_shared_with_every_unit() -> None:
    """
    Observed live: a capable hosted model shared a pacing guide and teacher
    notes across both units correctly, then refused to place a shop equipment
    inventory in either. A document it declined to attach to any unit is not
    unit-specific, which is what course-level means.
    """
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html"], ["unit-2-oxyfuel-lesson-plan.html"]
    )
    assert share_unplaced_documents(RECORDS, plan) == ["course-pacing-guide.md"]
    for unit in plan["units"]:
        assert "course-pacing-guide.md" in unit["source_files"]
    # And the plan it produces is one the coverage check accepts.
    assert validate_coverage(RECORDS, plan) == []


def test_a_complete_plan_is_left_exactly_as_it_was() -> None:
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html", "course-pacing-guide.md"],
    )
    before = [list(u["source_files"]) for u in plan["units"]]
    assert share_unplaced_documents(RECORDS, plan) == []
    assert [u["source_files"] for u in plan["units"]] == before


def test_nothing_is_shared_when_there_are_no_units_to_share_with() -> None:
    """A plan with no units is a failure to report, not something to repair."""
    plan = {"units": []}
    assert share_unplaced_documents(RECORDS, plan) == []
    assert any("no units" in e for e in validate_coverage(RECORDS, plan))


def test_sharing_does_not_duplicate_within_a_unit() -> None:
    """
    The file is added only to units that lack it -- it cannot be unplaced and
    already present, but the result still has to survive the same-unit
    duplicate rule.
    """
    plan = _plan(["unit-1-smaw-lesson-plan.html"], ["unit-2-oxyfuel-lesson-plan.html"])
    share_unplaced_documents(RECORDS, plan)
    assert validate_coverage(RECORDS, plan) == []
    for unit in plan["units"]:
        files = unit["source_files"]
        assert len(files) == len(set(files))


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    for fn in TESTS:
        fn()
        print(f"OK {fn.__name__}")
    print(f"ALL {len(TESTS)} ingest coverage TESTS PASSED")
