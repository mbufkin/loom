#!/usr/bin/env python3
"""Offline tests for Layer 1 module-structured placement refinements.

Covers two curriculum-audit fixes validated against the Bluebonnet Grade 5 run:

  fix 2 — program/course guides tagged `kind: overview` plus hub<->module
          `known_overlaps`, so a hub element naming a module is CROSS_REFERENCE /
          EXPECTED_OVERLAP, not a misfile.
  fix 1 — module-internal lesson numbering: a bare "Lesson 30" (or a shared topic)
          cannot reassign an element across content modules; only an explicit
          "Module N" in the quoted evidence can. Gated by a manifest flag so
          subject-cluster corpora (Dallas CTE) keep their existing behavior.

All pure code, no model calls — safe for CI.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from layer1 import (  # noqa: E402
    build_known_overlap_set,
    build_module_internal_numbering_flag,
    build_overview_unit_set,
    check_placement,
    quote_names_a_module,
)

PARENTS = {
    "te2": "g5-mod-2",   # Module 2 Teacher Edition, correctly filed
    "prog": "g5-program",  # a program/course guide (hub)
    "se2": "g5-mod-2",
}


def _check(doc_id, matched, quote, *, overview, known, flag, target_counts=None):
    element = {
        "element_id": f"{doc_id}-e1",
        "doc_id": doc_id,
        "element_type": "lesson_content",
        "excerpt": quote or "",
        "tier": "content",
        "confidence": "high",
    }
    judgment = {
        "matched_unit_id": matched,
        "matched_day_id": None,
        "supporting_quote": quote,
        "reasoning": "test",
    }
    return check_placement(
        element,
        judgment,
        PARENTS,
        overview,
        target_counts or Counter(),
        known,
        module_internal_numbering=flag,
    )


def test_quote_names_a_module():
    assert quote_names_a_module("The focus of Module 6 is the coordinate plane")
    assert quote_names_a_module("Grade 5 Module 3")
    assert not quote_names_a_module("Lesson 30 (Write 834.6 / 26.)")
    assert not quote_names_a_module("Define and construct triangles")
    assert not quote_names_a_module(None)


def test_lesson_number_does_not_reassign_when_flag_on():
    # Module 2 TE chunk reading "Lesson 30"; model guessed sibling module 3.
    res = _check("te2", "g5-mod-3", "Lesson 30 (Write 834.6 / 26.)",
                 overview=set(), known=set(), flag=True)
    assert res["match_status"] == "UNVERIFIED", res["match_status"]
    assert res["final_unit_id"] == "g5-mod-2"


def test_lesson_number_still_mismatch_when_flag_off():
    # Dallas-safety: with the flag off, cross-unit signal stays a MISMATCH.
    res = _check("te2", "g5-mod-3", "Lesson 30 (Write 834.6 / 26.)",
                 overview=set(), known=set(), flag=False)
    assert res["match_status"] == "MISMATCH", res["match_status"]


def test_explicit_module_name_still_mismatch_with_flag_on():
    # An explicit module name in the evidence is strong enough to reassign.
    res = _check("te2", "g5-mod-3", "This is Module 3: multi-digit division",
                 overview=set(), known=set(), flag=True)
    assert res["match_status"] == "MISMATCH", res["match_status"]


def test_matched_equals_parent_is_match_regardless_of_flag():
    for flag in (True, False):
        res = _check("te2", "g5-mod-2", "Lesson 30 fluency practice",
                     overview=set(), known=set(), flag=flag)
        assert res["match_status"] == "MATCH", (flag, res["match_status"])


def test_hub_known_overlap_is_expected_overlap():
    known = {frozenset(("g5-program", "g5-mod-1"))}
    # Concentrated hub disagreement (program guide 16/17 -> mod-1) hits rule 3.
    tc = Counter({"g5-mod-1": 16})
    res = _check("prog", "g5-mod-1", "Instructional Materials Design ... the unit",
                 overview={"g5-program"}, known=known, flag=True, target_counts=tc)
    assert res["match_status"] == "EXPECTED_OVERLAP", res["match_status"]


def test_hub_cross_reference_when_not_overlap_listed():
    # Hub parent, uncorroborated single reference, not in known_overlaps -> CROSS_REFERENCE.
    res = _check("prog", "g5-mod-4", "see Module 4 for area",
                 overview={"g5-program"}, known=set(), flag=True,
                 target_counts=Counter({"g5-mod-4": 1}))
    assert res["match_status"] == "CROSS_REFERENCE", res["match_status"]


def test_manifest_builders_read_generated_shape():
    # Mirrors what tools/stage_bluebonnet_units.py writes.
    manifest = {
        "units": {
            "g5-mod-1": {"title": "Grade 5 Math — Module 1"},
            "g5-program": {"title": "Grade 5 Math — program guides", "kind": "overview"},
        },
        "known_overlaps": [["g5-program", "g5-mod-1"]],
        "placement": {"lesson_numbering_is_module_internal": True},
    }
    assert build_overview_unit_set(manifest) == {"g5-program"}
    assert build_known_overlap_set(manifest) == {frozenset(("g5-program", "g5-mod-1"))}
    assert build_module_internal_numbering_flag(manifest) is True
    # Absent placement block -> flag defaults off (Dallas / legacy manifests).
    assert build_module_internal_numbering_flag({"units": {}}) is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"OK {fn.__name__}")
    print("ALL module-placement TESTS PASSED")
