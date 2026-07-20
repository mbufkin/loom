#!/usr/bin/env python3
"""Offline tests for the route.py graceful-degradation contract: confident routes
are not degraded, weak/unknown types and low-confidence routes are, and the reason
is honest. Pure — no project on disk required."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import CONFIDENCE_FLOOR, assess_degradation, doc_type_to_workflow


def test_confident_known_types_not_degraded() -> None:
    # A lesson plan and a quiz at normal confidence route to dedicated passes.
    for dt in ("lesson_plan", "quiz", "exit_ticket", "answer_key"):
        degraded, reason = assess_degradation(dt, 0.9)
        assert not degraded, (dt, reason)


def test_unknown_type_is_degraded() -> None:
    degraded, reason = assess_degradation("other", 0.9)
    assert degraded
    assert "no dedicated pass" in reason
    # It still routes (to Path C) — degraded means best-effort, not dropped.
    assert doc_type_to_workflow("other")[1] == "C"


def test_low_confidence_is_degraded_even_for_known_type() -> None:
    below = CONFIDENCE_FLOOR - 0.05
    degraded, reason = assess_degradation("lesson_plan", below)
    assert degraded
    assert "low routing confidence" in reason


def test_confidence_floor_boundary() -> None:
    # Exactly at the floor is acceptable; just below is degraded.
    assert not assess_degradation("lesson_plan", CONFIDENCE_FLOOR)[0]
    assert assess_degradation("lesson_plan", CONFIDENCE_FLOOR - 0.01)[0]


def test_none_confidence_only_degrades_on_type() -> None:
    # Missing confidence must not itself trip the floor (no false degradation).
    assert not assess_degradation("lesson_plan", None)[0]
    assert assess_degradation("other", None)[0]


if __name__ == "__main__":
    tests = [
        test_confident_known_types_not_degraded,
        test_unknown_type_is_degraded,
        test_low_confidence_is_degraded_even_for_known_type,
        test_confidence_floor_boundary,
        test_none_confidence_only_degrades_on_type,
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
