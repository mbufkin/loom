#!/usr/bin/env python3
"""
test_loom_pipeline.py — Loom data-flow smoke (plan success metrics).

Runs against projects/dallas-career-2026 artifacts. Re-exercises router + Path
workflows + calendars without a full Layer 0 model pass. Asserts auditor-only
contracts: route-map coverage, Path A A1–A8, inferred calendars, honest tiers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import load_yaml, project_dir
from reports import compute_curriculum_tier
from route import load_route_map, routed_doc_ids

PROJECT = "dallas-career-2026"


def _run(script: str, *extra: str) -> None:
    cmd = [sys.executable, str(BASE / script), "--project", PROJECT, *extra]
    rc = subprocess.call(cmd)
    assert rc == 0, f"command failed ({rc}): {' '.join(cmd)}"


def test_route_map_covers_docs():
    """Every Dallas run should produce route-map.json with A/B/C counts."""
    _run("route.py")
    root = project_dir(PROJECT)
    path = root / "layer0" / "route-map.json"
    assert path.is_file(), "missing layer0/route-map.json"
    rm = json.loads(path.read_text(encoding="utf-8"))
    routes = rm.get("routes") or []
    assert len(routes) >= 1
    counts = rm.get("counts") or {}
    assert "lesson_plan" in counts and "quiz" in counts and "general" in counts
    # Soft coverage: every routed entry has workflow_id + path
    for r in routes:
        assert r.get("doc_id")
        assert r.get("workflow_id") in {"lesson_plan", "quiz", "general"}
        assert r.get("path") in {"A", "B", "C"}
    # Feedback file exists when general/weak types were seen
    assert (root / "_loom_feedback.yaml").is_file() or counts.get("general", 0) == 0


def test_path_workflows_a1_a8():
    """Path A emits A1–A8; B/C stubs write findings; no invented curriculum required."""
    _run("workflows/run_paths.py", "--no-model")
    root = project_dir(PROJECT)
    pa = json.loads((root / "path_a" / "findings.json").read_text(encoding="utf-8"))
    steps = pa.get("steps") or {}
    for step in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"):
        assert step in steps, f"Path A missing {step}"
    assert (pa.get("a6_fields") is not None) or not routed_doc_ids(
        PROJECT, workflow_id="lesson_plan"
    )
    # Blanks allowed: PRESENT/MISSING only — never require all Hunter filled
    a5 = steps["A5"]
    assert a5.get("hunter_core_total", 0) >= 1
    assert 0 <= int(a5.get("hunter_core_present") or 0) <= int(a5["hunter_core_total"])

    pb = json.loads((root / "path_b" / "findings.json").read_text(encoding="utf-8"))
    pc = json.loads((root / "path_c" / "findings.json").read_text(encoding="utf-8"))
    assert pb.get("path") == "B" or pb.get("workflow_id") == "quiz"
    assert pc.get("path") == "C" or pc.get("workflow_id") == "general"

    # At least one LESSON-PLAN plate when lesson_plan docs exist
    if routed_doc_ids(PROJECT, workflow_id="lesson_plan"):
        teachers = root / "output" / "teachers"
        lesson_mds = list(teachers.glob("*/LESSON-PLAN.md"))
        assert lesson_mds, "expected LESSON-PLAN.md under output/teachers/"


def test_calendars_post_assemble_inferred():
    """Authoritative calendars are post-assemble inference, not early rollup."""
    _run("calendars.py")
    root = project_dir(PROJECT)
    cal_path = root / "calendars_inferred" / "INFERRED-CALENDARS.json"
    assert cal_path.is_file()
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    assert cal.get("source") == "inferred_from_documents"
    assert cal.get("generated_at")
    assert isinstance(cal.get("units"), (list, dict)) and cal.get("units")


def test_tiers_can_be_strong():
    """Honest Strong when Hunter is solid — calendar GAPS must not block it."""
    strong = compute_curriculum_tier(
        missing=10,
        fulfilled=10,
        hunter_present=8,
        path_a_coherent=True,
    )
    assert strong["tier"] == "Strong"
    weak = compute_curriculum_tier(
        missing=20,
        fulfilled=5,
        hunter_present=2,
    )
    assert weak["tier"] == "Weak"
    # Dallas artifacts should already include at least one Strong when Path A ran
    summary = project_dir(PROJECT) / "output" / "SUMMARY.md"
    if summary.is_file():
        text = summary.read_text(encoding="utf-8")
        assert "**Strong**" in text or "**Weak**" in text or "**Developing**" in text


def test_route_gate_helpers():
    """Nothing analyzed into a unit without a route — helper coverage."""
    rm = load_route_map(PROJECT)
    allowed = routed_doc_ids(PROJECT)
    assert allowed
    routes = rm.get("routes") or []
    from_map = {r["doc_id"] for r in routes if r.get("doc_id")}
    assert allowed == from_map


def test_handoff_schemas_exist():
    handoffs = BASE / "workflows" / "handoffs"
    for name in (
        "layer0_to_router.json",
        "router_to_workflow.json",
        "workflow_to_place.json",
    ):
        assert (handoffs / name).is_file(), name
        json.loads((handoffs / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    tests = [
        test_handoff_schemas_exist,
        test_route_map_covers_docs,
        test_path_workflows_a1_a8,
        test_calendars_post_assemble_inferred,
        test_tiers_can_be_strong,
        test_route_gate_helpers,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print("ALL LOOM PIPELINE TESTS PASSED")
