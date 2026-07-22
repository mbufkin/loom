#!/usr/bin/env python3
"""Offline tests for the artifact rung (Paths B/C non-lesson review).

Covers the vertical slice end to end without a model or network:
  - deterministic presence gate (pass/fail + named structural gaps),
  - the generic fallback + feedback-nursery for unknown types,
  - the shared anchor resolver (objective -> cited TEKS -> none),
  - the advisory alignment scorer's "cannot assess" path (no anchor),
  - alignment evidence-binding with a FAKE model (cited vs uncited band),
  - the pure per-unit rollup (gate counts, deterministic gaps, cannot-assess),
  - hermetic enumeration from a tiny on-disk ledger/manifest fixture.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import artifact_scorers  # noqa: F401 — registers the presence/alignment scorers
import artifact_rung
from artifact_scorers import ANCHOR_OBJECTIVE, ANCHOR_TEKS
from lesson_scoring import ArtifactInput, LessonElement, build_scorer


def _artifact(doc_type: str, els: list[tuple[str, str]], **kw) -> ArtifactInput:
    elements = [LessonElement(f"e{i}", t, ex) for i, (t, ex) in enumerate(els)]
    return ArtifactInput(
        project_id="proj",
        lesson_id=kw.get("doc_id", "d1"),
        unit_id=kw.get("unit_id", "u1"),
        title=kw.get("title", "Artifact"),
        elements=elements,
        doc_type=doc_type,
        anchor=kw.get("anchor"),
    )


# --- presence (deterministic gate) ------------------------------------------


def test_presence_gate_pass() -> None:
    art = _artifact("quiz", [("assessment_checkpoint", "1. Which is a variable? Select one.")])
    res = build_scorer("artifact_presence").score(art, None)
    assert res.summary["gate_pass"] is True
    assert res.summary["role"] == "quiz"
    assert res.summary["missing_required"] == []


def test_presence_gate_fail_names_gap() -> None:
    # A "quiz" with only logistics text and no items must fail its required gate and
    # NAME the missing part (so the unit rung can surface a real structural gap).
    art = _artifact("quiz", [("logistics_materials", "Bring a pencil. 30 minutes.")])
    res = build_scorer("artifact_presence").score(art, None)
    assert res.summary["gate_pass"] is False
    assert "Assessment items present" in res.summary["missing_required"]


def test_fallback_and_nursery() -> None:
    # An unknown type resolves to the generic fallback spec and is flagged for the
    # feedback nursery (the "grow a Path" signal), never crashing.
    art = _artifact("mystery_type", [("direct_instruction", "Some content here for students.")])
    res = build_scorer("artifact_presence").score(art, None)
    assert res.summary["is_fallback"] is True
    assert res.summary["nursery"] is True
    rec = artifact_rung.artifact_record(art, res)
    entries = artifact_rung._nursery_entries([rec])
    assert len(entries) == 1
    assert entries[0]["doc_type"] == "mystery_type"
    assert entries[0]["reason"] == "weak_or_unknown_type"


# --- anchor resolver --------------------------------------------------------


def test_anchor_resolver_prefers_objective() -> None:
    lessons = [
        ArtifactInput("proj", "L1", "u1", "Lesson 1", [
            LessonElement("L1e0", "standards_objectives", "Students will identify variables."),
        ]),
    ]
    anchors = artifact_rung.resolve_unit_anchors("proj", lessons=lessons)
    assert anchors["u1"]["kind"] == ANCHOR_OBJECTIVE
    assert "identify variables" in anchors["u1"]["text"]


def test_anchor_resolver_falls_back_to_teks() -> None:
    lessons = [
        ArtifactInput("proj", "L1", "u1", "Lesson 1", [
            LessonElement("L1e0", "direct_instruction", "This lesson addresses TEKS 130.362(c)(1)(A) content."),
        ]),
    ]
    anchors = artifact_rung.resolve_unit_anchors("proj", lessons=lessons)
    assert anchors["u1"]["kind"] == ANCHOR_TEKS
    assert "130.362" in anchors["u1"]["text"]


def test_anchor_resolver_none_when_no_objective_or_teks() -> None:
    lessons = [
        ArtifactInput("proj", "L1", "u1", "Lesson 1", [
            LessonElement("L1e0", "hook_engagement", "Let's get started with a fun warm-up!"),
        ]),
    ]
    anchors = artifact_rung.resolve_unit_anchors("proj", lessons=lessons)
    assert "u1" not in anchors  # -> artifacts resolve to the NONE anchor -> lesson gap


# --- alignment (advisory, model) --------------------------------------------


def test_alignment_cannot_assess_without_anchor() -> None:
    art = _artifact("exit_ticket", [("assessment_checkpoint", "Explain today's concept.")])
    res = build_scorer("artifact_alignment").score(art, None)  # no anchor set
    assert res.summary["cannot_assess"] is True
    assert res.summary["advisory"] is True
    assert all("cannot assess" in c.note for c in res.criteria)


def test_alignment_fallback_type_not_applicable() -> None:
    # The generic fallback has no alignment block -> advisory is simply not applicable.
    art = _artifact("mystery_type", [("direct_instruction", "content")], anchor={
        "kind": ANCHOR_OBJECTIVE, "text": "Students will do a thing."})
    res = build_scorer("artifact_alignment").score(art, None)
    assert res.summary["applicable"] is False


def test_alignment_binds_evidence_with_fake_model() -> None:
    """With an anchor + a fake model: a band that cites a REAL element id is trusted
    (carries evidence); a band that cites a bogus id is downgraded to needs-review."""
    import layer1

    art = _artifact(
        "exit_ticket",
        [("assessment_checkpoint", "Identify one variable in the scenario and justify.")],
        anchor={"kind": ANCHOR_OBJECTIVE, "text": "Students will identify variables."},
    )

    # Fake model: cite the real element id for the first criterion, a bogus id for
    # the second. call_and_parse_with_retry(cfg, role, prompt, tag) -> dict.
    def fake_call(cfg, role, prompt, tag):
        return {
            "scores": [
                {"criterion_id": "aligned_to_objective", "band": 3,
                 "evidence_element_id": "e0", "evidence_quote": "Identify one variable",
                 "note": "directly targets the objective"},
                {"criterion_id": "actionable", "band": 2,
                 "evidence_element_id": "does_not_exist", "evidence_quote": "x",
                 "note": "somewhat"},
            ]
        }

    orig = layer1.call_and_parse_with_retry
    layer1.call_and_parse_with_retry = fake_call
    try:
        res = build_scorer("artifact_alignment").score(art, {"fake": "cfg"})
    finally:
        layer1.call_and_parse_with_retry = orig

    by_id = {c.criterion_id: c for c in res.criteria}
    assert by_id["aligned_to_objective"].band == 3
    assert by_id["aligned_to_objective"].is_evidenced()  # real id -> trusted
    assert not by_id["actionable"].is_evidenced()  # bogus id -> not trusted
    assert "needs review" in by_id["actionable"].note
    assert res.summary["applicable"] is True


# --- rollup (pure) ----------------------------------------------------------


def test_rollup_units_gates_and_gaps() -> None:
    good = _artifact("exit_ticket", [("assessment_checkpoint", "Answer the prompt.")], unit_id="u1")
    bad = _artifact("quiz", [("logistics_materials", "bring pencil")], unit_id="u1", doc_id="d2")
    pres = build_scorer("artifact_presence")
    recs = [
        artifact_rung.artifact_record(good, pres.score(good, None)),
        artifact_rung.artifact_record(bad, pres.score(bad, None)),
    ]
    units = artifact_rung.rollup_units(recs)
    u = units["u1"]
    assert u["artifact_count"] == 2
    assert u["gate_pass_count"] == 1
    assert u["has_artifact_gap"] is True
    assert any(g["role"] == "quiz" for g in u["deterministic_gaps"])


# --- enumeration (hermetic, tiny on-disk fixture) ---------------------------


def test_enumerate_excludes_lessons(tmp_path: Path | None = None) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj = root / "projects" / "mini-artifact"
        (proj / "layer0").mkdir(parents=True)
        (proj / "manifest.yaml").write_text(
            "units:\n  u1:\n    title: Unit One\n    documents:\n"
            "      - doc_aaaa01_Unit1_Lesson_Plan.txt\n"
            "      - doc_aaaa02_Unit1_Quiz.txt\n"
            "      - doc_aaaa03_Unit1_Rubric.txt\n"
        )
        ledger = [
            {"doc_id": "aaaa01", "element_id": "aaaa01_e0", "element_type": "standards_objectives",
             "excerpt": "SWBAT do things", "source_file": "doc_aaaa01_Unit1_Lesson_Plan.txt"},
            {"doc_id": "aaaa02", "element_id": "aaaa02_e0", "element_type": "assessment_checkpoint",
             "excerpt": "1. Question?", "source_file": "doc_aaaa02_Unit1_Quiz.txt"},
            {"doc_id": "aaaa03", "element_id": "aaaa03_e0", "element_type": "assessment_checkpoint",
             "excerpt": "Criteria: exceeds/meets. 4 points.", "source_file": "doc_aaaa03_Unit1_Rubric.txt"},
        ]
        (proj / "layer0" / "ledger.json").write_text(json.dumps(ledger))

        import audit_lib
        orig_base = audit_lib.BASE_DIR
        audit_lib.BASE_DIR = root
        try:
            arts = artifact_rung.enumerate_artifacts("mini-artifact")
        finally:
            audit_lib.BASE_DIR = orig_base

        roles = sorted(a.doc_type for a in arts)
        # Lesson plan excluded; quiz + rubric enumerated and mapped to u1.
        assert roles == ["quiz", "rubric"]
        assert all(a.unit_id == "u1" for a in arts)


if __name__ == "__main__":
    tests = [
        test_presence_gate_pass,
        test_presence_gate_fail_names_gap,
        test_fallback_and_nursery,
        test_anchor_resolver_prefers_objective,
        test_anchor_resolver_falls_back_to_teks,
        test_anchor_resolver_none_when_no_objective_or_teks,
        test_alignment_cannot_assess_without_anchor,
        test_alignment_fallback_type_not_applicable,
        test_alignment_binds_evidence_with_fake_model,
        test_rollup_units_gates_and_gaps,
        test_enumerate_excludes_lessons,
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
