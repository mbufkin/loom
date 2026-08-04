#!/usr/bin/env python3
"""
test_path_g_syllabus.py — Offline Path G presence tests (no corpus required).

Best practice: feed tiny fake Layer 0 excerpts into G2–G7 scanners so CI
can trust syllabus presence without Dallas/Bluebonnet trees.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from workflows.syllabus import (  # noqa: E402
    _doc_has_cte_signals,
    g1_inventory,
    g_presence_for_step,
    load_syllabus_checklist,
    run_path_g_for_project,
)


def _el(doc_id: str, eid: str, excerpt: str, etype: str = "logistics_materials") -> dict:
    return {
        "doc_id": doc_id,
        "element_id": eid,
        "element_type": etype,
        "excerpt": excerpt,
    }


STRONG_CTE = [
    _el(
        "syl1",
        "e1",
        "Course: Career Preparation I (PEIMS 12701300). One credit. Grades 11–12.",
    ),
    _el(
        "syl1",
        "e2",
        "Instructor: Ms. Rivera — rivera@dallasisd.org — Room 214 — conference period 3.",
    ),
    _el("syl1", "e3", "Class meets Period 2, Monday–Friday."),
    _el(
        "syl1",
        "e4",
        "Prerequisite: Principles of Human Services recommended.",
        "standards_objectives",
    ),
    _el(
        "syl1",
        "e5",
        "Course description: In this course students will explore careers and prepare for workplace success.",
        "standards_objectives",
    ),
    _el(
        "syl1",
        "e6",
        "Learning outcomes: Students will be able to write a resume and interview for employment.",
        "standards_objectives",
    ),
    _el(
        "syl1",
        "e7",
        "TEKS and employability skills from Chapter 127 are addressed throughout the year.",
        "standards_objectives",
    ),
    _el(
        "syl1",
        "e8",
        "Grading: Internship 50%, Daily work/quizzes 25%, Exams 20%, Participation 5%.",
        "assessment_checkpoint",
    ),
    _el("syl1", "e9", "Grading scale: 90-100 A; 80-89 B; 70-79 C; below 70 F."),
    _el(
        "syl1",
        "e10",
        "Late work: for excused absences students may make up work; unexcused max 70%.",
    ),
    _el(
        "syl1",
        "e11",
        "Unit 1 Identifying Careers; Unit 2 Resumes; Unit 3 Employer Expectations (YAG).",
    ),
    _el("syl1", "e12", "Midterm week of October 12; final exam deadline in May."),
    _el(
        "syl1",
        "e13",
        "Attendance is required; internship hours count toward the course grade.",
    ),
    _el(
        "syl1",
        "e14",
        "Academic integrity: plagiarism and cheating are prohibited. AI policy: disclose tool use.",
    ),
    _el(
        "syl1",
        "e15",
        "Contact via email or Schoology; I respond within 24 school hours.",
    ),
    _el(
        "syl1",
        "e16",
        "Accommodations: IEP/504 supports honored; tutoring available after school.",
    ),
    _el(
        "syl1",
        "e17",
        "Safety: follow all shop safety and PPE rules at internship sites.",
    ),
    _el(
        "syl1",
        "e18",
        "Internship / work-based learning: 10 hours per week with an industry partner.",
    ),
    _el(
        "syl1",
        "e19",
        "Parent/guardian and student signature: I have read and acknowledge this syllabus.",
    ),
]


def test_checklist_loads_g2_g7() -> None:
    cl = load_syllabus_checklist()
    assert cl.get("role") == "syllabus"
    steps = {s.get("step") for s in (cl.get("sections") or {}).values()}
    assert steps == {"G2", "G3", "G4", "G5", "G6", "G7"}


def test_strong_cte_syllabus_presence() -> None:
    cl = load_syllabus_checklist()
    assert _doc_has_cte_signals(STRONG_CTE)
    g1 = g1_inventory(STRONG_CTE, "syl1")
    assert g1["status"] == "PRESENT"
    assert g1["element_count"] == len(STRONG_CTE)
    for step in ("G2", "G3", "G4", "G5", "G6", "G7"):
        result = g_presence_for_step(
            STRONG_CTE, cl, step, cte_signaled=True
        )
        assert result["status"] == "PRESENT", (step, result)
        assert all(f["status"] == "PRESENT" for f in result["fields"]), (step, result)


def test_empty_doc_missing_required_fields() -> None:
    cl = load_syllabus_checklist()
    empty: list[dict] = []
    g2 = g_presence_for_step(empty, cl, "G2", cte_signaled=False)
    assert g2["status"] == "MISSING"
    assert g2["present"] == 0
    g7 = g_presence_for_step(empty, cl, "G7", cte_signaled=False)
    # accommodations required → MISSING; optional CTE → NOT_SIGNALED
    statuses = {f["id"]: f["status"] for f in g7["fields"]}
    assert statuses["accommodations"] == "MISSING"
    assert statuses["safety"] == "NOT_SIGNALED"
    assert statuses["wbl_internship"] == "NOT_SIGNALED"
    assert statuses["acknowledgment"] == "NOT_SIGNALED"


def test_cte_signaled_makes_optional_fields_required() -> None:
    cl = load_syllabus_checklist()
    thin = [
        _el("syl2", "x1", "This CTE course includes an internship with industry partners.")
    ]
    g7 = g_presence_for_step(thin, cl, "G7", cte_signaled=True)
    statuses = {f["id"]: f["status"] for f in g7["fields"]}
    # internship keyword hits wbl; safety/ack still MISSING when CTE signaled
    assert statuses["wbl_internship"] == "PRESENT"
    assert statuses["safety"] == "MISSING"
    assert statuses["acknowledgment"] == "MISSING"


def test_run_path_g_writes_findings() -> None:
    """Integration-ish: fake project tree → path_g/findings.json."""
    import shutil

    # Build under projects/ via real project_dir convention.
    root_projects = BASE / "projects"
    pid = "_tmp_path_g_syllabus_test"
    proj = root_projects / pid
    try:
        (proj / "layer0").mkdir(parents=True, exist_ok=True)
        (proj / "sources").mkdir(parents=True, exist_ok=True)
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": "syl1",
                    "doc_type": "syllabus",
                    "workflow_id": "syllabus",
                    "path": "G",
                    "lens": "Syllabus",
                }
            ],
        }
        (proj / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (proj / "layer0" / "ledger.json").write_text(
            json.dumps(STRONG_CTE), encoding="utf-8"
        )
        out = run_path_g_for_project(pid)
        assert out["status"] == "ok"
        assert out["doc_ids"] == ["syl1"]
        findings = json.loads(
            (proj / "path_g" / "findings.json").read_text(encoding="utf-8")
        )
        steps = findings["steps_by_doc"]["syl1"]
        assert steps["G1"]["status"] == "PRESENT"
        assert steps["G4"]["status"] == "PRESENT"
        assert steps["G8"]["status"] == "STUB"
        assert findings["inventory"][0]["G3"]["status"] == "PRESENT"
    finally:
        if proj.is_dir():
            shutil.rmtree(proj)


def main() -> int:
    tests = [
        test_checklist_loads_g2_g7,
        test_strong_cte_syllabus_presence,
        test_empty_doc_missing_required_fields,
        test_cte_signaled_makes_optional_fields_required,
        test_run_path_g_writes_findings,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
