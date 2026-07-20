#!/usr/bin/env python3
"""Offline tests for the locked lesson rung: the per-unit rollup math and the
locked-scorer configuration. Pure functions only — no project files, no models."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from lesson_rung import GATE_SCORER, LOCKED_SCORERS, rollup_units


def _row(unit: str, lid: str, gate: bool, s1: float, s3: float) -> dict:
    return {
        "lesson_id": lid,
        "unit_id": unit,
        "title": lid,
        "gate_pass": gate,
        "coverage": {"s1_completeness": s1, "s3_curriculum_own": s3},
    }


def test_locked_config_is_deterministic_pair() -> None:
    # The bake-off locked the two deterministic scorers; the gate is S1.
    assert LOCKED_SCORERS == ["s1_completeness", "s3_curriculum_own"]
    assert GATE_SCORER == "s1_completeness"


def test_rollup_counts_and_means() -> None:
    rows = [
        _row("u1", "l1", True, 0.8, 0.6),
        _row("u1", "l2", False, 0.4, 0.4),
        _row("u2", "l3", True, 1.0, 1.0),
    ]
    units = rollup_units(rows)
    assert set(units) == {"u1", "u2"}
    assert units["u1"]["lesson_count"] == 2
    assert units["u1"]["gate_pass_count"] == 1
    assert units["u1"]["gate_pass_rate"] == 0.5
    # mean coverage per method, rounded to 3 dp
    assert units["u1"]["mean_coverage"]["s1_completeness"] == 0.6  # (0.8+0.4)/2
    assert units["u1"]["mean_coverage"]["s3_curriculum_own"] == 0.5
    assert units["u2"]["gate_pass_rate"] == 1.0


def test_rollup_ignores_missing_coverage() -> None:
    # A method that returned None for a lesson must not poison the mean.
    rows = [
        _row("u1", "l1", True, 0.8, 0.6),
        {
            "lesson_id": "l2",
            "unit_id": "u1",
            "title": "l2",
            "gate_pass": True,
            "coverage": {"s1_completeness": 0.4, "s3_curriculum_own": None},
        },
    ]
    units = rollup_units(rows)
    # s3 mean uses only the one real value
    assert units["u1"]["mean_coverage"]["s3_curriculum_own"] == 0.6
    assert units["u1"]["mean_coverage"]["s1_completeness"] == 0.6


def test_rollup_sorted_and_lessons_preserved() -> None:
    rows = [_row("z", "l1", True, 1.0, 1.0), _row("a", "l2", False, 0.0, 0.0)]
    units = rollup_units(rows)
    assert list(units) == ["a", "z"]  # sorted by unit id
    assert units["z"]["lessons"][0]["lesson_id"] == "l1"


if __name__ == "__main__":
    tests = [
        test_locked_config_is_deterministic_pair,
        test_rollup_counts_and_means,
        test_rollup_ignores_missing_coverage,
        test_rollup_sorted_and_lessons_preserved,
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
