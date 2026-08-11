#!/usr/bin/env python3
"""
test_path_e_student_practice.py — Offline Path E presence tests (no corpus).

Best practice: synthetic fixtures under tests/fixtures/path_e/ prove E2–E4;
temp projects prove findings.json write. Real G5 seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.student_practice import (  # noqa: E402
    e_presence_for_step,
    load_student_practice_checklist,
    run_path_e_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_e"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "student_practice",
            "excerpt": text,
        }
    ]


def test_learn_filename_routes_to_e() -> None:
    wf, path, _, reason = resolve_workflow(
        doc_type="other",
        source_file="K-5_Math_Grade_5_Module_1_Learn_Student_Edition.pdf",
        graph_hint=None,
    )
    assert (wf, path) == ("student_practice", "E")
    assert "student_practice" in reason or "filename" in reason


def test_worksheet_routes_to_e() -> None:
    wf, path, _, _ = resolve_workflow(
        doc_type="worksheet",
        source_file="Transportation_Student_Worksheet.txt",
        graph_hint=None,
    )
    assert (wf, path) == ("student_practice", "E")


def test_checklist_loads_e2_e4() -> None:
    cl = load_student_practice_checklist()
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert {"E2", "E3", "E4"} <= steps


def test_strong_learn_presence() -> None:
    text = (FIXTURES / "strong_learn.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("e1", text)
    cl = load_student_practice_checklist()
    e2 = e_presence_for_step(elements, cl, "E2")
    e3 = e_presence_for_step(elements, cl, "E3")
    e4 = e_presence_for_step(elements, cl, "E4")
    assert e2["status"] in {"PRESENT", "PARTIAL"}
    assert e3["status"] in {"PRESENT", "PARTIAL"}
    assert e4["status"] == "PRESENT"


def test_weak_practice_lacks_tasks() -> None:
    text = (FIXTURES / "weak_practice.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("e2", text)
    cl = load_student_practice_checklist()
    e3 = e_presence_for_step(elements, cl, "E3")
    assert e3["status"] == "MISSING"


def test_run_path_e_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_e_student_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_e1_Module_1_Learn_Student_Edition.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_learn.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "e1",
                    "doc_type": "other",
                    "workflow_id": "student_practice",
                    "path": "E",
                    "lens": "Student practice",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_e_for_project(pid)
        assert out["path"] == "E"
        assert out["doc_ids"] == ["e1"]
        assert out["steps_by_doc"]["e1"]["E2"]["status"] in {
            "PRESENT",
            "PARTIAL",
        }
        assert out["steps_by_doc"]["e1"]["E5"]["status"] == "STUB"
        findings = json.loads(
            (root / "path_e" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("student_practice.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_learn_filename_routes_to_e,
        test_worksheet_routes_to_e,
        test_checklist_loads_e2_e4,
        test_strong_learn_presence,
        test_weak_practice_lacks_tasks,
        test_run_path_e_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
