#!/usr/bin/env python3
"""Offline tests for the packet-type completeness axis (pure functions + the real
registry YAML). No project files, no models, no ledger — the ledger-backed
`present_roles_by_unit` is exercised in the unit-rung integration path instead."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from packet_types import (
    default_packet_type,
    load_packet_types,
    packet_type_spec,
    resolve_packet_type,
    unit_completeness,
)


def test_registry_loads_and_default_is_valid() -> None:
    reg = load_packet_types()
    assert reg["default"] in reg["types"]
    # The three seeded types the director chose.
    assert {"full_curriculum", "teacher_edition", "lesson_plans_only"} <= set(
        reg["types"]
    )


def test_resolve_declared_beats_clever_but_degrades_safely() -> None:
    assert resolve_packet_type("teacher_edition") == "teacher_edition"
    # Unknown / missing -> default, never a crash (graceful degradation).
    assert resolve_packet_type("nonsense") == default_packet_type()
    assert resolve_packet_type(None) == default_packet_type()


def test_completeness_full_for_teacher_edition() -> None:
    spec = packet_type_spec("teacher_edition")  # 3 components
    # Has a plan (lesson_content), activities (presentation), and a check (quiz).
    present = {"lesson_content", "presentation", "quiz"}
    prof = unit_completeness(present, spec)
    assert prof["present"] == 3 and prof["expected"] == 3
    assert prof["missing"] == []
    assert prof["short"] == "TEACHER ED"


def test_completeness_partial_names_the_missing_slot() -> None:
    spec = packet_type_spec("teacher_edition")
    # Plan + slides but no check-for-understanding.
    prof = unit_completeness({"lesson_plan", "presentation"}, spec)
    assert prof["present"] == 2 and prof["expected"] == 3
    assert prof["missing"] == ["Check / assessment"]


def test_completeness_any_of_group_matches_any_member() -> None:
    spec = packet_type_spec("full_curriculum")
    # "Practice / worksheet" slot is satisfied by project_work (an any_of member).
    prof = unit_completeness({"project_work"}, spec)
    prac = next(c for c in prof["components"] if c["label"] == "Practice / worksheet")
    assert prac["present"] and prac["matched"] == "project_work"


def test_completeness_unknown_when_no_ledger_evidence() -> None:
    # None (no ledger rows for the unit) must be honest "unknown", not 0/N.
    assert unit_completeness(None, packet_type_spec("full_curriculum")) is None


def test_completeness_empty_unit_is_zero_not_none() -> None:
    # A unit that exists but has no matching roles is a real 0/N (distinct from None).
    prof = unit_completeness(set(), packet_type_spec("lesson_plans_only"))
    assert prof is not None and prof["present"] == 0


if __name__ == "__main__":
    tests = [
        test_registry_loads_and_default_is_valid,
        test_resolve_declared_beats_clever_but_degrades_safely,
        test_completeness_full_for_teacher_edition,
        test_completeness_partial_names_the_missing_slot,
        test_completeness_any_of_group_matches_any_member,
        test_completeness_unknown_when_no_ledger_evidence,
        test_completeness_empty_unit_is_zero_not_none,
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
