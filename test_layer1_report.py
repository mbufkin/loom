#!/usr/bin/env python3
"""Offline tests for Layer 1 REPORT.md rendering (render_layer1_report).

WHY THIS EXISTS
render_layer1_report was extracted from the run_layer1 orchestrator precisely so
its output could be pinned WITHOUT running the pipeline (no model, no corpus). These
tests are the safety net that makes further decomposition of run_layer1 safe: they
lock the status line, per-status counts, the carried-forward header note, and the
corroboration-sorted MISMATCH detail. If a future refactor changes the report, one
of these fails loudly instead of the drift reaching a curriculum director's desk.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from layer1 import render_layer1_report  # noqa: E402


def _mismatch(eid: str, doc: str, self_unit: str, same: int, total: int) -> dict:
    """A MISMATCH row: filed under u1, self-declares `self_unit`, with corroboration."""
    return {
        "match_status": "MISMATCH",
        "element_id": eid,
        "doc_id": doc,
        "parent_link_unit_id": "u1",
        "matched_unit_id": self_unit,
        "mismatch_corroboration": {
            "same_target_count": same,
            "total_self_declarations_in_doc": total,
        },
    }


def test_status_success_when_no_check_failed() -> None:
    r = render_layer1_report("proj", None, [{"match_status": "MATCH"}], [], 1, 0)
    assert "**Status:** SUCCESS\n" in r  # not "SUCCESS WITH CHECK FAILURES"
    assert "SUCCESS WITH CHECK FAILURES" not in r


def test_status_flags_check_failures() -> None:
    findings = [{"status": "CHECK_FAILED"}]
    r = render_layer1_report("proj", None, [], findings, 0, 0)
    assert "**Status:** SUCCESS WITH CHECK FAILURES" in r
    assert "**CHECK_FAILED role findings" in r and "** 1" in r


def test_per_status_counts() -> None:
    bucket = [
        {"match_status": "MATCH"},
        {"match_status": "CROSS_REFERENCE"},
        {"match_status": "EXPECTED_OVERLAP"},
        {"match_status": "ORPHAN"},
        {"match_status": "UNVERIFIED"},
    ]
    findings = [{"status": "MISSING"}, {"status": "DUPLICATE"}]
    r = render_layer1_report("proj", None, bucket, findings, 5, 0)
    assert "**MATCH:** 1" in r
    assert "**ORPHAN:** 1" in r
    assert "**MISSING role findings:** 1" in r
    assert "**DUPLICATE role findings:** 1" in r


def test_carried_forward_note_only_when_present() -> None:
    # No carry-forward: the header note is suppressed entirely.
    r0 = render_layer1_report("proj", ["u1"], [{"match_status": "MATCH"}], [], 1, 0)
    assert "carried forward" not in r0
    # With carry-forward: the note names both counts.
    r1 = render_layer1_report("proj", ["u1"], [{"match_status": "MATCH"}], [], 1, 4)
    assert "1 newly judged this run, 4 carried forward from other units" in r1


def test_scope_label_reflects_only_units() -> None:
    r = render_layer1_report("proj", ["u2", "u3"], [], [], 0, 0)
    assert "**Scope:** u2,u3" in r
    r_all = render_layer1_report("proj", None, [], [], 0, 0)
    assert "**Scope:** all units" in r_all


def test_mismatch_detail_sorted_by_corroboration() -> None:
    # A weak (1/5) row precedes a strong (3/5) row in input; the report must sort
    # the strong one FIRST and tag it HIGH, weak one 'low'.
    bucket = [
        _mismatch("E_weak", "docA", "u3", same=1, total=5),
        _mismatch("E_strong", "docA", "u2", same=3, total=5),
    ]
    r = render_layer1_report("proj", None, bucket, [], 2, 0)
    strong_pos = r.index("E_strong")
    weak_pos = r.index("E_weak")
    assert strong_pos < weak_pos, "corroborated MISMATCH must sort before low one"
    assert "[HIGH] E_strong" in r
    assert "[low] E_weak" in r
    assert "**MISMATCH:** 2" in r


def test_mismatch_detail_none_when_empty() -> None:
    r = render_layer1_report("proj", None, [{"match_status": "MATCH"}], [], 1, 0)
    assert "## MISMATCH detail (sorted by corroboration strength)\n(none)" in r


if __name__ == "__main__":  # allow running the file directly, no pytest needed
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
