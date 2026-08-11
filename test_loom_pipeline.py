#!/usr/bin/env python3
"""
test_loom_pipeline.py — Loom data-flow smoke (plan success metrics).

Always-on: handoff schemas + tier math (no private corpora).
Dallas integration tests run only when local sources or a non-empty ledger exist.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import project_dir
from reports import compute_curriculum_tier
from route import load_route_map, routed_doc_ids

PROJECT = "dallas-career-2026"


def _dallas_ready() -> bool:
    """True when this checkout can exercise router/path workflows on Dallas."""
    root = project_dir(PROJECT)
    sources = root / "sources"
    if sources.is_dir() and any(sources.glob("doc_*.txt")):
        return True
    ledger = root / "layer0" / "ledger.json"
    if not ledger.is_file():
        return False
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, list) and len(data) > 0


def _run(script: str, *extra: str) -> None:
    cmd = [sys.executable, str(BASE / script), "--project", PROJECT, *extra]
    rc = subprocess.call(cmd)
    assert rc == 0, f"command failed ({rc}): {' '.join(cmd)}"


def test_handoff_schemas_exist() -> None:
    handoffs = BASE / "workflows" / "handoffs"
    for name in (
        "layer0_to_router.json",
        "router_to_workflow.json",
        "workflow_to_place.json",
    ):
        assert (handoffs / name).is_file(), name
        json.loads((handoffs / name).read_text(encoding="utf-8"))


def _enum(schema: dict, prop: str) -> set[str]:
    return set(((schema.get("properties") or {}).get(prop) or {}).get("enum") or [])


def test_handoff_schema_enums_cover_every_path() -> None:
    """The schemas drifted to a six-path world once and nothing caught it.

    Asserting against the checklist YAMLs rather than a literal list means adding
    Path I updates this test by adding the lens, not by remembering to edit it.
    """
    checklists = sorted((BASE / "workflows" / "checklists").glob("*.yaml"))
    live_paths, live_workflows = set(), set()
    for path in checklists:
        text = path.read_text(encoding="utf-8")
        for line, bucket in (("path:", live_paths), ("workflow_id:", live_workflows)):
            for row in text.splitlines():
                if row.startswith(line):
                    bucket.add(row.split(":", 1)[1].strip())

    handoffs = BASE / "workflows" / "handoffs"
    for name in ("router_to_workflow.json", "workflow_to_place.json"):
        schema = json.loads((handoffs / name).read_text(encoding="utf-8"))
        assert live_paths <= _enum(schema, "path"), (
            f"{name} path enum is missing {sorted(live_paths - _enum(schema, 'path'))}"
        )
        missing = live_workflows - _enum(schema, "workflow_id")
        assert not missing, f"{name} workflow_id enum is missing {sorted(missing)}"


def test_emitted_handoff_matches_its_schema() -> None:
    """Validate a real emitted handoff, not just that the schema parses.

    Skipped rather than failed when Dallas has not been run in this checkout —
    the always-on tests must stay corpus-free.
    """
    emitted = project_dir(PROJECT) / "layer0" / "workflow-handoff.json"
    if not emitted.is_file():
        return
    schema = json.loads(
        (BASE / "workflows" / "handoffs" / "workflow_to_place.json").read_text(
            encoding="utf-8"
        )
    )
    rows = json.loads(emitted.read_text(encoding="utf-8")).get("workflows") or []
    assert rows, "workflow-handoff.json has no workflows"
    for row in rows:
        for prop in ("workflow_id", "path", "status"):
            allowed = _enum(schema, prop)
            value = row.get(prop)
            assert value in allowed, (
                f"path {row.get('path')}: {prop}={value!r} not in schema enum "
                f"{sorted(allowed)}"
            )


def test_tiers_math() -> None:
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


_VALID_WORKFLOWS = {
    "lesson_plan",
    "quiz",
    "general",
    "teacher_support",
    "student_practice",
    "standards_pacing",
    "syllabus",
    "exit_ticket",
}
_VALID_PATHS = {"A", "B", "C", "D", "E", "F", "G", "H"}


def test_route_map_covers_docs() -> None:
    """Every Dallas run should produce route-map.json with A–H lens assignments."""
    if not _dallas_ready():
        print("SKIP test_route_map_covers_docs (no local Dallas corpus/ledger)")
        return
    _run("route.py")
    root = project_dir(PROJECT)
    path = root / "layer0" / "route-map.json"
    assert path.is_file(), "missing layer0/route-map.json"
    rm = json.loads(path.read_text(encoding="utf-8"))
    routes = rm.get("routes") or []
    assert len(routes) >= 1
    counts = rm.get("counts") or {}
    # Starter lenses still expected on Dallas; D/E/F may be zero without graph/TE names.
    assert "lesson_plan" in counts and "quiz" in counts and "general" in counts
    for r in routes:
        assert r.get("doc_id")
        assert r.get("workflow_id") in _VALID_WORKFLOWS
        assert r.get("path") in _VALID_PATHS
    assert (root / "_loom_feedback.yaml").is_file() or counts.get("general", 0) == 0


def test_path_workflows_a1_a8() -> None:
    """Path A emits A1–A8; Paths B–H write findings; no invented curriculum required."""
    if not _dallas_ready():
        print("SKIP test_path_workflows_a1_a8 (no local Dallas corpus/ledger)")
        return
    _run("workflows/run_paths.py", "--no-model")
    root = project_dir(PROJECT)
    pa = json.loads((root / "path_a" / "findings.json").read_text(encoding="utf-8"))
    steps = pa.get("steps") or {}
    for step in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"):
        assert step in steps, f"Path A missing {step}"
    assert (pa.get("a6_fields") is not None) or not routed_doc_ids(
        PROJECT, workflow_id="lesson_plan"
    )
    a5 = steps["A5"]
    assert a5.get("hunter_core_total", 0) >= 1
    assert 0 <= int(a5.get("hunter_core_present") or 0) <= int(a5["hunter_core_total"])

    pb = json.loads((root / "path_b" / "findings.json").read_text(encoding="utf-8"))
    pc = json.loads((root / "path_c" / "findings.json").read_text(encoding="utf-8"))
    assert pb.get("path") == "B" or pb.get("workflow_id") == "quiz"
    assert pc.get("path") == "C" or pc.get("workflow_id") == "general"
    # D/E/F/G/H stubs always write findings (status skipped when empty).
    for letter, wf in (
        ("d", "teacher_support"),
        ("e", "student_practice"),
        ("f", "standards_pacing"),
        ("g", "syllabus"),
        ("h", "exit_ticket"),
    ):
        pf = json.loads(
            (root / f"path_{letter}" / "findings.json").read_text(encoding="utf-8")
        )
        assert pf.get("path") == letter.upper() or pf.get("workflow_id") == wf

    if routed_doc_ids(PROJECT, workflow_id="lesson_plan"):
        teachers = root / "output" / "teachers"
        lesson_mds = list(teachers.glob("*/LESSON-PLAN.md"))
        assert lesson_mds, "expected LESSON-PLAN.md under output/teachers/"


def test_calendars_post_assemble_inferred() -> None:
    """Authoritative calendars are post-assemble inference, not early rollup."""
    if not _dallas_ready():
        # Public tree may still ship a structural calendars_inferred sample.
        root = project_dir(PROJECT)
        cal_path = root / "calendars_inferred" / "INFERRED-CALENDARS.json"
        if cal_path.is_file():
            cal = json.loads(cal_path.read_text(encoding="utf-8"))
            assert cal.get("source") == "inferred_from_documents"
            print("OK test_calendars_post_assemble_inferred (shipped sample only)")
            return
        print("SKIP test_calendars_post_assemble_inferred (no local Dallas corpus)")
        return
    _run("calendars.py")
    root = project_dir(PROJECT)
    cal_path = root / "calendars_inferred" / "INFERRED-CALENDARS.json"
    assert cal_path.is_file()
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    assert cal.get("source") == "inferred_from_documents"
    assert cal.get("generated_at")
    assert isinstance(cal.get("units"), (list, dict)) and cal.get("units")


def test_route_gate_helpers() -> None:
    """Nothing analyzed into a unit without a route — helper coverage."""
    if not _dallas_ready():
        print("SKIP test_route_gate_helpers (no local Dallas corpus/ledger)")
        return
    rm = load_route_map(PROJECT)
    allowed = routed_doc_ids(PROJECT)
    assert allowed
    routes = rm.get("routes") or []
    from_map = {r["doc_id"] for r in routes if r.get("doc_id")}
    assert allowed == from_map


if __name__ == "__main__":
    tests = [
        test_handoff_schemas_exist,
        test_handoff_schema_enums_cover_every_path,
        test_emitted_handoff_matches_its_schema,
        test_tiers_math,
        test_route_map_covers_docs,
        test_path_workflows_a1_a8,
        test_calendars_post_assemble_inferred,
        test_route_gate_helpers,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print("ALL LOOM PIPELINE TESTS PASSED")
