#!/usr/bin/env python3
"""
test_path_h_exit_ticket.py — Offline Path H routing + stub write (no corpus).

Best practice: prove exit tickets leave Path B before building deep H1–H3 checks.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from route import resolve_workflow  # noqa: E402
from workflows.exit_ticket import run_path_h_for_project  # noqa: E402


def test_exit_ticket_routes_to_h() -> None:
    wf, path, fb, _ = resolve_workflow(
        doc_type="exit_ticket",
        source_file="Culinary_Day2_Exit_Ticket.docx",
        graph_hint=None,
    )
    assert (wf, path, fb) == ("exit_ticket", "H", False)


def test_quiz_does_not_steal_exit_name() -> None:
    """Graph Assessment hint must not pull an exit-ticket filename onto B."""
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


def test_run_path_h_writes_findings() -> None:
    """Tiny fake project: route-map with one exit ticket → path_h/findings.json."""
    from audit_lib import project_dir

    pid = "_tmp_path_h_exit_test"
    root = project_dir(pid)
    if root.exists():
        shutil.rmtree(root)
    try:
        (root / "layer0").mkdir(parents=True)
        (root / "sources").mkdir(parents=True)
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "exit1",
                    "doc_type": "exit_ticket",
                    "workflow_id": "exit_ticket",
                    "path": "H",
                    "lens": "Exit ticket",
                    "source_file": "doc_exit1_Day1_Exit_Ticket.txt",
                }
            ],
        }
        (root / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        src = root / "sources" / "doc_exit1_Day1_Exit_Ticket.txt"
        src.write_text(
            "Exit ticket\nObjective: knife safety\nWhat is one safe cutting tip?\n",
            encoding="utf-8",
        )
        out = run_path_h_for_project(pid)
        assert out["path"] == "H"
        assert out["doc_ids"] == ["exit1"]
        findings = json.loads(
            (root / "path_h" / "findings.json").read_text(encoding="utf-8")
        )
        assert findings["inventory"][0]["H1"]["status"] == "PRESENT"
    finally:
        if root.exists():
            shutil.rmtree(root)


def main() -> int:
    for t in (
        test_exit_ticket_routes_to_h,
        test_quiz_does_not_steal_exit_name,
        test_run_path_h_writes_findings,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
