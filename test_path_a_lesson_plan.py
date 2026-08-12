#!/usr/bin/env python3
"""
test_path_a_lesson_plan.py — Offline Path A presence tests (no corpus required).

Best practice: synthetic fixtures under tests/fixtures/path_a/ prove A2–A5;
temp projects prove findings.json write. Real Dallas seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from lesson_plan_fill import load_daily_lesson_checklist  # noqa: E402
from route import resolve_workflow  # noqa: E402
from workflows.lesson_plan import (  # noqa: E402
    a2_standards,
    a3_coherence,
    a5_hunter_matrix,
    run_path_a_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_a"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    """One element per non-empty line so keyword and type matchers both fire."""
    elements = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if "teks" in lower or "§" in line:
            etype = "standards_objectives"
        elif "objective" in lower or "today you will" in lower:
            etype = "standards_objectives"
        elif "anticipatory" in lower or "do now" in lower or "engage" in lower:
            etype = "hook_engagement"
        elif "modeling" in lower or "i do" in lower:
            etype = "direct_instruction"
        elif "guided practice" in lower or "we do" in lower:
            etype = "guided_practice"
        elif "independent practice" in lower or "you do" in lower:
            etype = "independent_practice"
        elif "check for understanding" in lower or "exit ticket" in lower:
            etype = "assessment_checkpoint"
        elif "closure" in lower or "wrap up" in lower:
            etype = "reflection_closure"
        elif "direct instruction" in lower or "teach" in lower:
            etype = "direct_instruction"
        else:
            etype = "unclear"
        elements.append(
            {
                "doc_id": doc_id,
                "element_id": f"{doc_id}:{i}",
                "element_type": etype,
                "excerpt": line,
            }
        )
    return elements


def test_lesson_plan_routes_to_a() -> None:
    wf, path, fb, _ = resolve_workflow(
        doc_type="lesson_plan",
        source_file="Family_Services_Lesson_Plan.docx",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("lesson_plan", "A", False)


def test_checklist_loads_hunter_core() -> None:
    cl = load_daily_lesson_checklist()
    assert cl.get("path") == "A"
    assert cl.get("workflow_id") == "lesson_plan"
    field_ids = {
        f.get("id")
        for section in (cl.get("sections") or {}).values()
        for f in (section.get("fields") or [])
    }
    assert {
        "anticipatory_set",
        "objective_purpose",
        "guided_practice",
        "closure",
    } <= field_ids


def test_strong_lesson_a2_a5() -> None:
    text = (FIXTURES / "strong_lesson.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("l1", text)
    cl = load_daily_lesson_checklist()
    a2 = a2_standards(elements)
    assert a2["teks"]["status"] == "PRESENT"
    assert a2["objective"]["status"] == "PRESENT"
    a3 = a3_coherence(elements, a2)
    assert a3["status"] == "COHERENT"
    a5 = a5_hunter_matrix(elements, cl)
    assert a5["hunter_core_present"] >= 6
    assert a5["hunter_core_total"] == 8


def test_run_path_a_writes_shared_findings_shape() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_a_lesson_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_lesson1_Career_Cluster_Lesson_Plan.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_lesson.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        # Ledger elements so A2–A5 have evidence without a corpus extract step.
        elements = _elements_from_text(
            "lesson1",
            (FIXTURES / "strong_lesson.txt").read_text(encoding="utf-8"),
        )
        (root / "layer0" / "ledger.json").write_text(
            json.dumps(elements), encoding="utf-8"
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "lesson1",
                    "doc_type": "lesson_plan",
                    "workflow_id": "lesson_plan",
                    "path": "A",
                    "lens": "Lesson",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        out = run_path_a_for_project(pid, use_model=False)
        assert out["path"] == "A"
        assert out["status"] == "ok"
        assert out["lens"] == "Lesson"
        assert out["checklist"].endswith("daily_lesson_plan.yaml")
        assert isinstance(out["inventory"], list) and out["inventory"]
        assert isinstance(out["steps_by_doc"], dict)
        # Additive extras that curriculum-tier and LESSON-PLAN fill still read.
        assert "A5" in (out.get("steps") or {})
        assert out["steps"]["A5"].get("hunter_core_present") is not None
        assert out.get("a6_fields") is not None
        assert out.get("emit_paths")
        findings = json.loads(
            (root / "path_a" / "findings.json").read_text(encoding="utf-8")
        )
        for key in (
            "project_id",
            "workflow_id",
            "path",
            "lens",
            "status",
            "doc_ids",
            "checklist",
            "inventory",
            "steps_by_doc",
            "steps",
            "a6_fields",
            "emit_paths",
        ):
            assert key in findings, key
        assert findings["status"] == "ok"
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_lesson_plan_routes_to_a,
        test_checklist_loads_hunter_core,
        test_strong_lesson_a2_a5,
        test_run_path_a_writes_shared_findings_shape,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
