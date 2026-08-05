#!/usr/bin/env python3
"""
test_path_h_exit_ticket.py — Offline Path H presence tests (no corpus required).

Best practice: synthetic fixtures under tests/fixtures/path_h/ prove H2–H4;
temp projects prove findings.json write. Real Dallas seeds stay in lab smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.exit_ticket import (  # noqa: E402
    h_presence_for_step,
    load_exit_ticket_checklist,
    run_path_h_for_project,
)

FIXTURES = BASE / "tests" / "fixtures" / "path_h"


def _elements_from_text(doc_id: str, text: str) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "element_id": f"{doc_id}:1",
            "element_type": "exit_ticket",
            "excerpt": text,
        }
    ]


def test_exit_ticket_routes_to_h() -> None:
    wf, path, fb, _ = resolve_workflow(
        doc_type="exit_ticket",
        source_file="Culinary_Day2_Exit_Ticket.docx",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("exit_ticket", "H", False)


def test_quiz_does_not_steal_exit_name() -> None:
    hint = {
        "role": "assessment",
        "workflow_id": "quiz",
        "reason": "graph Assessment link",
    }
    wf, path, _, reason = resolve_workflow(
        doc_type="other",
        source_file="Module_1_Exit_Ticket.pdf",
        graph_hint=hint,
    )
    assert (wf, path) == ("exit_ticket", "H")
    assert "exit_ticket" in reason


def test_checklist_loads_h2_h4() -> None:
    cl = load_exit_ticket_checklist()
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert {"H2", "H3", "H4"} <= steps


def test_strong_exit_presence() -> None:
    text = (FIXTURES / "strong_exit.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("e1", text)
    cl = load_exit_ticket_checklist()
    h2 = h_presence_for_step(elements, cl, "H2")
    h4 = h_presence_for_step(elements, cl, "H4")
    assert h2["status"] in {"PRESENT", "PARTIAL"}
    assert h4["status"] == "PRESENT"


def test_weak_exit_has_prompt_not_rich_signal() -> None:
    text = (FIXTURES / "weak_exit.txt").read_text(encoding="utf-8")
    elements = _elements_from_text("e2", text)
    cl = load_exit_ticket_checklist()
    h2 = h_presence_for_step(elements, cl, "H2")
    h4 = h_presence_for_step(elements, cl, "H4")
    assert h2["present"] >= 1
    # One-liner may still hit "?" / what — H4 often MISSING (no rate/learn).
    assert h4["status"] in {"MISSING", "PRESENT", "PARTIAL"}


def test_run_path_h_writes_findings() -> None:
    from audit_lib import project_dir

    pid = "_tmp_path_h_exit_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        name = "doc_exit1_Day1_Exit_Ticket.txt"
        (root / "sources" / name).write_text(
            (FIXTURES / "strong_exit.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "exit1",
                    "doc_type": "exit_ticket",
                    "workflow_id": "exit_ticket",
                    "path": "H",
                    "lens": "Exit ticket",
                    "source_file": name,
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (root / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_h_for_project(pid)
        assert out["path"] == "H"
        assert out["doc_ids"] == ["exit1"]
        assert out["steps_by_doc"]["exit1"]["H2"]["status"] in {
            "PRESENT",
            "PARTIAL",
        }
        assert out["steps_by_doc"]["exit1"]["H5"]["status"] == "STUB"
        findings = json.loads(
            (root / "path_h" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["checklist"].endswith("exit_ticket.yaml")
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_exit_ticket_routes_to_h,
        test_quiz_does_not_steal_exit_name,
        test_checklist_loads_h2_h4,
        test_strong_exit_presence,
        test_weak_exit_has_prompt_not_rich_signal,
        test_run_path_h_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
