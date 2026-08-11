#!/usr/bin/env python3
"""
test_artifact_rung.py — Offline Path B–H → ARTIFACT-RUNG rollup tests.

Best practice: synthetic path_<letter>/findings.json under a temp project prove
the gate rules without a live corpus. Real Dallas severity stays a manual smoke
(python3 artifact_rung.py --project dallas-career-2026).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from artifact_rung import (  # noqa: E402
    build_artifact_rung,
    collect_path_records,
    load_checklist,
    rollup_units,
    score_inventory_item,
)
from lesson_bakeoff import LESSON_DOC_TYPES, enumerate_lessons  # noqa: E402
from unit_rung import _unit_artifacts  # noqa: E402


def _write_project(pid: str, *, units: dict, paths: dict[str, dict]) -> Path:
    """Minimal project tree: manifest + path findings (+ optional route-map)."""
    from audit_lib import project_dir

    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "manifest.yaml").write_text(
        "project:\n  id: " + pid + "\nunits:\n"
        + "".join(
            f"  {uid}:\n    title: {uid}\n    documents:\n"
            + "".join(f"    - {rel}\n" for rel in docs)
            for uid, docs in units.items()
        ),
        encoding="utf-8",
    )
    routes = []
    for letter, findings in paths.items():
        pdir = root / f"path_{letter}"
        pdir.mkdir(parents=True)
        (pdir / "findings.json").write_text(
            json.dumps(findings, indent=2), encoding="utf-8"
        )
        for item in findings.get("inventory") or []:
            did = item.get("doc_id")
            if not did:
                continue
            src = f"doc_{did}_Sample_Quiz.txt"
            routes.append(
                {
                    "doc_id": did,
                    "doc_type": item.get("doc_type", "quiz"),
                    "path": letter.upper(),
                    "source_file": src,
                }
            )
    (root / "layer0").mkdir(parents=True)
    (root / "layer0" / "route-map.json").write_text(
        json.dumps({"project_id": pid, "routes": routes}), encoding="utf-8"
    )
    return root


def test_all_present_passes_gate() -> None:
    presence = score_inventory_item(
        {
            "doc_id": "aaaa",
            "doc_type": "quiz",
            "B1": {"status": "PRESENT", "note": "ok"},
            "B2": {"status": "PRESENT", "note": "ok"},
            "B6": {"status": "STUB", "note": "emit TBD"},
        },
        {"B1": "Inventory", "B2": "Item stems"},
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is True
    assert presence["missing_required"] == []
    assert presence["coverage"] == 1.0


def test_missing_step_fails_gate_and_names_gap() -> None:
    presence = score_inventory_item(
        {
            "doc_id": "bbbb",
            "doc_type": "quiz",
            "B2": {"status": "PRESENT", "note": "ok"},
            "B3": {"status": "MISSING", "note": "0/2 fields present"},
            "B6": {"status": "STUB", "note": "emit TBD"},
        },
        {"B2": "Item stems", "B3": "Answer key signal"},
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is False
    assert "B3 Answer key signal" in presence["missing_required"]


def test_stub_and_not_applicable_ignored() -> None:
    presence = score_inventory_item(
        {
            "doc_id": "cccc",
            "doc_type": "rubric",
            "B2": {"status": "PRESENT", "note": "ok"},
            "B5": {"status": "NOT_APPLICABLE", "note": "pairing N/A"},
            "B6": {"status": "STUB", "note": "emit TBD"},
        },
        {"B2": "Item stems"},
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is True
    assert len(presence["criteria"]) == 1
    assert presence["criteria"][0]["criterion_id"] == "B2"


def test_partial_does_not_fail_gate() -> None:
    presence = score_inventory_item(
        {
            "doc_id": "dddd",
            "doc_type": "quiz",
            "B2": {"status": "PARTIAL", "note": "1/2"},
            "B3": {"status": "PRESENT", "note": "ok"},
        },
        {"B2": "Item stems", "B3": "Answer key signal"},
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is True
    assert presence["missing_required"] == []
    # PARTIAL is not PRESENT — coverage counts only full PRESENT toward the rate.
    assert presence["coverage"] == 0.5


def test_optional_absent_is_advisory() -> None:
    """OPTIONAL_ABSENT (all-optional step, no hit) must not fail the gate."""
    labels = load_checklist("workflows/checklists/assessment.yaml")
    assert "B4" in labels  # assessment B4 is the all-optional fixture
    presence = score_inventory_item(
        {
            "doc_id": "eeee",
            "doc_type": "quiz",
            "B2": {"status": "PRESENT", "note": "ok"},
            "B3": {"status": "PRESENT", "note": "ok"},
            "B4": {"status": "OPTIONAL_ABSENT", "note": "0/0 fields present"},
        },
        labels,
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is True
    assert presence["missing_required"] == []
    # Still visible in criteria — advisory status, not a gap.
    assert any(
        c["criterion_id"] == "B4" and c["verdict"] == "OPTIONAL_ABSENT"
        for c in presence["criteria"]
    )


def test_partly_required_missing_still_fails() -> None:
    """A MISSING step remains a deterministic gap — OPTIONAL_ABSENT is the only
    soft-absent status; bare MISSING always gates."""
    presence = score_inventory_item(
        {
            "doc_id": "ffff",
            "doc_type": "quiz",
            "B2": {"status": "PRESENT", "note": "ok"},
            "B3": {"status": "MISSING", "note": "0/2 fields present"},
        },
        {"B2": "Item stems", "B3": "Answer key signal"},
        path="B",
        lens="Assessment",
    )
    assert presence["gate_pass"] is False
    assert "B3 Answer key signal" in presence["missing_required"]


def test_skipped_path_contributes_nothing() -> None:
    from audit_lib import project_dir

    pid = "_tmp_artifact_rung_skipped"
    root = project_dir(pid)
    try:
        # doc_ids must be hex — doc_id_from_filename only strips doc_<hex>_ prefixes.
        _write_project(
            pid,
            units={"u1": ["doc_aaaa01_Sample_Quiz.txt"]},
            paths={
                "b": {
                    "project_id": pid,
                    "path": "B",
                    "lens": "Assessment",
                    "status": "skipped",
                    "checklist": "workflows/checklists/assessment.yaml",
                    "inventory": [
                        {
                            "doc_id": "aaaa01",
                            "doc_type": "quiz",
                            "B2": {"status": "MISSING", "note": "should be ignored"},
                        }
                    ],
                },
                "f": {
                    "project_id": pid,
                    "path": "F",
                    "lens": "Standards",
                    "status": "skipped",
                    "checklist": "workflows/checklists/standards_pacing.yaml",
                    "inventory": [],
                },
            },
        )
        records = collect_path_records(pid)
        assert records == []
    finally:
        if root.exists():
            shutil.rmtree(root)


def test_unlinked_doc_lands_in_unlinked_bucket() -> None:
    from audit_lib import project_dir

    pid = "_tmp_artifact_rung_unlinked"
    root = project_dir(pid)
    try:
        # Manifest only knows aaaa01 — dead99 is deliberately absent.
        _write_project(
            pid,
            units={"u1": ["doc_aaaa01_Sample_Quiz.txt"]},
            paths={
                "b": {
                    "project_id": pid,
                    "path": "B",
                    "lens": "Assessment",
                    "status": "ok",
                    "checklist": "workflows/checklists/assessment.yaml",
                    "inventory": [
                        {
                            "doc_id": "aaaa01",
                            "doc_type": "quiz",
                            "B2": {"status": "PRESENT", "note": "ok"},
                        },
                        {
                            "doc_id": "dead99",
                            "doc_type": "quiz",
                            "B2": {"status": "PRESENT", "note": "ok"},
                        },
                    ],
                }
            },
        )
        records = collect_path_records(pid)
        by_id = {r["doc_id"]: r for r in records}
        assert by_id["aaaa01"]["unit_id"] == "u1"
        assert by_id["dead99"]["unit_id"] == "(unlinked)"
    finally:
        if root.exists():
            shutil.rmtree(root)


def test_build_writes_json_unit_rung_can_read() -> None:
    from audit_lib import project_dir

    pid = "_tmp_artifact_rung_build"
    root = project_dir(pid)
    try:
        _write_project(
            pid,
            units={"u1": ["doc_aaaa01_Sample_Quiz.txt", "doc_bbbb02_Sample_Quiz.txt"]},
            paths={
                "b": {
                    "project_id": pid,
                    "path": "B",
                    "lens": "Assessment",
                    "status": "ok",
                    "checklist": "workflows/checklists/assessment.yaml",
                    "inventory": [
                        {
                            "doc_id": "aaaa01",
                            "doc_type": "quiz",
                            "B2": {"status": "PRESENT", "note": "ok"},
                            "B3": {"status": "PRESENT", "note": "ok"},
                            "B6": {"status": "STUB", "note": "emit TBD"},
                        },
                        {
                            "doc_id": "bbbb02",
                            "doc_type": "quiz",
                            "B2": {"status": "PRESENT", "note": "ok"},
                            "B3": {"status": "MISSING", "note": "0/2"},
                            "B6": {"status": "STUB", "note": "emit TBD"},
                        },
                    ],
                },
                "h": {
                    "project_id": pid,
                    "path": "H",
                    "lens": "Exit ticket",
                    "status": "skipped",
                    "checklist": "workflows/checklists/exit_ticket.yaml",
                    "inventory": [],
                },
            },
        )
        dest = build_artifact_rung(pid)
        assert dest.is_file()
        data = json.loads(dest.read_text(encoding="utf-8"))
        for key in (
            "project_id",
            "presence_scorer",
            "alignment_scorer",
            "with_model",
            "summary",
            "units",
            "artifacts",
        ):
            assert key in data, f"missing top-level key {key!r}"

        assert data["alignment_scorer"] is None
        assert data["with_model"] is False
        assert data["summary"]["artifact_count"] == 2
        assert data["summary"]["gate_pass_count"] == 1

        unit = data["units"]["u1"]
        # Every field _unit_artifacts() reads must be present and shaped right.
        shaped = _unit_artifacts(unit)
        assert shaped["count"] == 2
        assert shaped["gate_pass"] == 1
        assert shaped["has_gap"] is True
        assert len(shaped["deterministic_gaps"]) == 1
        assert shaped["deterministic_gaps"][0]["doc_id"] == "bbbb02"
        assert shaped["cannot_assess_alignment"] == 0
        assert "quiz" in shaped["roles"]

        # Rollup helper agrees with the written unit block.
        rolled = rollup_units(data["artifacts"])
        assert rolled["u1"]["has_artifact_gap"] is True
        assert rolled["u1"]["gate_pass_rate"] == 0.5

        md = (root / "layer_artifact" / "ARTIFACT-RUNG.md").read_text(encoding="utf-8")
        assert "Paths B–H" in md
        assert "u1" in md
    finally:
        if root.exists():
            shutil.rmtree(root)


def test_rollup_excludes_lesson_doc_types() -> None:
    """artifact_rung and lesson_rung must enumerate disjoint document sets.

    Path E inventorizes lesson_content; without the LESSON_DOC_TYPES skip those
    docs would be graded as both lessons and artifacts (the contradiction the
    pre-rewrite enumerator avoided).
    """
    from audit_lib import project_dir

    pid = "_tmp_artifact_rung_disjoint"
    root = project_dir(pid)
    try:
        lesson_src = "doc_aa11bb22cc33_Cluster_Slides.txt"
        quiz_src = "doc_dd44ee55ff66_Cluster_Quiz.txt"
        _write_project(
            pid,
            units={"u1": [lesson_src, quiz_src]},
            paths={
                "e": {
                    "project_id": pid,
                    "path": "E",
                    "lens": "Student practice",
                    "status": "ok",
                    "checklist": "workflows/checklists/student_practice.yaml",
                    "inventory": [
                        {
                            "doc_id": "aa11bb22cc33",
                            "doc_type": "lesson_content",
                            "E2": {"status": "MISSING", "note": "would false-gap"},
                            "E4": {"status": "MISSING", "note": "optional"},
                        }
                    ],
                },
                "b": {
                    "project_id": pid,
                    "path": "B",
                    "lens": "Assessment",
                    "status": "ok",
                    "checklist": "workflows/checklists/assessment.yaml",
                    "inventory": [
                        {
                            "doc_id": "dd44ee55ff66",
                            "doc_type": "quiz",
                            "B2": {"status": "PRESENT", "note": "ok"},
                            "B3": {"status": "PRESENT", "note": "ok"},
                        }
                    ],
                },
            },
        )
        # Route-map from _write_project uses Sample_Quiz names; overwrite with
        # filenames classify_doc_type will read as lesson_content vs quiz, and
        # give lesson_bakeoff a Layer 0 ledger to enumerate from.
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "aa11bb22cc33",
                    "doc_type": "lesson_content",
                    "path": "E",
                    "source_file": lesson_src,
                },
                {
                    "doc_id": "dd44ee55ff66",
                    "doc_type": "quiz",
                    "path": "B",
                    "source_file": quiz_src,
                },
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text(
            json.dumps(
                [
                    {
                        "doc_id": "aa11bb22cc33",
                        "source_file": lesson_src,
                        "element_id": "aa11bb22cc33:1",
                        "element_type": "instruction",
                        "excerpt": "Slide deck content for the cluster overview.",
                    },
                    {
                        "doc_id": "dd44ee55ff66",
                        "source_file": quiz_src,
                        "element_id": "dd44ee55ff66:1",
                        "element_type": "assessment_item",
                        "excerpt": "1. What is a career cluster?",
                    },
                ]
            ),
            encoding="utf-8",
        )

        assert "lesson_content" in LESSON_DOC_TYPES
        art_ids = {r["doc_id"] for r in collect_path_records(pid)}
        lesson_ids = {le.lesson_id for le in enumerate_lessons(pid)}
        assert "dd44ee55ff66" in art_ids
        assert "aa11bb22cc33" not in art_ids
        assert "aa11bb22cc33" in lesson_ids
        assert art_ids.isdisjoint(lesson_ids), (
            f"rungs overlap on {sorted(art_ids & lesson_ids)}"
        )
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_all_present_passes_gate,
        test_missing_step_fails_gate_and_names_gap,
        test_stub_and_not_applicable_ignored,
        test_partial_does_not_fail_gate,
        test_optional_absent_is_advisory,
        test_partly_required_missing_still_fails,
        test_skipped_path_contributes_nothing,
        test_unlinked_doc_lands_in_unlinked_bucket,
        test_build_writes_json_unit_rung_can_read,
        test_rollup_excludes_lesson_doc_types,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
