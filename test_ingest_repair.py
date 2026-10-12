#!/usr/bin/env python3
"""Tests for organise's repair round and deterministic cleanup.

The shape under test is a real failure from a live organise of an 18-document
course: the verifier wrote documents' in-file titles where their filenames
belonged, and gave one unit an empty list of days. Validation then rejected the
whole plan:

    unknown files in plan: [<five invented names>];
    units[2].calendar.days must be a non-empty list

The file names here are neutral stand-ins with the same shape -- a title used
for a filename, a numbered heading, a blank-template name -- not the district's
documents. No network: the models are replaced by fakes, and model_call itself
is replaced in the end-to-end test.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import ingest  # noqa: E402
from schema_validate import validate_ingest_plan  # noqa: E402

CATALOG = [
    "Unit 1 Lesson Plan.docx",
    "Unit 1 Exit Ticket Day 1.docx",
    "Unit 2 Lesson Plan.docx",
    "Unit 2 Quiz Answer Key.pdf",
    "Course Pacing Guide.pdf",  # serves both units (abdef99)
    "Project Rubric.docx",  # placed nowhere -> course-level
    "Overview Slides.pptx",
]
RECORDS = [
    {
        "source_file": n,
        "source_format": n.rsplit(".", 1)[-1],
        "doc_type": "unknown",
        "day_hints": [],
        "unit_length_days_hint": None,
        "title": n,
        "excerpt_head": "",
    }
    for n in CATALOG
]

INVENTED = [
    "1. Introduction.pdf",  # a numbered heading, not a filename
    "What is the Unit About.docx",  # a document's title
    "_____ Template.docx",  # a blank-template heading
]


def _days(n: int) -> list[dict]:
    return [
        {"id": f"d{i}", "label": f"Day {i}", "expected": ["lesson_content"]}
        for i in range(1, n + 1)
    ]


def _unit(uid: str, files: list[str], days: int) -> dict:
    return {
        "unit_id": uid,
        "title": uid.title(),
        "source_files": list(files),
        "calendar": {"unit_length_days": days or None, "days": _days(days)},
    }


def failing_plan() -> dict:
    """The live failure, in miniature."""
    return {
        "school_calendar_hint": None,
        "units": [
            # Real files plus one invented title; shares the pacing guide.
            _unit(
                "unit-one",
                ["Unit 1 Lesson Plan.docx", "Course Pacing Guide.pdf", INVENTED[0]],
                3,
            ),
            # All real, also shares the pacing guide.
            _unit(
                "unit-two",
                ["Unit 2 Lesson Plan.docx", "Unit 2 Quiz Answer Key.pdf",
                 "Course Pacing Guide.pdf"],
                2,
            ),
            # A real document but no days: units[2].calendar.days is empty.
            _unit("unit-three", ["Unit 1 Exit Ticket Day 1.docx", INVENTED[1]], 0),
            # Nothing real in it at all.
            _unit("unit-four", [INVENTED[2]], 2),
        ],
    }


class _Log:
    """Stands in for audit_lib.log so the run log's lines can be asserted on."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, msg: str) -> None:
        self.lines.append(msg)

    def warns(self) -> list[str]:
        return [line for line in self.lines if line.startswith("WARN:")]


def _with_log():
    saved = ingest.log
    captured = _Log()
    ingest.log = captured
    return captured, lambda: setattr(ingest, "log", saved)


def _units(plan: dict) -> dict[str, dict]:
    return {u["unit_id"]: u for u in plan["units"]}


def test_the_live_failure_shape_fails_validation_without_repair_or_cleanup() -> None:
    """Guards the fixture: it really is the failure, not an easier cousin."""
    plan = failing_plan()
    problems = ingest.plan_problems(RECORDS, plan)
    assert any("unknown files" in p for p in problems)
    assert any("units[2].calendar.days must be a non-empty list" in p for p in problems)


