#!/usr/bin/env python3
"""Offline tests for the Teacher-Edition pre-pass: TE type classification, the
multi-lesson density signal, and correct per-lesson segmentation (front-matter
excluded, no lesson invented, markers never merged). No models, no project files."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import classify_doc_type
from te_prepass import (
    MIN_DISTINCT_LESSONS,
    distinct_lesson_numbers,
    looks_like_multi_lesson_te,
    segment_te_document,
)


def _els(*excerpts: str) -> list[dict]:
    return [
        {"element_id": f"e{i}", "element_type": "direct_instruction", "excerpt": ex}
        for i, ex in enumerate(excerpts)
    ]


def test_te_filename_classifies_as_multi_lesson() -> None:
    assert (
        classify_doc_type("K-5_Math_Grade_5_Module_1_Teacher_Edition.pdf")
        == "teacher_edition_multi_lesson"
    )
    assert (
        classify_doc_type("Algebra_I_Math_Teacher_Edition_Volume_1_Module_1.pdf")
        == "teacher_edition_multi_lesson"
    )
    # A normal lesson plan is unaffected.
    assert classify_doc_type("Engineering_Lesson_Plan.txt") == "lesson_plan"


def test_density_signal() -> None:
    multi = _els("Lesson 1 intro", "content", "Lesson 2 begins", "more")
    assert distinct_lesson_numbers(multi) == {1, 2}
    assert looks_like_multi_lesson_te(multi)
    # A single stray marker is not a multi-lesson TE.
    single = _els("Lesson 1 only", "body text", "no markers here")
    assert not looks_like_multi_lesson_te(single)
    assert MIN_DISTINCT_LESSONS == 2


def test_segmentation_groups_by_running_marker() -> None:
    els = _els(
        "Module front matter (no marker)",  # front-matter -> excluded
        "Lesson 1 objective",
        "Lesson 1 practice",
        "Lesson 2 objective",
        "Lesson 2 exit ticket",
        "Lesson 3 warmup",
    )
    segs = segment_te_document(els)
    nums = [s["lesson_number"] for s in segs]
    assert nums == [1, 2, 3], nums
    # Front matter before the first marker is NOT emitted as a lesson.
    assert sum(len(s["elements"]) for s in segs) == 5
    # Lesson 1 captured both of its elements.
    assert len(segs[0]["elements"]) == 2


def test_no_markers_yields_no_lessons() -> None:
    segs = segment_te_document(_els("intro", "body", "conclusion"))
    assert segs == []


def test_out_of_order_markers_do_not_merge() -> None:
    # Even if lesson numbers reappear/reorder, each contiguous run keeps its number;
    # a repeated number accumulates into the same segment, never a different one.
    els = _els("Lesson 5 a", "Lesson 5 b", "Lesson 6 a", "Lesson 5 c")
    segs = segment_te_document(els)
    by_num = {s["lesson_number"]: len(s["elements"]) for s in segs}
    assert by_num == {5: 3, 6: 1}, by_num


if __name__ == "__main__":
    tests = [
        test_te_filename_classifies_as_multi_lesson,
        test_density_signal,
        test_segmentation_groups_by_running_marker,
        test_no_markers_yields_no_lessons,
        test_out_of_order_markers_do_not_merge,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    sys.exit(1 if failed else 0)
