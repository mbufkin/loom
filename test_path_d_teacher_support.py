#!/usr/bin/env python3
"""
test_path_d_teacher_support.py — Offline Path D presence tests (no corpus).

Best practice: synthetic fixtures under tests/fixtures/path_d/ prove D2–D4;
temp projects prove findings.json write. Real BB evidence seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.teacher_support import (  # noqa: E402
    d_presence_for_step,
    load_teacher_support_checklist,
    run_path_d_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_d"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "teacher_support",
            "excerpt": text,
        }
    ]


def test_teacher_edition_routes_to_d() -> None:
    wf, path, _, reason = resolve_workflow(
        doc_type="other",
        source_file="K-5_Math_Grade_5_Module_1_Teacher_Edition.pdf",
        graph_hint=None,
    )
    assert (wf, path) == ("teacher_support", "D")
    assert "teacher_support" in reason or "filename" in reason


def test_program_implementation_stays_on_f() -> None:
    """Bare program+implementation guides stay Path F (D plate left router alone)."""
    wf, path, _, _ = resolve_workflow(
        doc_type="other",
        source_file="Secondary_Mathematics_Program_and_Implementation_Guide.pdf",
        graph_hint=None,
    )
    assert (wf, path) == ("standards_pacing", "F")


def test_checklist_loads_d2_d4() -> None:
    cl = load_teacher_support_checklist()
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert {"D2", "D3", "D4"} <= steps


def test_strong_te_presence() -> None:
    text = (FIXTURES / "strong_te.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("d1", text)
    cl = load_teacher_support_checklist()
    d2 = d_presence_for_step(elements, cl, "D2")
    d3 = d_presence_for_step(elements, cl, "D3")
    d4 = d_presence_for_step(elements, cl, "D4")
    assert d2["status"] in {"PRESENT", "PARTIAL"}
    assert d3["status"] in {"PRESENT", "PARTIAL"}
    assert d4["status"] == "PRESENT"


def test_weak_te_lacks_facilitation() -> None:
    text = (FIXTURES / "weak_te.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("d2", text)
    cl = load_teacher_support_checklist()
    d3 = d_presence_for_step(elements, cl, "D3")
    assert d3["status"] == "MISSING"


def test_run_path_d_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_d_teacher_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_d1_Module_1_Teacher_Edition.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_te.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "d1",
                    "doc_type": "other",
                    "workflow_id": "teacher_support",
                    "path": "D",
                    "lens": "Teacher support",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_d_for_project(pid)
        assert out["path"] == "D"
        assert out["doc_ids"] == ["d1"]
        assert out["steps_by_doc"]["d1"]["D2"]["status"] in {
            "PRESENT",
            "PARTIAL",
        }
        assert out["steps_by_doc"]["d1"]["D5"]["status"] == "STUB"
        findings = json.loads(
            (root / "path_d" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("teacher_support.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_teacher_edition_routes_to_d,
        test_program_implementation_stays_on_f,
        test_checklist_loads_d2_d4,
        test_strong_te_presence,
        test_weak_te_lacks_facilitation,
        test_run_path_d_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
