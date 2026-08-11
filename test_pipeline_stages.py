#!/usr/bin/env python3
"""
test_pipeline_stages.py — Import-smoke the stages run_project.py shells out to,
and pin the stage-output contract that closes the quiet "wrote nothing" failure.

Best practice: catch packaging / history-rewrite damage at import time. The
best-effort band in run_project used to swallow ModuleNotFoundError as a WARN
and still report SUCCESS; this test fails the moment a required stage cannot
import, without needing a live model or a full corpus run.

The output assertions below cover the other half of check 10: a stage that
returns zero must leave its declared artifact, while a legitimately skipped
stage (undeclared, or findings written with status: skipped) must not fail.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# Explicit list of modules run_project.py invokes (or imports from) as pipeline
# stages. Kept as a constant — clearer and more reviewable than parsing the
# orchestrator, and the drift check below covers synthesize ↔ unit_rung.
PIPELINE_STAGE_MODULES: tuple[str, ...] = (
    "route",
    "rollup",
    "layer0",
    "layer1",
    "layer2",
    "lesson_rung",
    "artifact_rung",
    "unit_rung",
    "lesson_quality",
    "curriculum_review",
    "calendars",
    "synthesize",
    "workflows.run_paths",
)

# Stages intentionally excluded from the import smoke (empty once every
# run_project stage imports cleanly). Entries must still fail to import —
# test_known_broken_stages_still_broken asserts that, so a silent fix cannot
# leave a stale skip behind.
KNOWN_BROKEN: dict[str, str] = {}


def _import_names_from(module_path: Path, source_module: str) -> list[str]:
    """Names pulled via `from <source_module> import (...)` in module_path."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == source_module:
            for alias in node.names:
                if alias.name != "*":
                    names.append(alias.name)
    return names


def test_pipeline_stage_modules_import() -> None:
    for name in PIPELINE_STAGE_MODULES:
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001 — surface any import failure clearly
            raise AssertionError(
                f"pipeline stage {name!r} failed to import: "
                f"{type(e).__name__}: {e}"
            ) from e


def test_unit_rung_synthesize_imports_exist() -> None:
    """The regression that bit us: unit_rung imported a symbol synthesize lost."""
    import synthesize  # noqa: F401 — already proven importable above

    names = _import_names_from(BASE / "unit_rung.py", "synthesize")
    assert names, "unit_rung.py has no `from synthesize import ...` to check"
    missing = [n for n in names if not hasattr(synthesize, n)]
    assert not missing, (
        f"unit_rung imports from synthesize but symbol(s) missing: {missing}"
    )


def test_known_broken_stages_still_broken() -> None:
    for name, reason in KNOWN_BROKEN.items():
        try:
            importlib.import_module(name)
        except Exception:
            print(f"SKIP {name} (known broken): {reason}")
            continue
        raise AssertionError(
            f"{name!r} is listed in KNOWN_BROKEN but imports cleanly — "
            f"remove it from KNOWN_BROKEN ({reason})"
        )


def _with_temp_project(rel_files: dict[str, str] | None = None) -> tuple[str, Path]:
    """Create an isolated curriculum id under a temp LOOM projects root.

    Uses LOOM_E2E_RUN + a swapped audit_lib.BASE_DIR so assertions resolve
    through the same project_dir helper production uses, without touching
    real corpora.
    """
    import audit_lib

    tmp = Path(tempfile.mkdtemp(prefix="loom-stage-out-"))
    project_id = "stage-out-fixture"
    run_id = "test-run"
    # Mirror projects/<id>/e2e/runs/<run>/ so project_dir honors LOOM_E2E_RUN.
    root = tmp / "projects" / project_id / "e2e" / "runs" / run_id
    root.mkdir(parents=True)
    for rel, body in (rel_files or {}).items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")

    audit_lib.BASE_DIR = tmp
    os.environ["LOOM_E2E_RUN"] = run_id
    return project_id, root


def _restore_project_dir(saved_audit_base: Path, saved_e2e: str | None) -> None:
    import audit_lib

    audit_lib.BASE_DIR = saved_audit_base
    if saved_e2e is None:
        os.environ.pop("LOOM_E2E_RUN", None)
    else:
        os.environ["LOOM_E2E_RUN"] = saved_e2e


