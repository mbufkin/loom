#!/usr/bin/env python3
"""
test_path_b_assessment.py — Offline Path B presence tests (no corpus required).

Best practice: synthetic fixtures under tests/fixtures/path_b/ prove B2–B5;
temp projects prove findings.json write. Real Dallas seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from workflows.quiz import (  # noqa: E402
    load_assessment_checklist,
    pair_key,
    run_path_b_for_project,
    b_presence_for_step,
)


FIXTURES = BASE / "tests" / "fixtures" / "path_b"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "assessment_item",
            "excerpt": text,
        }
    ]


def test_checklist_loads_b2_b4() -> None:
    cl = load_assessment_checklist()
    assert cl.get("path") == "B" or "b2_items" in (cl.get("sections") or {})
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert {"B2", "B3", "B4"} <= steps


def test_pair_key_joins_quiz_and_answer_key() -> None:
    q = pair_key("doc_fc48920a5ca9_Engineering_Lesson_Quiz___Quizizz.txt")
    k = pair_key(
        "doc_86fff193b91a_Engineering_Lesson_Quiz___Quizizz_Answer_key.txt"
    )
    assert q == k
    assert "engineering" in q and "lesson" in q


def test_strong_quiz_presence() -> None:
    text = (FIXTURES / "strong_quiz.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("q1", text)
    cl = load_assessment_checklist()
    b2 = b_presence_for_step(elements, cl, "B2")
    assert b2["status"] in {"PRESENT", "PARTIAL"}
    assert b2["present"] >= 1


def test_strong_key_presence() -> None:
    text = (FIXTURES / "strong_key.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("k1", text)
    cl = load_assessment_checklist()
    b3 = b_presence_for_step(elements, cl, "B3")
    assert b3["status"] in {"PRESENT", "PARTIAL"}
    assert b3["present"] >= 1


def test_run_path_b_pairs_and_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_b_assessment_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        quiz_name = "doc_aaaa01_Engineering_Lesson_Quiz___Quizizz.txt"
        key_name = "doc_aaaa02_Engineering_Lesson_Quiz___Quizizz_Answer_key.txt"
        orphan_name = "doc_bbbb01_Orphan_Quiz.txt"
        (root / "sources" / quiz_name).write_text(
            (FIXTURES / "strong_quiz.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / "sources" / key_name).write_text(
            (FIXTURES / "strong_key.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / "sources" / orphan_name).write_text(
            (FIXTURES / "orphan_quiz.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "aaaa01",
                    "doc_type": "quiz",
                    "workflow_id": "quiz",
                    "path": "B",
                    "source_file": quiz_name,
                },
                {
                    "doc_id": "aaaa02",
                    "doc_type": "answer_key",
                    "workflow_id": "quiz",
                    "path": "B",
                    "source_file": key_name,
                },
                {
                    "doc_id": "bbbb01",
                    "doc_type": "quiz",
                    "workflow_id": "quiz",
                    "path": "B",
                    "source_file": orphan_name,
                },
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_b_for_project(pid)
        assert out["path"] == "B"
        assert set(out["doc_ids"]) == {"aaaa01", "aaaa02", "bbbb01"}
        steps = out["steps_by_doc"]
        assert steps["aaaa01"]["B5"]["status"] == "PRESENT"
        assert steps["aaaa02"]["B5"]["status"] == "PRESENT"
        assert steps["bbbb01"]["B5"]["status"] == "PARTIAL"
        assert steps["aaaa01"]["B2"]["status"] in {"PRESENT", "PARTIAL"}
        assert steps["aaaa02"]["B3"]["status"] in {"PRESENT", "PARTIAL"}
        findings = json.loads(
            (root / "path_b" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("assessment.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_checklist_loads_b2_b4,
        test_pair_key_joins_quiz_and_answer_key,
        test_strong_quiz_presence,
        test_strong_key_presence,
        test_run_path_b_pairs_and_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
