#!/usr/bin/env python3
"""Offline tests for the noise-reduction rollup (synthesize.aggregate_missing +
load_expectations + rendering). No models, no network.

These pin the behavior the plan's finding-aggregation / expectation-calibration
workstream exists to guarantee: a per-slot MISSING storm collapses into a few
role-patterns (rate + capped, de-duplicated exemplars), a corpus-wide absence is
inhibited into a single "decide once" prompt, a human silence removes a settled
pattern from the gap counts, and a genuinely localized gap still surfaces.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from synthesize import (
    EXEMPLAR_CAP,
    SYSTEMIC_ABSENCE_RATE,
    aggregate_missing,
    load_expectations,
    render_dashboard,
    render_global_audit_deterministic,
)


def _finding(unit_id: str, day_id: str, role: str, status: str, reason: str = "r"):
    return {
        "unit_id": unit_id,
        "day_id": day_id,
        "role": role,
        "fulfilled_by": [],
        "reasoning": reason,
        "status": status,
    }


def _roll(findings, silenced=None):
    return aggregate_missing(findings, silenced or {}, unit_titles={})


def test_uniform_absence_collapses_to_one_pattern() -> None:
    # A role expected on every day of 3 units but never fulfilled anywhere is an
    # expectation mismatch (Alertmanager-style inhibition), not N defects.
    findings = [
        _finding(f"u{u}", f"d{d}", "exit_ticket", "MISSING")
        for u in range(3)
        for d in range(5)
    ]
    r = _roll(findings)
    assert r["counts"]["missing_total"] == 15
    assert r["counts"]["pattern_count"] == 1, r["counts"]
    assert r["counts"]["missing_systemic"] == 15
    assert r["counts"]["isolated_gap_count"] == 0
    assert [x["role"] for x in r["systemic_absent"]] == ["exit_ticket"]
    assert r["systemic_absent"][0]["absence_rate"] == 1.0


def test_isolated_gap_stays_actionable() -> None:
    # exit_ticket present in most slots, missing in only one -> a real localized gap
    # (below the systemic absence rate), so it must NOT be inhibited.
    findings = [_finding(f"u{u}", "d1", "exit_ticket", "FULFILLED") for u in range(9)]
    findings.append(_finding("u9", "d1", "exit_ticket", "MISSING"))
    r = _roll(findings)
    assert r["counts"]["pattern_count"] == 0
    assert r["counts"]["isolated_gap_count"] == 1
    assert [x["role"] for x in r["isolated"]] == ["exit_ticket"]
    assert r["isolated"][0]["absence_rate"] < SYSTEMIC_ABSENCE_RATE


def test_exemplars_capped_and_reason_deduped() -> None:
    # Ten identical machine reasons must show as ONE representative exemplar, capped
    # (near-duplicate collapse) — never ten copies of the same sentence.
    findings = [
        _finding(f"u{u}", f"d{d}", "quiz", "MISSING", reason="no candidate routed")
        for u in range(5)
        for d in range(2)
    ]
    r = _roll(findings)
    ex = r["systemic_absent"][0]["exemplars"]
    assert len(ex) == 1, "identical reasons should collapse to one exemplar"
    # Distinct reasons fill up to the cap.
    findings2 = [
        _finding(f"u{u}", "d1", "quiz", "MISSING", reason=f"reason {u}")
        for u in range(10)
    ]
    r2 = _roll(findings2)
    assert len(r2["systemic_absent"][0]["exemplars"]) == EXEMPLAR_CAP


def test_check_failed_not_counted_as_expectation() -> None:
    # A failed model call is not evidence of a gap and must be excluded entirely.
    findings = [_finding(f"u{u}", "d1", "rubric", "CHECK_FAILED") for u in range(4)]
    r = _roll(findings)
    assert r["counts"]["missing_total"] == 0
    assert r["roles"] == []


def test_silence_removes_pattern_from_gap_counts() -> None:
    # A human decision (expectations.yaml) demotes a systemic pattern to "calibrated":
    # reported once, excluded from both the pattern and isolated gap tallies.
    findings = [
        _finding(f"u{u}", f"d{d}", "exit_ticket", "MISSING")
        for u in range(3)
        for d in range(5)
    ]
    r = aggregate_missing(
        findings,
        {"exit_ticket": {"reason": "module-pack math has no daily exit tickets"}},
        unit_titles={},
    )
    assert r["counts"]["pattern_count"] == 0
    assert r["counts"]["missing_systemic"] == 0
    assert r["counts"]["missing_silenced"] == 15
    assert [x["role"] for x in r["silenced"]] == ["exit_ticket"]
    assert r["silenced"][0]["decision"]["reason"].startswith("module-pack")


def test_load_expectations_forms_and_missing_file() -> None:
    import synthesize

    original = synthesize.project_dir
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td) / "p"
        proj.mkdir(parents=True)
        # load_expectations resolves via project_dir(); point it at our temp root.
        synthesize.project_dir = lambda pid: proj  # type: ignore[assignment]
        try:
            # No file -> {} (graceful default: nothing silenced).
            assert load_expectations("p") == {}
            # List form.
            (proj / "expectations.yaml").write_text(
                "silenced_roles: [quiz, exit_ticket]\n"
            )
            assert set(load_expectations("p")["silenced_roles"]) == {
                "quiz",
                "exit_ticket",
            }
            # Mapping form with decision detail.
            (proj / "expectations.yaml").write_text(
                "silenced_roles:\n  quiz:\n    reason: none used\n"
            )
            got = load_expectations("p")
            assert got["silenced_roles"]["quiz"]["reason"] == "none used"
        finally:
            synthesize.project_dir = original


def test_renderers_consume_rollup_without_crashing() -> None:
    # Minimal agg shaped like aggregate_layer1's output; renderers must degrade
    # gracefully and reflect the pattern/isolated split, not raw per-slot counts.
    findings = [
        _finding(f"u{u}", f"d{d}", "exit_ticket", "MISSING")
        for u in range(3)
        for d in range(5)
    ]
    rollup = aggregate_missing(findings, {}, unit_titles={"u0": "Unit 0"})
    agg = {
        "documents_judged": 3,
        "elements_judged": 30,
        "status_counts": {"MATCH": 10},
        "finding_status_counts": {"MISSING": 15, "FULFILLED": 0, "DUPLICATE": 0},
        "mismatch_docs_high": [],
        "mismatch_docs_low": [],
        "mismatch_element_count": 0,
        "review_queue_pending_pairs": 0,
        "systemic_missing": [],
        "missing_rollup": rollup,
        "unit_rollup": [
            {
                "unit_id": "u0",
                "title": "Unit 0",
                "match": 10,
                "mismatch": 0,
                "fulfilled": 0,
                "missing": 15,
                "duplicate": 0,
            }
        ],
    }
    md = render_global_audit_deterministic("p", agg)
    assert "expectation pattern" in md.lower()
    assert "exit tickets" in md.lower()  # _role_label plural
    dash = render_dashboard("p", agg)
    assert "Expectation patterns to calibrate" in dash


if __name__ == "__main__":
    tests = [
        test_uniform_absence_collapses_to_one_pattern,
        test_isolated_gap_stays_actionable,
        test_exemplars_capped_and_reason_deduped,
        test_check_failed_not_counted_as_expectation,
        test_silence_removes_pattern_from_gap_counts,
        test_load_expectations_forms_and_missing_file,
        test_renderers_consume_rollup_without_crashing,
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
