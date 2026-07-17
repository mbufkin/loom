#!/usr/bin/env python3
"""Tests for schema_validate.py (no models)."""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from schema_validate import (
    raise_on_errors,
    validate_ingest_plan,
    validate_manifest,
    validate_placements,
    validate_unit_calendar,
)
from audit_lib import (
    is_unit_report_success,
    load_manifest,
    load_unit_calendar,
    parse_model_json,
    validate_slug_id,
)


def test_engineering_calendar_on_disk():
    cal = load_unit_calendar(
        BASE / "projects/dallas-career-2026/units/engineering/calendar.yaml"
    )
    assert cal["unit_id"] == "engineering"
    assert len(cal["days"]) >= 1


def test_manifest_on_disk():
    m = load_manifest(BASE / "projects/dallas-career-2026/manifest.yaml")
    assert "engineering" in m["units"]


def test_ingest_plan_rejects_bad_unit_id():
    plan = {
        "units": [
            {
                "unit_id": "Bad ID!",
                "source_files": ["a.txt"],
                "calendar": {
                    "unit_length_days": 1,
                    "days": [
                        {"id": "d1", "label": "Day 1", "expected": ["lesson_content"]}
                    ],
                    "unit_supporting": [],
                },
            }
        ]
    }
    errs = validate_ingest_plan(plan)
    assert any("unit_id" in e for e in errs)


def test_placements_require_excerpt():
    errs = validate_placements(
        {
            "placements": [
                {
                    "doc_id": "x",
                    "slot": "d1",
                    "role": "lesson_content",
                    "confidence": "high",
                }
            ]
        }
    )
    assert any("excerpt" in e for e in errs)


def test_raise_on_errors():
    try:
        raise_on_errors(["a", "b"], "test")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "test" in str(e)


def test_parse_model_json_fenced_and_raw():
    fenced = 'Here:\n```json\n{"units": []}\n```'
    assert parse_model_json(fenced)["units"] == []
    raw = '{"units": [{"unit_id": "x"}]}'
    assert parse_model_json(raw)["units"][0]["unit_id"] == "x"


def test_parse_model_json_embedded():
    text = 'Note:\n{"placements": [], "notes": []}\nDone.'
    assert "placements" in parse_model_json(text, context="test")


def test_validate_slug_id_rejects_injection():
    try:
        validate_slug_id("foo; rm -rf /", "project id")
        assert False
    except ValueError:
        pass


def test_is_unit_report_success_strict():
    ok = "**Status:** SUCCESS\n**Project:** x\n"
    bad = "**Status:** FAILED\n"
    loose = "Previous SUCCESS comment\n**Status:** SUCCESS\n"
    assert is_unit_report_success(ok)
    assert not is_unit_report_success(bad)
    assert is_unit_report_success(loose)


def test_role_singular_matches_role_label_enum():
    """reports.ROLE_SINGULAR's comment claims it's kept in sync with
    synthesize._role_label()'s role enum — assert that, so the two can't
    silently drift apart (e.g. a new role added to one but not the other)."""
    from reports import ROLE_SINGULAR
    from synthesize import _role_label

    role_label_keys = {
        "lesson_plan", "lesson_content", "exit_ticket", "quiz", "answer_key",
        "rubric", "worksheet", "project_work", "presentation", "game_activity",
        "lab_activity", "flex_day", "other",
    }
    assert set(ROLE_SINGULAR) == role_label_keys, set(ROLE_SINGULAR) ^ role_label_keys
    for role, plural in [("quiz", "Quizzes"), ("lesson_plan", "Lesson plans")]:
        assert _role_label(role) == plural


def test_top_units_by_is_precomputed_not_left_to_model():
    """report_delivery._top_units_by must rank deterministically and never include
    zero-count units — this is the guardrail against the model inventing its own
    'which units are worst' ranking (see report_delivery.py docstring on the
    live confabulation this replaced)."""
    from report_delivery import _top_units_by

    rollup = [
        {"title": "A", "missing": 3},
        {"title": "B", "missing": 9},
        {"title": "C", "missing": 0},
        {"title": "D", "missing": 5},
    ]
    top = _top_units_by(rollup, "missing", limit=2)
    assert top == [{"title": "B", "missing": 9}, {"title": "D", "missing": 5}]
    assert _top_units_by([{"title": "Z", "missing": 0}], "missing") == []


def test_clean_element_id_strips_candidate_prefix():
    """layer1._clean_element_id must strip the 'CANDIDATE <id>' label the model
    sometimes echoes verbatim into fulfilled_by (build_phase3_prompt's own
    candidate block is literally formatted that way) — confirmed live on
    dallas-career-2026/financial-literacy Day 3 exit_ticket."""
    from layer1 import _clean_element_id

    assert _clean_element_id("CANDIDATE 54aff8cc2360-e12") == "54aff8cc2360-e12"
    assert _clean_element_id("candidate  abc-e1") == "abc-e1"
    assert _clean_element_id("abc-e1") == "abc-e1"


if __name__ == "__main__":
    for fn in [
        test_engineering_calendar_on_disk,
        test_manifest_on_disk,
        test_ingest_plan_rejects_bad_unit_id,
        test_placements_require_excerpt,
        test_raise_on_errors,
        test_parse_model_json_fenced_and_raw,
        test_parse_model_json_embedded,
        test_validate_slug_id_rejects_injection,
        test_is_unit_report_success_strict,
        test_role_singular_matches_role_label_enum,
        test_top_units_by_is_precomputed_not_left_to_model,
        test_clean_element_id_strips_candidate_prefix,
    ]:
        fn()
        print(f"OK {fn.__name__}")
    print("ALL TESTS PASSED")
