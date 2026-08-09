#!/usr/bin/env python3
"""Offline tests for workflows/keyword_match.py.

Every false-positive case below was observed on the real Waxahachie culinary
syllabi before boundary matching existed. They are kept as tests because the
tempting "fix" for a missed keyword is to shorten it, and shortening is what
produced "lab safety present" from the word Clippers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflows.keyword_match import (  # noqa: E402
    match_context,
    matched_keywords,
    matches,
)


def test_substring_inside_a_word_is_not_a_hit() -> None:
    """The original bug: PPE found inside Clippers, happen, dropped."""
    text = "Fingernail Clippers. These competitions happen in April. Two lowest dropped."
    assert not matches(text, ["PPE"])
    assert matches("Wear PPE in the lab at all times.", ["PPE"])


def test_cte_is_not_found_inside_expected() -> None:
    """`cte` as a substring sits in expected/protected, so the CTE soft gate
    fired on nearly every document and optional fields were never optional."""
    assert not matches("Students are expected to follow protected procedures.", ["cte"])
    assert matches("This CTE course meets state requirements.", ["cte"])


def test_excluded_phrase_does_not_count() -> None:
    """`credit` is a course credit statement; `extra credit` is not."""
    only_extra = "There are opportunities throughout the year for extra credit."
    assert not matches(only_extra, ["credit"], exclude=["extra credit"])
    both = only_extra + " This course is worth one credit."
    assert matches(both, ["credit"], exclude=["extra credit"])


def test_plural_form_still_matches() -> None:
    """Boundaries must not cost us the plural a document actually uses."""
    assert matches("Assignments are due by their perspective due dates.", ["due date"])
    assert matches("Turn in one project.", ["project"])


def test_punctuation_keywords_match_literally() -> None:
    """A word boundary next to `%` would demand a letter and never fire."""
    assert matches("Lab Presentations 60% of the grade.", ["%"])
    assert matches("See TEKS §130.226 for details.", ["§"])


def test_phrase_tolerates_extraction_whitespace() -> None:
    """.docx and .pdf extraction splits runs; a rigid space would miss this."""
    assert matches("Summative Test,  Lab\nPresentations 60%", ["lab presentations"])


def test_matched_keywords_reports_only_real_hits() -> None:
    text = "Recipe cover to protect from food. Behavior and Consequences apply."
    hits = matched_keywords(text, ["cover", "sequence", "TEKS"])
    # "cover" is a real word here (a recipe cover), "sequence" only exists
    # inside "Consequences", and TEKS is absent.
    assert hits == ["cover"]


def test_match_context_quotes_the_matching_sentence() -> None:
    """A citation has to show the text that caused the hit, not the paragraph
    head, or a reviewer cannot tell a real hit from a spurious one."""
    text = (
        "Waxahachie High School Culinary Arts Department. " * 4
        + "Late work is not acceptable in my class."
    )
    cite = match_context(text, ["late work"])
    assert "Late work is not acceptable" in cite
    assert cite.startswith("...")


def test_match_context_empty_when_nothing_matches() -> None:
    assert match_context("nothing relevant here", ["PPE"]) == ""


def main() -> int:
    tests = [
        test_substring_inside_a_word_is_not_a_hit,
        test_cte_is_not_found_inside_expected,
        test_excluded_phrase_does_not_count,
        test_plural_form_still_matches,
        test_punctuation_keywords_match_literally,
        test_phrase_tolerates_extraction_whitespace,
        test_matched_keywords_reports_only_real_hits,
        test_match_context_quotes_the_matching_sentence,
        test_match_context_empty_when_nothing_matches,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
