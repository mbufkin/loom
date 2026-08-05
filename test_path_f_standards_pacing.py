#!/usr/bin/env python3
"""
test_path_f_standards_pacing.py — Offline Path F presence tests (no corpus).

Best practice: synthetic fixtures under tests/fixtures/path_f/ prove F2–F4;
temp projects prove findings.json write. Real Alg1 seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.standards_pacing import (  # noqa: E402
    f_presence_for_step,
    load_standards_pacing_checklist,
    run_path_f_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_f"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "standards_objectives",
            "excerpt": text,
        }
    ]


def test_yag_filename_routes_to_f() -> None:
    wf, path, _, reason = resolve_workflow(
        doc_type="other",
        source_file="Algebra_I_Math_YAG_150-day.pdf",
        graph_hint=None,
    )
    assert (wf, path) == ("standards_pacing", "F")
    assert "standards_pacing" in reason or "filename" in reason


def test_checklist_loads_f2_f4() -> None:
    cl = load_standards_pacing_checklist()
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert {"F2", "F3", "F4"} <= steps


def test_strong_pacing_presence() -> None:
    text = (FIXTURES / "strong_pacing.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("f1", text)
    cl = load_standards_pacing_checklist()
    f2 = f_presence_for_step(elements, cl, "F2")
    f3 = f_presence_for_step(elements, cl, "F3")
    f4 = f_presence_for_step(elements, cl, "F4")
    assert f2["status"] in {"PRESENT", "PARTIAL"}
    assert f3["status"] in {"PRESENT", "PARTIAL"}
    assert f4["status"] == "PRESENT"


def test_weak_sequence_lacks_standards() -> None:
    text = (FIXTURES / "weak_sequence.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("f2", text)
    cl = load_standards_pacing_checklist()
    f4 = f_presence_for_step(elements, cl, "F4")
    assert f4["status"] == "MISSING"


def test_run_path_f_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_f_standards_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_f1_Algebra_I_Topic_Pacing_Guide.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_pacing.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "f1",
                    "doc_type": "other",
                    "workflow_id": "standards_pacing",
                    "path": "F",
                    "lens": "Standards & pacing",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_f_for_project(pid)
        assert out["path"] == "F"
        assert out["doc_ids"] == ["f1"]
        assert out["steps_by_doc"]["f1"]["F2"]["status"] in {
            "PRESENT",
            "PARTIAL",
        }
        assert out["steps_by_doc"]["f1"]["F5"]["status"] == "STUB"
        findings = json.loads(
            (root / "path_f" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("standards_pacing.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_yag_filename_routes_to_f,
        test_checklist_loads_f2_f4,
        test_strong_pacing_presence,
        test_weak_sequence_lacks_standards,
        test_run_path_f_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
