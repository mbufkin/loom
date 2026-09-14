#!/usr/bin/env python3
"""Tests for recovering a partial answer from a model that stopped mid-array.

The shapes here are taken from a real run: nemotron-3.5-lightning-30b judging
037-immune__action-plan.html through Layer 1 Phase 1. It wrote four complete
placements, abandoned JSON mid-object, narrated its plan for the rest, and
stopped with finish_reason "stop". Nothing hit a token ceiling. Two attempts
failed identically and the whole document was left unjudged, discarding four
correct judgments along with the narration.
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import salvage_json_array


# The real failure, trimmed: valid objects, then drift mid-object, then prose.
DRIFTED = """{
  "placements": [
    {
      "element_id": "037-immune__action-plan.html-e1",
      "self_identifies_with_a_unit": true,
      "matched_unit_id": "immune",
      "matched_day_id": "d1",
      "supporting_quote": "Objectives: 1. To describe the main functions of the immune system.",
      "reasoning": "explicitly names 'immune system' and 'Class 1'"
    },
    {
      "element_id": "037-immune__action-plan.html-e2",
      "self_identifies_with_a_unit": false,
      "matched_unit_id": null,
      "matched_day_id": null,
      "supporting_quote": "",
      "reasoning": ""
    },
    {
      "element_id": "037-immune__action-plan.html-e3",
      "self_identifies_with_a_unit
I'll also need to ensure the day_id mappings are correct for the immune unit,
and handle the supporting quotes and reasoning for each element. Let me proceed
with the remaining element judgments."""


def test_recovers_the_complete_objects_before_the_drift():
    got = salvage_json_array(DRIFTED, "placements")
    assert len(got) == 2, f"expected the 2 complete placements, got {len(got)}"
    assert got[0]["element_id"] == "037-immune__action-plan.html-e1"
    assert got[0]["matched_unit_id"] == "immune"
    # The blank-field no-match judgment survives salvage intact, since "" and
    # null are both valid spellings of "not stated".
    assert got[1]["supporting_quote"] == ""
    assert got[1]["matched_unit_id"] is None


def test_a_clean_array_is_returned_whole():
    clean = '{"placements": [{"element_id": "e1"}, {"element_id": "e2"}]}'
    got = salvage_json_array(clean, "placements")
    assert [p["element_id"] for p in got] == ["e1", "e2"]


def test_brackets_inside_quoted_text_do_not_confuse_the_boundaries():
    """These objects quote curriculum text verbatim, so braces and brackets
    inside strings are ordinary. Counting delimiters by hand would mis-split
    here; raw_decode does not."""
    tricky = (
        '{"placements": [{"element_id": "e1", '
        '"supporting_quote": "Materials: [handout], {see p. 4}, \\"Immunity\\""}, '
        '{"element_id": "e2", "supporting_quote": "arr[0] = {x}"}]}'
    )
    got = salvage_json_array(tricky, "placements")
    assert len(got) == 2
    assert got[0]["supporting_quote"] == 'Materials: [handout], {see p. 4}, "Immunity"'
    assert got[1]["element_id"] == "e2"


def test_nothing_to_salvage_returns_empty():
    # Pure narration, never reached an object.
    assert salvage_json_array('{"placements": [\nLet me think about this.', "placements") == []
    # Drift inside the very first object -- no complete work to keep.
    assert salvage_json_array('{"placements": [{"element_id": "e1"', "placements") == []
    # Key absent entirely.
    assert salvage_json_array('{"role_fulfillment": [{"role": "x"}]}', "placements") == []
    # Degenerate inputs must not raise.
    assert salvage_json_array("", "placements") == []
    assert salvage_json_array('{"placements": []}', "placements") == []


def test_works_for_the_phase_3_array_too():
    text = (
        '{"role_fulfillment": [{"role": "lesson plan", "fulfilled_by": ["e1"], '
        '"confidence": "high", "reasoning": "names the lesson"}, {"role": "exit'
    )
    got = salvage_json_array(text, "role_fulfillment")
    assert len(got) == 1
    assert got[0]["fulfilled_by"] == ["e1"]


if __name__ == "__main__":
    for fn in [
        test_recovers_the_complete_objects_before_the_drift,
        test_a_clean_array_is_returned_whole,
        test_brackets_inside_quoted_text_do_not_confuse_the_boundaries,
        test_nothing_to_salvage_returns_empty,
        test_works_for_the_phase_3_array_too,
    ]:
        fn()
        print(f"OK {fn.__name__}")
    print("ALL TESTS PASSED")
