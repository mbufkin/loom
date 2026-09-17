#!/usr/bin/env python3
"""Tests for Layer 1 Phase 2's placement check — the audit's strongest claim.

MISMATCH means "a human filed this document in the wrong unit". It is the one
finding that accuses the curriculum team of an error rather than reporting a
gap, so a false one is expensive: it costs a reviewer real time and it teaches
them to distrust the report. check_placement carries three special-case rules
worked out by hand against a live corpus to prevent exactly that, and this file
pins each of them down so they cannot be lost to a refactor.

These are characterisation tests first and foremost: most were written against
the existing single-home behaviour and must keep passing unchanged. The
multi-home cases at the end cover documents that legitimately serve more than
one unit — a course pacing guide, a syllabus, a shop equipment list.
"""

from __future__ import annotations

import sys
import tempfile
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import CONCENTRATION_MIN_COUNT
from layer1 import build_parent_link_map, check_placement

NO_OVERLAPS: set[frozenset] = set()


def _element(doc_id: str = "pacing-guide", element_id: str = "e1") -> dict:
    return {
        "element_id": element_id,
        "doc_id": doc_id,
        "element_type": "objective",
        "excerpt": "Students select an electrode for a given joint and position.",
        "confidence": 0.9,
        "tier": 1,
    }


def _judgment(unit_id: str | None, day_id: str | None = "d1") -> dict:
    return {
        "matched_unit_id": unit_id,
        "matched_day_id": day_id,
        "supporting_quote": "Select an appropriate E7018 electrode.",
        "reasoning": "Names the unit's electrode objective.",
    }


def _check(
    parents,
    matched: str | None,
    *,
    overview: set[str] | None = None,
    counts: Counter | None = None,
    overlaps: set[frozenset] | None = None,
) -> dict:
    el = _element()
    return check_placement(
        el,
        _judgment(matched) if matched is not None else None,
        {el["doc_id"]: parents} if parents is not None else {},
        overview or set(),
        counts if counts is not None else Counter(),
        overlaps if overlaps is not None else NO_OVERLAPS,
    )


# --- the four plain outcomes ------------------------------------------------


def test_document_the_manifest_never_filed_is_an_orphan() -> None:
    row = _check(None, "smaw")
    assert row["match_status"] == "ORPHAN"
    # With no manifest answer to fall back on, the element's own claim is all
    # there is, so it becomes the placement.
    assert row["final_unit_id"] == "smaw"
    assert row["placement_basis"] == "self_declared"


def test_element_that_declares_nothing_falls_back_to_the_manifest() -> None:
    row = _check("smaw", None)
    assert row["match_status"] == "UNVERIFIED"
    assert row["final_unit_id"] == "smaw"
    assert row["placement_basis"] == "parent_link_only"


def test_agreement_between_document_and_manifest_is_a_match() -> None:
    row = _check("smaw", "smaw")
    assert row["match_status"] == "MATCH"
    assert row["final_unit_id"] == "smaw"
    assert row["mismatch_corroboration"] is None


def test_disagreement_with_nothing_to_excuse_it_is_a_mismatch() -> None:
    row = _check("smaw", "oxyfuel", counts=Counter({"oxyfuel": 4, "smaw": 1}))
    assert row["match_status"] == "MISMATCH"
    # Code never picks a winner here; the report shows both sides and a human
    # decides.
    assert row["parent_link_unit_id"] == "smaw"
    assert row["matched_unit_id"] == "oxyfuel"
    assert row["mismatch_corroboration"] == {
        "same_target_count": 4,
        "total_self_declarations_in_doc": 5,
    }


# --- rule 1: a hub unit named BY an element is not evidence -----------------


def test_declaring_a_hub_unit_is_discounted_not_a_mismatch() -> None:
    """
    A branding footer reading "Dallas ISD CTE" self-declares the district hub on
    every page it appears. That is boilerplate, not a claim about where the
    document belongs, so it is discounted however many times it repeats.
    """
    row = _check("smaw", "district-hub", overview={"district-hub"})
    assert row["match_status"] == "UNVERIFIED"
    assert row["final_unit_id"] == "smaw"
    assert row["placement_basis"] == "parent_link_only"
    assert "discounted self-declaration" in row["cross_reference_note"]