def test_repair_is_asked_once_and_cleanup_finishes_the_job() -> None:
    """The worst case: the repair helps but still leaves mistakes behind."""
    log, restore = _with_log()
    calls: list[tuple[dict, list[str]]] = []

    def repair(plan: dict, problems: list[str]) -> dict:
        calls.append((copy.deepcopy(plan), list(problems)))
        fixed = failing_plan()
        # It fixes unit-one's name but leaves the rest as it was.
        fixed["units"][0]["source_files"][2] = "Unit 1 Exit Ticket Day 1.docx"
        return fixed

    try:
        plan = ingest.settle_plan(RECORDS, failing_plan(), repair=repair)
    finally:
        restore()

    assert len(calls) == 1, "one repair round, no more"
    sent_problems = calls[0][1]
    assert any("unknown files" in p for p in sent_problems)
    assert any("days must be a non-empty list" in p for p in sent_problems)

    # The result is a plan the pipeline accepts.
    assert ingest.validate_coverage(RECORDS, plan) == []
    assert validate_ingest_plan(plan) == []

    units = _units(plan)
    assert set(units) == {"unit-one", "unit-two", "unit-three"}, "unit-four removed"
    assert units["unit-three"]["calendar"]["days"] == [ingest.DEFAULT_DAY]
    assert INVENTED[1] not in units["unit-three"]["source_files"]

    # Every change is named in the run log.
    warns = "\n".join(log.warns())
    assert INVENTED[1] in warns and INVENTED[2] in warns, warns
    assert "unit unit-three had no calendar days" in warns
    assert "removed unit unit-four" in warns


def test_a_document_serving_several_units_stays_in_all_of_them() -> None:
    """abdef99: the pacing guide is listed under both real units, and cleanup
    must not reduce that to one."""
    _log, restore = _with_log()
    try:
        plan = ingest.settle_plan(RECORDS, failing_plan(), repair=None)
    finally:
        restore()
    units = _units(plan)
    assert "Course Pacing Guide.pdf" in units["unit-one"]["source_files"]
    assert "Course Pacing Guide.pdf" in units["unit-two"]["source_files"]


def test_real_documents_in_no_unit_are_still_shared_as_course_level() -> None:
    """Unchanged behaviour: a real file the organiser placed nowhere goes to
    every surviving unit -- including ones whose invented names were dropped."""
    log, restore = _with_log()
    try:
        plan = ingest.settle_plan(RECORDS, failing_plan(), repair=None)
    finally:
        restore()
    for unit in plan["units"]:
        assert "Project Rubric.docx" in unit["source_files"], unit["unit_id"]
        assert "Overview Slides.pptx" in unit["source_files"], unit["unit_id"]
    assert any(line.startswith("course-level:") for line in log.lines)


def test_a_repair_that_fixes_everything_leaves_nothing_for_cleanup() -> None:
    log, restore = _with_log()

    def repair(plan: dict, problems: list[str]) -> dict:
        return {
            "units": [
                _unit("unit-one", ["Unit 1 Lesson Plan.docx",
                                   "Unit 1 Exit Ticket Day 1.docx",
                                   "Course Pacing Guide.pdf"], 3),
                _unit("unit-two", ["Unit 2 Lesson Plan.docx",
                                   "Unit 2 Quiz Answer Key.pdf",
                                   "Course Pacing Guide.pdf"], 2),
            ]
        }

    try:
        plan = ingest.settle_plan(RECORDS, failing_plan(), repair=repair)
    finally:
        restore()
    assert [u["unit_id"] for u in plan["units"]] == ["unit-one", "unit-two"]
    # Only the one WARN announcing the repair; nothing dropped or defaulted.
    assert len(log.warns()) == 1 and "asking the verifier once" in log.warns()[0]


def test_a_failed_repair_falls_back_to_cleaning_the_original() -> None:
    log, restore = _with_log()

    def repair(plan: dict, problems: list[str]) -> dict:
        raise RuntimeError("504 from the gateway")

    try:
        plan = ingest.settle_plan(RECORDS, failing_plan(), repair=repair)
    finally:
        restore()
    assert validate_ingest_plan(plan) == []
    assert any("repair attempt failed" in w for w in log.warns())


