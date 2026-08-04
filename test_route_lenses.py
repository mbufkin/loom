#!/usr/bin/env python3
"""
test_route_lenses.py — Unit tests for Path A–G router cascade (no corpus required).

Best practice: keep router tests offline with tiny fake ledgers + HAS-PART so
CI does not need Dallas/Bluebonnet source trees.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import (  # noqa: E402
    PATH_BY_WORKFLOW,
    filename_lens_prior,
    resolve_workflow,
    _norm_source_key,
)


def test_path_letters_cover_seven_lenses() -> None:
    assert set(PATH_BY_WORKFLOW.values()) == {"A", "B", "C", "D", "E", "F", "G"}
    assert PATH_BY_WORKFLOW["lesson_plan"] == "A"
    assert PATH_BY_WORKFLOW["quiz"] == "B"
    assert PATH_BY_WORKFLOW["general"] == "C"
    assert PATH_BY_WORKFLOW["teacher_support"] == "D"
    assert PATH_BY_WORKFLOW["student_practice"] == "E"
    assert PATH_BY_WORKFLOW["standards_pacing"] == "F"
    assert PATH_BY_WORKFLOW["syllabus"] == "G"


def test_dallas_style_lesson_plan_filename() -> None:
    wf, path, fb, reason = resolve_workflow(
        doc_type="lesson_plan",
        source_file="doc_abc_Engineering_Lesson_Plan.txt",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("lesson_plan", "A", False)
    assert "filename" in reason


def test_assessment_filename_and_rubric() -> None:
    wf, path, _, _ = resolve_workflow(
        doc_type="exit_ticket", source_file="x_Exit_Ticket.txt", graph_hint=None
    )
    assert (wf, path) == ("quiz", "B")
    wf, path, _, _ = resolve_workflow(
        doc_type="rubric", source_file="Project_Rubric.txt", graph_hint=None
    )
    assert (wf, path) == ("quiz", "B")


def test_graph_teacher_edition_overrides_other() -> None:
    hint = {
        "role": "teacher_edition",
        "workflow_id": "teacher_support",
        "reason": "graph Material.role=teacher_edition",
    }
    wf, path, fb, reason = resolve_workflow(
        doc_type="other",
        source_file="Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf",
        graph_hint=hint,
    )
    assert (wf, path, fb) == ("teacher_support", "D", False)
    assert "graph" in reason


def test_graph_student_role() -> None:
    hint = {
        "role": "learn_student",
        "workflow_id": "student_practice",
        "reason": "graph Material.role=learn_student",
    }
    wf, path, _, _ = resolve_workflow(
        doc_type="other",
        source_file="Algebra_I_Math_Student_Edition_Volume_1_Module_1.pdf",
        graph_hint=hint,
    )
    assert (wf, path) == ("student_practice", "E")


def test_filename_standards_prior() -> None:
    assert filename_lens_prior("Algebra_I_Math_Scope_and_Sequence_150-day.pdf")
    wf, path, _, reason = resolve_workflow(
        doc_type="other",
        source_file="Algebra_I_Math_Scope_and_Sequence_150-day.pdf",
        graph_hint=None,
    )
    assert (wf, path) == ("standards_pacing", "F")
    assert "standards" in reason


def test_filename_syllabus_prior() -> None:
    assert filename_lens_prior("Unit_1_Course_Syllabus.pdf")
    wf, path, fb, reason = resolve_workflow(
        doc_type="other",
        source_file="Unit_1_Course_Syllabus.pdf",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("syllabus", "G", False)
    assert "syllabus" in reason


def test_syllabus_filename_beats_graph_te() -> None:
    hint = {
        "role": "teacher_edition",
        "workflow_id": "teacher_support",
        "reason": "graph Material.role=teacher_edition",
    }
    wf, path, _, _ = resolve_workflow(
        doc_type="other",
        source_file="Module_Syllabus_Teacher_Edition.pdf",
        graph_hint=hint,
    )
    assert (wf, path) == ("syllabus", "G")


def test_sylibuis_typo_alias_still_routes() -> None:
    """Legacy misspelling from early Path G stub still lands on Syllabus."""
    wf, path, fb, reason = resolve_workflow(
        doc_type="other",
        source_file="Unit_1_sylibuis_guide.pdf",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("syllabus", "G", False)
    assert "syllabus" in reason


def test_standards_filename_beats_graph_te() -> None:
    hint = {
        "role": "teacher_edition",
        "workflow_id": "teacher_support",
        "reason": "graph Material.role=teacher_edition",
    }
    wf, path, _, _ = resolve_workflow(
        doc_type="other",
        source_file="Algebra_I_Math_Scope_and_Sequence_150-day.pdf",
        graph_hint=hint,
    )
    assert (wf, path) == ("standards_pacing", "F")


def test_lesson_plan_filename_beats_graph_te() -> None:
    """Explicit lesson_plan docs stay on A even if a stray graph hint exists."""
    hint = {
        "role": "teacher_edition",
        "workflow_id": "teacher_support",
        "reason": "graph Material.role=teacher_edition",
    }
    wf, path, _, _ = resolve_workflow(
        doc_type="lesson_plan",
        source_file="doc_x_Lesson_Plan.txt",
        graph_hint=hint,
    )
    assert (wf, path) == ("lesson_plan", "A")


def test_norm_source_key_joins_pdf_and_stem() -> None:
    a = _norm_source_key("Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf")
    b = _norm_source_key("Algebra_I_Math_Teacher_Edition_Volume_1_Module_1")
    assert a == b
    assert a


def test_bluebonnet_e2e_route_smoke_if_present() -> None:
    """Optional: re-route Bluebonnet E2E tree and expect D/E/F > 0 when graph exists."""
    import os

    run = Path("projects/bluebonnet-math-2026/e2e/runs/grok-4.5")
    if not (run / "layer0" / "ledger.json").is_file():
        print("SKIP bluebonnet e2e route smoke (no local run)")
        return
    if not list((run / "graph").rglob("HAS-PART.json")):
        print("SKIP bluebonnet e2e route smoke (no graph)")
        return
    os.environ["LOOM_E2E_RUN"] = "grok-4.5"
    try:
        from route import build_route_map

        out = build_route_map("bluebonnet-math-2026")
        counts = out.get("counts") or {}
        assert counts.get("teacher_support", 0) >= 1, counts
        assert counts.get("student_practice", 0) >= 1, counts
        assert counts.get("standards_pacing", 0) >= 1, counts
        # Must not dump everything to C anymore
        total = sum(counts.values())
        assert counts.get("general", 0) < total
        print(
            "OK bluebonnet route:",
            {k: counts.get(k, 0) for k in sorted(counts)},
        )
    finally:
        os.environ.pop("LOOM_E2E_RUN", None)


def main() -> int:
    tests = [
        test_path_letters_cover_seven_lenses,
        test_dallas_style_lesson_plan_filename,
        test_assessment_filename_and_rubric,
        test_graph_teacher_edition_overrides_other,
        test_graph_student_role,
        test_filename_standards_prior,
        test_filename_syllabus_prior,
        test_syllabus_filename_beats_graph_te,
        test_sylibuis_typo_alias_still_routes,
        test_lesson_plan_filename_beats_graph_te,
        test_norm_source_key_joins_pdf_and_stem,
        test_bluebonnet_e2e_route_smoke_if_present,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