def test_a_hub_declaration_is_discounted_even_from_inside_another_hub() -> None:
    """
    Rule 1 is checked before rule 2 and regardless of the parent's own kind.
    Found live: a document filed under one hub, whose "MISMATCH" rows were just
    a repeated branding URL naming a second hub. Two hubs being involved does
    not make a branding line meaningful.
    """
    row = _check(
        "career-cluster",
        "district-hub",
        overview={"district-hub", "career-cluster"},
        counts=Counter({"district-hub": 8}),
    )
    assert row["match_status"] == "UNVERIFIED"
    assert "discounted self-declaration" in row["cross_reference_note"]


# --- rule 2: a hub unit's own document naming another unit ------------------


def test_a_hub_document_referencing_a_real_unit_is_cross_reference() -> None:
    """A "Career Clusters" deck covering Agriculture is the hub doing its job."""
    row = _check("career-cluster", "agriculture", overview={"career-cluster"})
    assert row["match_status"] == "CROSS_REFERENCE"
    assert row["final_unit_id"] == "career-cluster"
    assert "expected overview behavior" in row["cross_reference_note"]


def test_a_hub_document_that_is_really_about_one_unit_still_mismatches() -> None:
    """
    The exception to rule 2, and the case the whole corroboration mechanism
    exists for: a document filed under a hub whose own elements agree, over and
    over, that it belongs somewhere specific. That is a misfile, not
    cross-referencing, and the hub rule must not hide it.
    """
    counts = Counter({"hospitality-tourism": CONCENTRATION_MIN_COUNT})
    row = _check(
        "career-cluster",
        "hospitality-tourism",
        overview={"career-cluster"},
        counts=counts,
    )
    assert row["match_status"] == "MISMATCH"


def test_one_stray_reference_in_a_hub_document_is_not_enough_to_accuse() -> None:
    """Below the corroboration count, rule 2 still applies."""
    counts = Counter({"hospitality-tourism": CONCENTRATION_MIN_COUNT - 1, "other": 5})
    row = _check(
        "career-cluster",
        "hospitality-tourism",
        overview={"career-cluster"},
        counts=counts,
    )
    assert row["match_status"] == "CROSS_REFERENCE"


# --- rule 3: human-confirmed overlapping disciplines ------------------------


def test_a_confirmed_overlap_pair_is_not_a_filing_error() -> None:
    """
    Engineering design content inside an Architecture & Construction lesson is
    on-topic — Texas CTE's own standards put it there. A human confirms the
    pair once and it applies to every document in it afterwards.
    """
    row = _check(
        "architecture-construction",
        "engineering",
        counts=Counter({"engineering": 6}),
        overlaps={frozenset(("architecture-construction", "engineering"))},
    )
    assert row["match_status"] == "EXPECTED_OVERLAP"
    assert row["final_unit_id"] == "architecture-construction"
    assert "human-confirmed" in row["cross_reference_note"]


def test_overlap_pairs_are_unordered() -> None:
    """"A overlaps B" and "B overlaps A" are the same fact."""
    row = _check(
        "engineering",
        "architecture-construction",
        overlaps={frozenset(("architecture-construction", "engineering"))},
    )
    assert row["match_status"] == "EXPECTED_OVERLAP"


def test_hub_rules_win_over_a_listed_overlap_pair() -> None:
    """
    Rule 3 is checked only after rules 1 and 2. A hub-unit disagreement stays
    governed by the hub rules even if the pair also happens to be listed.
    """
    row = _check(
        "career-cluster",
        "agriculture",
        overview={"career-cluster"},
        overlaps={frozenset(("career-cluster", "agriculture"))},
    )
    assert row["match_status"] == "CROSS_REFERENCE"


# --- a blank field and an absent one mean the same thing --------------------


def test_empty_strings_from_the_model_are_recorded_as_absent() -> None:
    """
    Models write "" for a field they have nothing to say about. A report
    rendering an empty quote as evidence reads as a missing citation rather
    than an absent one, so both spellings collapse to None.
    """
    el = _element()
    judgment = {
        "matched_unit_id": "smaw",
        "matched_day_id": "d1",
        "supporting_quote": "",
        "reasoning": "",
    }
    row = check_placement(
        el, judgment, {el["doc_id"]: "smaw"}, set(), Counter(), NO_OVERLAPS
    )
    assert row["supporting_quote"] is None
    assert row["reasoning"] is None