def test_an_empty_repair_reply_does_not_replace_the_original() -> None:
    _log, restore = _with_log()
    try:
        plan = ingest.settle_plan(
            RECORDS, failing_plan(), repair=lambda p, probs: {"units": []}
        )
    finally:
        restore()
    assert {"unit-one", "unit-two"} <= set(_units(plan))


def test_a_clean_plan_never_calls_repair() -> None:
    _log, restore = _with_log()
    calls = []
    good = {
        "units": [
            _unit("unit-one", CATALOG, 2),
        ]
    }
    try:
        ingest.settle_plan(RECORDS, good, repair=lambda p, probs: calls.append(1))
    finally:
        restore()
    assert calls == []


def test_existing_near_miss_matching_still_runs_before_anything_is_dropped() -> None:
    """A retyped real name is repaired, not dropped: the matcher goes first."""
    log, restore = _with_log()
    plan = {
        "units": [_unit("unit-one", ["unit_1_lesson_plan.docx", "Course Pacing Guide.pdf"], 2)]
    }
    try:
        plan = ingest.settle_plan(RECORDS, plan, repair=None)
    finally:
        restore()
    assert "Unit 1 Lesson Plan.docx" in plan["units"][0]["source_files"]
    assert not any("unit_1_lesson_plan" in w for w in log.warns())


def test_nothing_usable_left_is_a_clear_failure() -> None:
    _log, restore = _with_log()
    plan = {"units": [_unit("unit-one", INVENTED, 2)]}
    try:
        ingest.settle_plan(RECORDS, plan, repair=lambda p, probs: copy.deepcopy(p))
    except ValueError as e:
        assert "no usable units" in str(e)
    else:
        raise AssertionError("a plan with no real documents must fail")
    finally:
        restore()


def test_ingest_end_to_end_with_a_fake_model() -> None:
    """The wiring: analyst, verifier, then exactly one repair call on the
    verifier role, whose prompt carries every real filename and the errors --
    and a manifest the audit can read at the end."""
    log, restore = _with_log()
    replies = [failing_plan(), failing_plan(), failing_plan()]
    seen: list[dict] = []

    def fake_model_call(cfg, role, messages, step, temperature=0.1):
        seen.append({"role": role, "step": step, "prompt": messages[0]["content"]})
        return {"choices": [{"message": {"content": json.dumps(replies[len(seen) - 1])}}]}

    tmp = Path(tempfile.mkdtemp(prefix="loom-ingest-repair-"))
    saved = (ingest.model_call, ingest.build_catalog, ingest.load_config, ingest.project_dir)
    ingest.model_call = fake_model_call
    ingest.build_catalog = lambda sources: (RECORDS, [])
    ingest.load_config = lambda: {}
    ingest.project_dir = lambda pid: tmp / pid
    try:
        root = ingest.ingest("demo", tmp / "sources")
    finally:
        (ingest.model_call, ingest.build_catalog, ingest.load_config,
         ingest.project_dir) = saved
        restore()

    assert [c["step"] for c in seen] == ["ingest-analyst", "ingest-verifier", "ingest-repair"]
    assert seen[2]["role"] == "verifier", "same role and config as the verifier"
    repair_prompt = seen[2]["prompt"]
    for name in CATALOG:
        assert f"  {name}\n" in repair_prompt, f"{name} not listed exactly"
    assert "units[2].calendar.days must be a non-empty list" in repair_prompt
    assert (root / "ingest" / ".raw" / "organize-repair.json").is_file()

    from audit_lib import load_manifest

    manifest = load_manifest(root / "manifest.yaml")
    assert set(manifest["units"]) == {"unit-one", "unit-two", "unit-three"}
    assert any("dropped" in w for w in log.warns())


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    for fn in TESTS:
        fn()
        print(f"OK {fn.__name__}")
    print(f"ALL {len(TESTS)} ingest repair TESTS PASSED")