def test_assert_stage_outputs_passes_when_artifact_present() -> None:
    from run_project import LESSON_RUNG, assert_stage_outputs
    import audit_lib

    saved_audit_base = audit_lib.BASE_DIR
    saved_e2e = os.environ.get("LOOM_E2E_RUN")
    try:
        project_id, _ = _with_temp_project(
            {"layer_lesson/LESSON-RUNG.json": json.dumps({"ok": True})}
        )
        assert_stage_outputs(LESSON_RUNG, project_id)  # must not raise
    finally:
        _restore_project_dir(saved_audit_base, saved_e2e)


def test_assert_stage_outputs_fails_naming_artifact() -> None:
    from run_project import LESSON_RUNG, StageOutputError, assert_stage_outputs
    import audit_lib

    saved_audit_base = audit_lib.BASE_DIR
    saved_e2e = os.environ.get("LOOM_E2E_RUN")
    try:
        project_id, root = _with_temp_project()
        try:
            assert_stage_outputs(LESSON_RUNG, project_id)
        except StageOutputError as e:
            msg = str(e)
            assert "lesson_rung.py" in msg, msg
            assert "layer_lesson/LESSON-RUNG.json" in msg, msg
            assert str(root / "layer_lesson" / "LESSON-RUNG.json") in msg, msg
        else:
            raise AssertionError("expected StageOutputError when artifact is absent")
    finally:
        _restore_project_dir(saved_audit_base, saved_e2e)


def test_assert_stage_outputs_allows_conditional_skip() -> None:
    """Two skip shapes must not fail the run.

    1. Undeclared stage (e.g. opt-in graph) — assert is a no-op even on an empty
       tree, matching main() never checking stages absent from the map.
    2. Path lens with status: skipped — findings.json is still written; presence
       alone is the contract, so an empty-corpus Path G does not red the run.
    """
    from run_project import (
        GRAPH_PHASE,
        PATH_WORKFLOWS,
        assert_stage_outputs,
    )
    import audit_lib

    saved_audit_base = audit_lib.BASE_DIR
    saved_e2e = os.environ.get("LOOM_E2E_RUN")
    try:
        # Undeclared stage on an empty project root — must be silent.
        project_id, _ = _with_temp_project()
        assert_stage_outputs(GRAPH_PHASE, project_id)

        # Path G skipped still emits findings.json (and the other seven paths).
        skipped = json.dumps({"status": "skipped", "doc_ids": [], "lens": "Syllabus"})
        files = {f"path_{letter}/findings.json": skipped for letter in "abcdefgh"}
        project_id, _ = _with_temp_project(files)
        assert_stage_outputs(PATH_WORKFLOWS, project_id)
    finally:
        _restore_project_dir(saved_audit_base, saved_e2e)


def test_curriculum_review_writes_under_e2e_run() -> None:
    """Regression: curriculum_review must not leak plates onto the live root.

    With LOOM_E2E_RUN set, generate() writes LESSON-CURRICULUM-REVIEW.json under
    e2e/runs/<id>/output/ (via project_dir), never projects/<id>/output/.
    """
    import audit_lib
    import curriculum_review

    saved_audit_base = audit_lib.BASE_DIR
    saved_e2e = os.environ.get("LOOM_E2E_RUN")
    try:
        project_id, root = _with_temp_project(
            {"layer0/ledger.json": json.dumps([])}
        )
        # Empty lesson list — still writes the plate; no model calls needed.
        saved_enum = curriculum_review.enumerate_lessons
        curriculum_review.enumerate_lessons = lambda _pid: []  # type: ignore[assignment]
        try:
            written = curriculum_review.generate(project_id)
        finally:
            curriculum_review.enumerate_lessons = saved_enum  # type: ignore[assignment]

        expected = root / "output" / "LESSON-CURRICULUM-REVIEW.json"
        assert written == expected, f"wrote {written}, expected {expected}"
        assert expected.is_file(), f"missing e2e plate at {expected}"
        live_leak = (
            audit_lib.BASE_DIR
            / "projects"
            / project_id
            / "output"
            / "LESSON-CURRICULUM-REVIEW.json"
        )
        assert not live_leak.is_file(), f"leaked plate onto live root: {live_leak}"
    finally:
        _restore_project_dir(saved_audit_base, saved_e2e)


def main() -> int:
    for t in (
        test_pipeline_stage_modules_import,
        test_unit_rung_synthesize_imports_exist,
        test_known_broken_stages_still_broken,
        test_assert_stage_outputs_passes_when_artifact_present,
        test_assert_stage_outputs_fails_naming_artifact,
        test_assert_stage_outputs_allows_conditional_skip,
        test_curriculum_review_writes_under_e2e_run,
    ):
        t()
        print(f"OK {t.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
