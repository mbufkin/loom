#!/usr/bin/env python3
"""Offline tests for the deterministic unit rung: band thresholds, pacing fit, and
internal-gap rollup. Pure functions only \u2014 no project files, no models."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from unit_rung import (
    PACING_UNDER_RATIO,
    STRONG_COVERAGE,
    STRONG_GATE_RATE,
    WEAK_GATE_RATE,
    unit_band,
    unit_internal_gaps,
    unit_pacing_fit,
)


# --- unit_band ---------------------------------------------------------------
def _m(**kw) -> dict:
    base = {
        "lesson_count": 4,
        "gate_pass_rate": 0.75,
        "gate_coverage": 0.8,
        "has_systemic_gap": False,
        "pacing_flag": "OK",
    }
    base.update(kw)
    return base


def test_band_unrated_when_no_lessons() -> None:
    # No lesson evidence -> we refuse to fabricate a Weak verdict.
    assert unit_band(_m(lesson_count=0)) == "Unrated"


def test_band_strong_requires_all_conditions() -> None:
    assert unit_band(_m()) == "Strong"


def test_band_systemic_gap_does_not_force_weak() -> None:
    # A systemic absence is a curriculum-wide packet-type characteristic (surfaced
    # on the completeness axis), NOT a per-unit quality defect. It must not drag an
    # otherwise-strong unit to Weak — that was the "everything reads Weak" bug.
    assert unit_band(_m(has_systemic_gap=True)) == "Strong"


def test_band_low_gate_rate_is_weak() -> None:
    assert unit_band(_m(gate_pass_rate=WEAK_GATE_RATE - 0.01)) == "Weak"
    # exactly at the floor is NOT weak (>= floor survives)
    assert unit_band(_m(gate_pass_rate=WEAK_GATE_RATE)) != "Weak"


def test_band_developing_when_between() -> None:
    # Above weak floor, below strong bar -> Developing.
    assert unit_band(_m(gate_pass_rate=0.5, gate_coverage=0.5)) == "Developing"


def test_band_under_covered_pacing_does_not_block_strong() -> None:
    # Pacing is an inventory/completeness signal (thin vs. planned days), shown
    # descriptively — it no longer blocks the QUALITY band. A unit whose present
    # lessons are strong stays Strong even if the packet is thin.
    assert unit_band(_m(pacing_flag="UNDER_COVERED")) == "Strong"


def test_band_artifact_gap_blocks_strong_but_not_weak() -> None:
    # A structurally-incomplete artifact drops an otherwise-Strong unit to Developing
    # (deterministic gate) ...
    assert unit_band(_m(has_artifact_gap=True)) == "Developing"
    # ... but it never fabricates Weak on its own (a healthy-lesson unit stays >= Developing).
    assert unit_band(_m(has_artifact_gap=True, gate_pass_rate=0.9)) != "Weak"


def test_band_missing_coverage_cannot_be_strong() -> None:
    assert unit_band(_m(gate_coverage=None)) == "Developing"


def test_band_boundaries_use_named_constants() -> None:
    # Strong needs gate_rate >= STRONG_GATE_RATE AND coverage >= STRONG_COVERAGE.
    assert (
        unit_band(_m(gate_pass_rate=STRONG_GATE_RATE, gate_coverage=STRONG_COVERAGE))
        == "Strong"
    )
    assert (
        unit_band(
            _m(gate_pass_rate=STRONG_GATE_RATE, gate_coverage=STRONG_COVERAGE - 0.01)
        )
        == "Developing"
    )


# --- unit_pacing_fit ---------------------------------------------------------
def _days(*statuses: str) -> dict:
    return {"days": [{"id": f"d{i}", "status": s} for i, s in enumerate(statuses)]}


def test_pacing_unknown_without_planned() -> None:
    fit = unit_pacing_fit(None, _days("HAS_EVIDENCE"))
    assert fit["flag"] == "UNKNOWN" and fit["ratio"] is None
    assert fit["evidence_days"] == 1


def test_pacing_under_covered() -> None:
    # 6 evidence days of a 10-day unit -> 0.6 < 0.8 -> UNDER_COVERED.
    fit = unit_pacing_fit(
        {"unit_length_days": 10}, _days(*(["HAS_EVIDENCE"] * 6 + ["EMPTY"] * 4))
    )
    assert fit["evidence_days"] == 6
    assert fit["ratio"] == 0.6
    assert fit["flag"] == "UNDER_COVERED"


def test_pacing_ok_at_threshold() -> None:
    # Exactly at PACING_UNDER_RATIO is NOT under-covered.
    planned = 10
    ev = int(planned * PACING_UNDER_RATIO)
    fit = unit_pacing_fit(
        {"unit_length_days": planned},
        _days(*(["HAS_EVIDENCE"] * ev + ["EMPTY"] * (planned - ev))),
    )
    assert fit["flag"] == "OK"


def test_pacing_over_covered() -> None:
    fit = unit_pacing_fit({"unit_length_days": 2}, _days(*(["HAS_EVIDENCE"] * 3)))
    assert fit["flag"] == "OVER_COVERED"


# --- unit_internal_gaps ------------------------------------------------------
def _l2(doc_id: str, status: str, missing: list[str]) -> dict:
    return {"doc_id": doc_id, "status": status, "components_missing": missing}


def test_internal_gaps_counts_and_ranks() -> None:
    rows = [
        _l2("a", "INCOMPLETE", ["standards_objectives", "assessment_checkpoint"]),
        _l2("b", "INCOMPLETE", ["standards_objectives"]),
        _l2("c", "COMPLETE", []),
        _l2("z", "INCOMPLETE", ["should_be_ignored"]),  # not in this unit
    ]
    out = unit_internal_gaps(rows, {"a", "b", "c"})
    assert out["docs_judged"] == 3
    assert out["docs_incomplete"] == 2
    # standards_objectives (2 hits) ranks ahead of assessment_checkpoint (1 hit)
    assert out["top_missing_components"][0] == "standards_objectives"
    assert "should_be_ignored" not in out["top_missing_components"]


def test_internal_gaps_empty_unit() -> None:
    out = unit_internal_gaps([], set())
    assert out == {"docs_judged": 0, "docs_incomplete": 0, "top_missing_components": []}


if __name__ == "__main__":
    tests = [
        test_band_unrated_when_no_lessons,
        test_band_strong_requires_all_conditions,
        test_band_systemic_gap_does_not_force_weak,
        test_band_low_gate_rate_is_weak,
        test_band_developing_when_between,
        test_band_under_covered_pacing_does_not_block_strong,
        test_band_missing_coverage_cannot_be_strong,
        test_band_boundaries_use_named_constants,
        test_pacing_unknown_without_planned,
        test_pacing_under_covered,
        test_pacing_ok_at_threshold,
        test_pacing_over_covered,
        test_internal_gaps_counts_and_ranks,
        test_internal_gaps_empty_unit,
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
