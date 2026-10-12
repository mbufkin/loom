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

from ingest import (
    reconcile_source_files,
    dedupe_source_files,
    share_unplaced_documents,
    validate_coverage,
)

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


# --- filename reconciliation ------------------------------------------------
# The organiser is given a catalog of filenames and asked to group them, so
# every name in its reply should be one it was handed. It retypes them instead,
# and a retyped identifier drifts. Found on the Bluebonnet Algebra I corpus: a
# plan that had grouped all thirteen documents correctly was rejected because
# one name came back "150-Day" where the file says "150-day", and another lost
# the word "Edition".


def test_a_name_that_differs_only_by_case_is_matched() -> None:
    """The exact failure that stopped the Bluebonnet run."""
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "Course-Pacing-Guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )

    corrections = reconcile_source_files(RECORDS, plan)

    assert corrections == ["Course-Pacing-Guide.md -> course-pacing-guide.md"]
    assert validate_coverage(RECORDS, plan) == []


def test_a_name_that_differs_by_punctuation_is_matched() -> None:
    """Underscores for hyphens, or a dropped separator, are the same document."""
    plan = _plan(
        ["unit_1_smaw_lesson_plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )

    reconcile_source_files(RECORDS, plan)

    assert validate_coverage(RECORDS, plan) == []


def test_a_name_that_matches_nothing_is_left_alone() -> None:
    """Reconciliation must not paper over a document that really is absent.

    The plan names a file that was never in the catalog, which is a genuine
    problem and has to reach the human as one.
    """
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "invented-document.pdf"],
        ["unit-2-oxyfuel-lesson-plan.html", "course-pacing-guide.md"],
    )

    corrections = reconcile_source_files(RECORDS, plan)

    assert corrections == []
    errors = validate_coverage(RECORDS, plan)
    assert any("invented-document.pdf" in e for e in errors)


def test_an_ambiguous_name_is_not_guessed() -> None:
    """Two files differing only by punctuation are a problem to show, not solve.

    Picking one would silently attribute evidence to whichever sorted first.
    """
    records = [{"source_file": "guide-1.md"}, {"source_file": "guide_1.md"}]
    plan = _plan(["Guide 1.md"])

    corrections = reconcile_source_files(records, plan)

    assert corrections == []


def test_an_already_correct_plan_is_not_rewritten() -> None:
    """No corrections to report when the organiser copied the names faithfully."""
    plan = _plan(
        ["unit-1-smaw-lesson-plan.html", "course-pacing-guide.md"],
        ["unit-2-oxyfuel-lesson-plan.html"],
    )

    assert reconcile_source_files(RECORDS, plan) == []

def test_a_dropped_word_is_matched() -> None:
    """The second Bluebonnet failure: "Edition" vanished from the middle.

    The document existed and was grouped correctly; the plan was rejected over
    one missing word.
    """
    records = [
        {"source_file": "Algebra_I_Math_Student_Edition_Course_Guide.pdf"},
        {"source_file": "Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf"},
    ]
    plan = _plan(
        [
            "Algebra_I_Math_Student_Course_Guide.pdf",
            "Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf",
        ]
    )

    corrections = reconcile_source_files(records, plan)

    assert corrections == [
        "Algebra_I_Math_Student_Course_Guide.pdf -> "
        "Algebra_I_Math_Student_Edition_Course_Guide.pdf"
    ]
    assert validate_coverage(records, plan) == []


def test_a_different_module_number_is_never_matched() -> None:
    """The dangerous case that makes fuzzy matching tempting to get wrong.

    "Volume 1 Module 2" and "Volume 1 Module 3" differ by one character in
    forty and score about 0.98 on string similarity. Accepting that would file
    one module's teacher edition as another's, attributing evidence to the wrong
    unit in a way no later stage can detect.
    """
    records = [
        {"source_file": "Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf"},
        {"source_file": "Algebra_I_Math_Teacher_Edition_Volume_1_Module_2.pdf"},
    ]
    plan = _plan(["Algebra_I_Math_Teacher_Edition_Volume_1_Module_3.pdf"])

    corrections = reconcile_source_files(records, plan)

    assert corrections == []
    errors = validate_coverage(records, plan)
    assert any("Module_3" in e for e in errors)


def test_a_volume_number_must_also_agree() -> None:
    """Same guard, one level up: volume 2 module 1 is not volume 1 module 1."""
    records = [{"source_file": "Teacher_Edition_Volume_1_Module_1.pdf"}]
    plan = _plan(["Teacher_Edition_Volume_2_Module_1.pdf"])

    assert reconcile_source_files(records, plan) == []


def test_two_plausible_near_matches_are_refused() -> None:
    """When more than one real file is close enough, the human decides."""
    records = [
        {"source_file": "lesson-plan-unit-one.pdf"},
        {"source_file": "lesson-plan-unit-ones.pdf"},
    ]
    plan = _plan(["lesson-plan-unit-onex.pdf"])

    assert reconcile_source_files(records, plan) == []

def test_a_duplicate_inside_one_unit_is_collapsed() -> None:
    """The third Bluebonnet failure: the organiser listed one file twice.

    Both units repeated the standards overview. That says nothing the single
    listing did not, so the run should repair it rather than stop.
    """
    plan = {
        "units": [
            {"unit_id": "m1", "source_files": ["a.pdf", "standards.pdf",
                                               "b.pdf", "standards.pdf"]},
            {"unit_id": "m2", "source_files": ["standards.pdf", "c.pdf"]},
        ]
    }

    collapsed = dedupe_source_files(plan)

    assert collapsed == ["standards.pdf"]
    assert plan["units"][0]["source_files"] == ["a.pdf", "standards.pdf", "b.pdf"]
    assert plan["units"][1]["source_files"] == ["standards.pdf", "c.pdf"]


def test_a_document_shared_across_units_is_left_alone() -> None:
    """The normal shape of a course-level document, which must survive intact."""
    plan = {
        "units": [
            {"unit_id": "m1", "source_files": ["pacing.pdf", "a.pdf"]},
            {"unit_id": "m2", "source_files": ["pacing.pdf", "b.pdf"]},
        ]
    }

    assert dedupe_source_files(plan) == []
    assert plan["units"][0]["source_files"] == ["pacing.pdf", "a.pdf"]


def test_two_mistyped_spellings_of_one_file_end_up_as_one_entry() -> None:
    """Why dedupe runs after matching rather than before.

    Neither spelling is a duplicate as written; they only become one once both
    have been snapped onto the real filename.
    """
    records = [{"source_file": "150-day_Pacing.pdf"}]
    plan = _plan(["150-Day_Pacing.pdf", "150-DAY_PACING.pdf"])

    reconcile_source_files(records, plan)
    collapsed = dedupe_source_files(plan)

    assert collapsed == ["150-day_Pacing.pdf"]
    assert plan["units"][0]["source_files"] == ["150-day_Pacing.pdf"]
    assert validate_coverage(records, plan) == []