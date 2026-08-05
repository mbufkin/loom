#!/usr/bin/env python3
"""
test_path_c_general.py — Offline Path C nursery presence tests (no corpus).

Best practice: synthetic fixtures under tests/fixtures/path_c/ prove C2–C4;
temp projects prove findings.json write. Real coach/presentation seeds stay in lab.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.general import (  # noqa: E402
    c_presence_for_step,
    c2_identity,
    c3_feedback,
    load_general_checklist,
    run_path_c_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_c"


def _elements_from_text(doc_id: str, text: str, name: str = "") -> list[dict]:
    excerpt = f"{name}\n{text}" if name else text
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "general",
            "excerpt": excerpt,
        }
    ]


def test_presentation_routes_to_c() -> None:
    wf, path, fb, _ = resolve_workflow(
        doc_type="presentation",
        source_file="CTSO_Presentation.txt",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("general", "C", True)


def test_checklist_loads_c4() -> None:
    cl = load_general_checklist()
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert "C4" in steps


def test_c2_identity_requires_general_route() -> None:
    ok = c2_identity(
        {
            "workflow_id": "general",
            "path": "C",
            "doc_type": "other",
            "reason": "mapped from doc_type=other",
        },
        "x1",
    )
    assert ok["status"] == "PRESENT"
    bad = c2_identity(
        {"workflow_id": "quiz", "path": "B", "doc_type": "quiz"}, "x2"
    )
    assert bad["status"] == "MISSING"


def test_c3_route_or_yaml() -> None:
    assert (
        c3_feedback({"feedback": True}, "a1", set())["status"] == "PRESENT"
    )
    assert (
        c3_feedback({"feedback": False}, "a2", {"a2"})["status"] == "PRESENT"
    )
    assert (
        c3_feedback({"feedback": False}, "a3", set())["status"] == "MISSING"
    )


def test_strong_coach_growth_bucket() -> None:
    text = (FIXTURES / "strong_coach.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("c1", text, "Coach_Protocol.txt")
    cl = load_general_checklist()
    c4 = c_presence_for_step(elements, cl, "C4")
    assert c4["status"] == "PRESENT"


def test_weak_other_lacks_growth_bucket() -> None:
    text = (FIXTURES / "weak_other.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("c2", text, "Other_Handout_Stub.txt")
    cl = load_general_checklist()
    c4 = c_presence_for_step(elements, cl, "C4")
    assert c4["status"] == "MISSING"


def test_run_path_c_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_c_general_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_c1_Coach_Lesson_Internalization_Protocol.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_coach.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "c1",
                    "doc_type": "other",
                    "workflow_id": "general",
                    "path": "C",
                    "lens": "General feedback",
                    "feedback": True,
                    "reason": "mapped from doc_type=other",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_c_for_project(pid)
        assert out["path"] == "C"
        assert out["doc_ids"] == ["c1"]
        assert out["steps_by_doc"]["c1"]["C2"]["status"] == "PRESENT"
        assert out["steps_by_doc"]["c1"]["C3"]["status"] == "PRESENT"
        assert out["steps_by_doc"]["c1"]["C4"]["status"] == "PRESENT"
        assert out["steps_by_doc"]["c1"]["C5"]["status"] == "STUB"
        findings = json.loads(
            (root / "path_c" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("general.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_presentation_routes_to_c,
        test_checklist_loads_c4,
        test_c2_identity_requires_general_route,
        test_c3_route_or_yaml,
        test_strong_coach_growth_bucket,
        test_weak_other_lacks_growth_bucket,
        test_run_path_c_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
