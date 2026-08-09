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


# A syllabus made only of the phrases that used to produce false hits. Every
# line is shaped after the real Waxahachie culinary syllabi; none of it states
# the section the old matcher claimed it did. Kept as text, not .docx, because
# the source corpus is deliberately not committed - what CI needs is the trap,
# not the curriculum.
DECOY_ONLY = """Culinary Arts Department

Required Materials:
Fingernail Clippers
Clear dividers (recipe cover to protect from food)
Hair ties

Behavior and Consequences
Students are expected to follow all school rules.

Extra credit
There will be a couple of opportunities throughout the year for extra credit.

Locker Areas
All items put in a locker must leave at the end of the class period.
"""

# The same document with the sections a syllabus is supposed to have.
REAL_SECTIONS = (
    DECOY_ONLY
    + """
Instructor: Chef Hamilton
Course: Culinary Arts I
Email: chef@example.org
Appointment Times: (B DAY) 2:21-3:55

1st 6 Weeks
ServSafe Certification training

Grading
Lab Presentations 60% of the grade.
All computer assignments are due by their perspective due dates.
"""
)


def _run_g_on_text(pid: str, text: str) -> dict:
    """Write a one-document project whose source is text, then run Path G."""
    import shutil

    proj = BASE / "projects" / pid
    try:
        (proj / "layer0").mkdir(parents=True, exist_ok=True)
        (proj / "sources").mkdir(parents=True, exist_ok=True)
        doc_id = "Syllabus.txt"
        (proj / "sources" / doc_id).write_text(text, encoding="utf-8")
        route = {
            "project_id": pid,
            "routes": [
                {
                    "doc_id": doc_id,
                    "doc_type": "syllabus",
                    "workflow_id": "syllabus",
                    "path": "G",
                    "lens": "Syllabus",
                    "source_file": doc_id,
                }
            ],
        }
        (proj / "layer0" / "route-map.json").write_text(
            json.dumps(route), encoding="utf-8"
        )
        (proj / "layer0" / "ledger.json").write_text("[]", encoding="utf-8")
        out = run_path_g_for_project(pid)
        return out["steps_by_doc"][doc_id]
    finally:
        if proj.is_dir():
            shutil.rmtree(proj)


def _statuses(step: dict) -> dict[str, str]:
    return {f["id"]: f["status"] for f in step.get("fields") or []}


def test_decoy_phrases_do_not_report_sections() -> None:
    """The regression that matters: absent sections must read absent.

    Under substring matching this document scored lab safety (Clippers),
    a course credit statement (extra credit), a TEKS coverage claim (recipe
    cover) and a meeting pattern (locker rules) - four sections it does not
    contain. A false PRESENT is a gap the auditor never reports.
    """
    steps = _run_g_on_text("_tmp_path_g_decoys", DECOY_ONLY)
    assert _statuses(steps["G2"])["course_identity"] == "MISSING"
    assert _statuses(steps["G2"])["meeting_pattern"] == "MISSING"
    assert _statuses(steps["G5"])["teks_timeline"] == "MISSING"
    assert _statuses(steps["G7"])["safety"] in {"MISSING", "NOT_SIGNALED"}


def test_real_sections_are_found_with_checkable_cites() -> None:
    """The other half: present sections must read present, and the citation
    must quote the text that caused the hit."""
    steps = _run_g_on_text("_tmp_path_g_real", REAL_SECTIONS)
    g2 = _statuses(steps["G2"])
    assert g2["course_identity"] == "PRESENT"
    assert g2["instructor_contact"] == "PRESENT"
    assert g2["meeting_pattern"] == "PRESENT"
    # The six-weeks course map is how Texas syllabi lay out the year; it was
    # read as absent until "six weeks" became a unit_topics keyword.
    assert _statuses(steps["G5"])["unit_topics"] == "PRESENT"
    assert _statuses(steps["G5"])["due_dates"] == "PRESENT"
    assert _statuses(steps["G7"])["safety"] == "PRESENT"
    # ...and still no TEKS timeline, even with real sections present.
    assert _statuses(steps["G5"])["teks_timeline"] == "MISSING"

    safety_cite = [
        f["cites"][0] for f in steps["G7"]["fields"] if f["id"] == "safety"
    ][0]
    assert "ServSafe" in safety_cite, safety_cite
    assert "Clippers" not in safety_cite


def test_source_text_beats_a_thin_ledger() -> None:
    """Layer 0 samples a syllabus rather than covering it. When the header is
    missing from the ledger, reading the document is what keeps instructor,
    email and room from reading MISSING on a document that states all three."""
    steps = _run_g_on_text("_tmp_path_g_evidence", REAL_SECTIONS)
    assert _statuses(steps["G2"])["instructor_contact"] == "PRESENT"


def main() -> int:
    tests = [
        test_checklist_loads_g2_g7,
        test_strong_cte_syllabus_presence,
        test_empty_doc_missing_required_fields,
        test_cte_signaled_makes_optional_fields_required,
        test_run_path_g_writes_findings,
        test_decoy_phrases_do_not_report_sections,
        test_real_sections_are_found_with_checkable_cites,
        test_source_text_beats_a_thin_ledger,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
