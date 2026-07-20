#!/usr/bin/env python3
"""Offline tests for the lesson-rung bake-off: rubric loading/validation, the
pluggable scorer interface, deterministic presence scoring, graceful model
degradation, and the harness comparison helpers. No models, no network."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import lesson_scorers  # noqa: F401 — registers scorers
from lesson_scoring import (
    MISSING,
    PRESENT,
    LessonElement,
    LessonInput,
    ScorerResult,
    available_scorers,
    build_scorer,
)
from lesson_bakeoff import _divergence, normalized_score, score_agreement
from rubrics import (
    COMPLETENESS_RUBRIC,
    QUALITY_RUBRIC,
    UBD_RUBRIC,
    RubricError,
    criteria_ids,
    load_curriculum_own,
    load_rubric,
)


def _lesson(types_to_excerpt: dict[str, str]) -> LessonInput:
    els = [
        LessonElement(f"e{i}", t, ex)
        for i, (t, ex) in enumerate(types_to_excerpt.items())
    ]
    return LessonInput("proj", "doc1", "unit1", "Test Lesson", els)


def test_rubrics_load_and_validate() -> None:
    for rid in (COMPLETENESS_RUBRIC, UBD_RUBRIC, QUALITY_RUBRIC):
        r = load_rubric(rid)
        assert r["version"] and criteria_ids(r)
    assert load_rubric(COMPLETENESS_RUBRIC)["scoring"] == "presence"
    assert load_rubric(UBD_RUBRIC)["scoring"] == "band"
    # Dallas ships its own rubric; an unknown project falls back to None.
    assert load_curriculum_own("dallas-career-2026") is not None
    assert load_curriculum_own("no-such-project-xyz") is None


def test_bad_rubric_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        import rubrics

        original = rubrics.RUBRICS_DIR
        rubrics.RUBRICS_DIR = Path(td)
        try:
            (Path(td) / "broken.yaml").write_text("version: v1\nrubric_id: x\n")
            raised = False
            try:
                load_rubric("broken")
            except RubricError:
                raised = True
            assert raised, "missing scoring/criteria should raise RubricError"
        finally:
            rubrics.RUBRICS_DIR = original


def test_registry_has_four_methods() -> None:
    assert set(available_scorers()) == {
        "s1_completeness",
        "s2_ubd",
        "s3_curriculum_own",
        "s4_quality",
    }


def test_completeness_presence_and_gate() -> None:
    # All four required core parts present -> gate passes, evidence attached.
    lesson = _lesson(
        {
            "standards_objectives": "Students will identify...",
            "logistics_materials": "Materials: paper, scissors",
            "direct_instruction": "Today we will explain...",
            "assessment_checkpoint": "Exit ticket: solve...",
        }
    )
    res = build_scorer("s1_completeness").score(lesson)
    by = {c.criterion_id: c for c in res.criteria}
    assert by["standards_objectives"].verdict == PRESENT
    assert by["standards_objectives"].is_evidenced()
    assert by["hook_engagement"].verdict == MISSING
    assert res.summary["gate_pass"] is True
    assert res.cost["model_calls"] == 0


def test_completeness_gate_fails_when_required_missing() -> None:
    lesson = _lesson({"standards_objectives": "objective only"})
    res = build_scorer("s1_completeness").score(lesson)
    assert res.summary["gate_pass"] is False


def test_band_scorer_degrades_offline() -> None:
    lesson = _lesson({"standards_objectives": "x", "assessment_checkpoint": "y"})
    for sid in ("s2_ubd", "s4_quality"):
        res = build_scorer(sid).score(lesson, None)
        assert res.error and "offline" in res.error
        assert all(c.band is None for c in res.criteria)
        assert normalized_score(res) is None


def test_normalized_and_divergence() -> None:
    pres = ScorerResult(
        "s1", "r", "v", "presence", "d1", summary={"coverage": 0.5}
    )
    band = ScorerResult(
        "s2", "r", "v", "band", "d1", summary={"mean_band": 3, "max_band": 3}
    )
    err = ScorerResult("s4", "r", "v", "band", "d1", error="boom")
    assert normalized_score(pres) == 0.5
    assert normalized_score(band) == 1.0
    assert normalized_score(err) is None
    assert _divergence({"a": 0.5, "b": 1.0}) == 0.5
    assert _divergence({"a": 0.5, "b": None}) is None  # <2 comparable -> no spread


def test_score_agreement_against_gold() -> None:
    artifacts = [
        {"lesson_id": "L1", "normalized": {"s1": 0.80, "s2": 0.30}},
        {"lesson_id": "L2", "normalized": {"s1": 0.20, "s2": 0.90}},
    ]
    gold = {"L1": {"quality": 0.80}, "L2": {"quality": 0.20}}
    agr = score_agreement(artifacts, gold, ["s1", "s2"])
    # s1 matches gold exactly (MAE 0), s2 is far off.
    assert agr["s1"]["mean_abs_error"] == 0.0
    assert agr["s2"]["mean_abs_error"] > agr["s1"]["mean_abs_error"]
    assert agr["s1"]["within_tolerance"] == 2


if __name__ == "__main__":
    tests = [
        test_rubrics_load_and_validate,
        test_bad_rubric_raises,
        test_registry_has_four_methods,
        test_completeness_presence_and_gate,
        test_completeness_gate_fails_when_required_missing,
        test_band_scorer_degrades_offline,
        test_normalized_and_divergence,
        test_score_agreement_against_gold,
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