# --- documents that serve more than one unit --------------------------------


def test_a_shared_document_matches_any_unit_it_was_filed_under() -> None:
    """
    A course pacing guide describes every unit it covers, so it is filed under
    all of them. An element of it naming any one of those units is agreement,
    not a misfile.

    Before documents could be shared this was the bug that made sharing
    unusable: one unit won the 1:1 parent lookup and every element naming the
    other unit was accused of being filed in the wrong place -- the exact error
    sharing exists to prevent.
    """
    for named in ("smaw", "oxyfuel"):
        row = _check({"smaw", "oxyfuel"}, named, counts=Counter({named: 9}))
        assert row["match_status"] == "MATCH", named
        # The element's own unit becomes the placement, so a shared document's
        # content is attributed to the unit it actually discusses.
        assert row["final_unit_id"] == named
        assert row["parent_link_unit_id"] == named


def test_a_shared_document_still_mismatches_on_a_unit_it_was_not_filed_under() -> None:
    """Sharing widens what counts as agreement; it does not disable the check."""
    row = _check(
        {"smaw", "oxyfuel"}, "culinary-arts", counts=Counter({"culinary-arts": 7})
    )
    assert row["match_status"] == "MISMATCH"
    # One home is reported, chosen deterministically so two runs of the same
    # audit do not disagree about which unit was accused.
    assert row["parent_link_unit_id"] == "oxyfuel"
    assert row["parent_link_unit_ids"] == ["oxyfuel", "smaw"]


def test_a_shared_document_reports_every_unit_it_belongs_to() -> None:
    row = _check({"oxyfuel", "smaw"}, None)
    assert row["match_status"] == "UNVERIFIED"
    assert row["parent_link_unit_ids"] == ["oxyfuel", "smaw"]


def test_an_overlap_pair_is_honoured_against_any_home(tmp_path: Path = None) -> None:
    """A shared document needs only one of its homes to pair with the target."""
    row = _check(
        {"architecture-construction", "welding"},
        "engineering",
        overlaps={frozenset(("architecture-construction", "engineering"))},
    )
    assert row["match_status"] == "EXPECTED_OVERLAP"


def test_a_single_unit_string_is_still_accepted(tmp_path: Path = None) -> None:
    """
    The map's values became sets, but a bare string keeps working. Callers
    outside this module build these maps too, and a silent ORPHAN for every
    element would be a quiet, plausible-looking wrong answer.
    """
    row = _check("smaw", "smaw")
    assert row["match_status"] == "MATCH"
    assert row["parent_link_unit_ids"] == ["smaw"]


# --- the map the manifest produces ------------------------------------------


def test_parent_link_map_collects_every_unit_a_document_is_filed_under() -> None:
    manifest = {
        "units": {
            "smaw": {
                "documents": [
                    "unit-1-smaw-lesson-plan.html",
                    "course-pacing-guide.md",
                ]
            },
            "oxyfuel": {
                "documents": [
                    "unit-2-oxyfuel-lesson-plan.html",
                    "course-pacing-guide.md",
                ]
            },
        }
    }
    # doc ids keep their extension -- audit_lib.doc_id_from_filename strips only
    # a doc_<hash>_ prefix and a .txt suffix. Layer 0 derives them with the same
    # function, so the two sides join; the ids are just not as tidy as the
    # docstring suggests.
    mapping = build_parent_link_map(manifest)
    assert mapping["unit-1-smaw-lesson-plan.html"] == {"smaw"}
    assert mapping["unit-2-oxyfuel-lesson-plan.html"] == {"oxyfuel"}
    # The shared document keeps both homes rather than the last one written.
    assert mapping["course-pacing-guide.md"] == {"smaw", "oxyfuel"}


def test_parent_link_map_still_reads_the_older_source_files_key() -> None:
    manifest = {"units": {"smaw": {"source_files": ["unit-1-smaw-lesson-plan.html"]}}}
    assert build_parent_link_map(manifest) == {
        "unit-1-smaw-lesson-plan.html": {"smaw"}
    }


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory():
        for fn in TESTS:
            fn()
            print(f"OK {fn.__name__}")
    print(f"ALL {len(TESTS)} layer1 placement TESTS PASSED")
