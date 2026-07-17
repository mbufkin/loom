#!/usr/bin/env python3
"""Library tests for audit_lib scrub helpers (no models, no archived CLIs)."""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import classify_doc_type, dedupe_table_line, scrub_document


def test_dedupe_triple_column():
    line = "foo | foo | foo"
    assert dedupe_table_line(line) == "foo"


def test_classify_engineering_files():
    assert classify_doc_type("doc_x_Engineering_Lesson_Plan.txt") == "lesson_plan"
    assert (
        classify_doc_type("doc_x_Engineering_Lesson_-__Exit_Ticket.txt")
        == "exit_ticket"
    )
    assert classify_doc_type("doc_x_Engineering_Lesson_Quiz___Quizizz.txt") == "quiz"


def test_scrub_engineering_lesson():
    path = BASE / "data/career-curriculum/osint/doc_4b97944cd264_Engineering_Lesson.txt"
    ev = scrub_document(path)
    assert ev["doc_type"] == "lesson_content"
    assert 1 in ev["day_hints"]
    assert ev["char_count_clean"] > 500
    assert "Paper Airplane" in ev["title"] or "Engineering" in ev["content_clean"]


if __name__ == "__main__":
    tests = [
        test_dedupe_triple_column,
        test_classify_engineering_files,
        test_scrub_engineering_lesson,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print("ALL TESTS PASSED")
