#!/usr/bin/env python3
"""
run_project.py — The one E2E program: curriculum + model → common review folder.

Program (this repo) + data (projects/<curriculum>/). Preferred CLI: ./run-audit.

Canonical output (default):
  projects/<curriculum>/e2e/runs/<model>/
    layer0/… layer1/… output/… graph/runs/<model>/…
Review UI picks curriculum, then E2E · <model>. See docs/E2E.md.

  preflight → ingest (if needed) → rollup (provisional; calendars authoritative after assemble)
           → layer0 (0-A decompose → 0-B resolve-wide-spans)
           → graph_phase.py (opt-in --with-graph: HAS-PART belonging)
           → route.py (Loom Path A–H map — BEFORE unit placement)
           → path workflows (A lesson / B assessment / C general / D teacher
             support / E student practice / F standards & pacing / G syllabus /
             H exit ticket)
           → layer1 → layer2 → calendars.py (model day/year after assemble)
           → synthesize --report all --delivery model (+ first-pass PDF)
           → push reports to Google Drive (default; --skip-drive-push to opt out)

Usage:
  ./run-audit my-district --with-graph --graph-run nemotron3-nano-30b
  python3 run_project.py --project my-district --with-graph
  python3 run_project.py --project my-district --allow-live-root   # golden tree only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from audit_lib import BASE_DIR, load_config, log, project_dir, validate_slug_id
from tools.e2e_run_lib import ensure_e2e_env, slugify_run_id
from usage_lib import set_usage_project, write_usage_summary

INGEST = BASE_DIR / "ingest.py"
ROLLUP = BASE_DIR / "rollup.py"
LAYER0 = BASE_DIR / "layer0.py"
GRAPH_PHASE = BASE_DIR / "graph_phase.py"
ROUTE = BASE_DIR / "route.py"
PATH_WORKFLOWS = BASE_DIR / "workflows" / "run_paths.py"
LAYER1 = BASE_DIR / "layer1.py"
LAYER2 = BASE_DIR / "layer2.py"
LESSON_RUNG = BASE_DIR / "lesson_rung.py"
ARTIFACT_RUNG = BASE_DIR / "artifact_rung.py"
UNIT_RUNG = BASE_DIR / "unit_rung.py"
LESSON_QUALITY = BASE_DIR / "lesson_quality.py"
CURRICULUM_REVIEW = BASE_DIR / "curriculum_review.py"
CALENDARS = BASE_DIR / "calendars.py"
SYNTH = BASE_DIR / "synthesize.py"
PUSH_DRIVE = BASE_DIR / "tools" / "push_drive_reports.py"

# Markers that mean the child failed before it could do real work — always a bug
# in the stage module (or its imports), never a soft "model offline" skip.
_STAGE_BROKEN_MARKERS = ("ModuleNotFoundError", "ImportError", "SyntaxError")


class StageBrokenError(RuntimeError):
    """A pipeline stage crashed on import/syntax — fail the run, do not soft-skip.

    `run_step` shells out, so the child's ImportError becomes a non-zero exit. We
    recover the failure class from stderr so best-effort bands can still warn on
    model/runtime issues without swallowing packaging bugs again.
    """


class StageOutputError(RuntimeError):
    """A stage exited zero but left a declared artifact missing — fail the run.

    The quiet twin of StageBrokenError: the child imported and returned success,
    yet wrote nothing the orchestrator contracted for. Best-effort bands re-raise
    this class (model/runtime skips stay soft); only a genuine non-contract
    failure is warned past.
    """


# Artifacts each stage must leave under project_dir(project_id) when it runs to
# completion. Relative paths keep the contract honest next to the stage Path
# constants; resolution always goes through project_dir so LOOM_E2E_RUN trees
# are checked at the same root the child wrote. Stages absent from this map are
# intentionally unchecked (opt-in graph, Drive push). Path lenses that emit
# status: skipped still write findings.json — presence, not content, is the gate.
STAGE_EXPECTED_OUTPUTS: dict[Path, tuple[str, ...]] = {
    INGEST: ("manifest.yaml",),
    ROLLUP: ("pacing-plan.yaml",),
    LAYER0: ("layer0/ledger.json",),
    ROUTE: ("layer0/route-map.json",),
    PATH_WORKFLOWS: (
        "path_a/findings.json",
        "path_b/findings.json",
        "path_c/findings.json",
        "path_d/findings.json",
        "path_e/findings.json",
        "path_f/findings.json",
        "path_g/findings.json",
        "path_h/findings.json",
    ),
    LAYER1: ("layer1/bucket-ledger.json",),
    LAYER2: ("layer2/findings.json",),
    LESSON_RUNG: ("layer_lesson/LESSON-RUNG.json",),
    ARTIFACT_RUNG: ("layer_artifact/ARTIFACT-RUNG.json",),
    UNIT_RUNG: ("layer_unit/UNIT-RUNG.json",),
    LESSON_QUALITY: ("output/LESSON-QUALITY-FEEDBACK.json",),
    CURRICULUM_REVIEW: ("output/LESSON-CURRICULUM-REVIEW.json",),
    CALENDARS: ("calendars_inferred/INFERRED-CALENDARS.json",),
    SYNTH: ("output/GLOBAL-AUDIT.md",),
}


def assert_stage_outputs(script: Path, project_id: str) -> None:
    """Fail when a finished stage left a declared artifact absent.

    Call only after a successful run_step for that script. Stages gated by
    `if script.is_file()` never reach this when the module is missing — that is
    the legitimate skip path. Undeclared scripts are a no-op so opt-in steps do
    not need special cases in main().
    """
    expected = STAGE_EXPECTED_OUTPUTS.get(script)
    if not expected:
        return
    root = project_dir(project_id)
    missing = [rel for rel in expected if not (root / rel).is_file()]
    if not missing:
        return
    detail = "; ".join(f"{rel} (checked {root / rel})" for rel in missing)
    raise StageOutputError(
        f"stage {script.name} produced no output for: {detail}"
    )


# Plates the Review UI requires before advertising an E2E run (REVIEW-READY.json).
# Path findings may be status:skipped but the file must exist. Course report is
# GLOBAL-AUDIT.md or DASHBOARD.md. Graph is required only when --with-graph ran.
REVIEW_READY_PATH_FINDINGS = tuple(
    f"path_{letter}/findings.json" for letter in "abcdefgh"
)
REVIEW_READY_PLATES = (
    "output/LESSON-QUALITY-FEEDBACK.json",
    "output/LESSON-CURRICULUM-REVIEW.json",
)


def write_review_ready(
    project_id: str,
    *,
    run_id: str,
    model: str,
    with_graph: bool,
) -> Path | None:
    """Publish REVIEW-READY.json when the e2e tree has a complete review surface.

    Educational note: the website lists only runs with this marker. Incomplete
    or soft-skipped quality/review plates must not become visible mid-flight.
    """
    root = project_dir(project_id)
    missing: list[str] = []
    for rel in REVIEW_READY_PATH_FINDINGS + REVIEW_READY_PLATES:
        if not (root / rel).is_file():
            missing.append(rel)
    if not (
        (root / "output" / "GLOBAL-AUDIT.md").is_file()
        or (root / "output" / "DASHBOARD.md").is_file()
    ):
        missing.append("output/GLOBAL-AUDIT.md|DASHBOARD.md")
    if with_graph:
        graph_runs = root / "graph" / "runs"
        has_graph = graph_runs.is_dir() and any(graph_runs.iterdir())
        if not has_graph and not (root / "graph" / "PHASE-SUMMARY.json").is_file():
            missing.append("graph/runs/<id>/ or graph/PHASE-SUMMARY.json")
    if missing:
        log(
            "WARN: REVIEW-READY not written — missing: "
            + ", ".join(missing)
        )
        return None
    plates = list(REVIEW_READY_PATH_FINDINGS + REVIEW_READY_PLATES)
    if (root / "output" / "GLOBAL-AUDIT.md").is_file():
        plates.append("output/GLOBAL-AUDIT.md")
    if (root / "output" / "DASHBOARD.md").is_file():
        plates.append("output/DASHBOARD.md")
    payload = {
        "run_id": run_id,
        "model": model,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "with_graph": with_graph,
        "plates": plates,
    }
    path = root / "REVIEW-READY.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log(f"review-ready: wrote {path}")
    return path


def run_stage(script: Path, args: list[str], project_id: str) -> None:
    """Shell out to a stage, then enforce its declared output contract."""
    run_step(script, args)
    assert_stage_outputs(script, project_id)


def _health_candidates(chat_completions_url: str) -> list[str]:
    """Possible health endpoints for an OpenAI-compatible chat URL.

    llama.cpp serves /health; the Cursor bridge serves /healthz.
    """
    parsed = urlparse(chat_completions_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid model URL: {chat_completions_url!r}")
    base = f"{parsed.scheme}://{parsed.netloc}"
    # Prefer /healthz first on the Cursor bridge port.
    if ":8788" in parsed.netloc or parsed.netloc.endswith("8788"):
        return [f"{base}/healthz", f"{base}/health"]
    return [f"{base}/health", f"{base}/healthz"]


def preflight_models() -> None:
    """Health-check analyst/verifier endpoints from config.yaml (not hardcoded ports)."""
    import os

    cfg = load_config()
    models = cfg.get("models") or {}
    checks: list[tuple[str, str]] = []
    for role in ("analyst", "verifier"):
        url = models.get(f"{role}_url")
        if not url:
            raise RuntimeError(f"config.yaml missing models.{role}_url")
        checks.append((role, str(url)))

    headers = {}
    key = models.get("api_key") or os.environ.get("CURSOR_API_KEY") or ""
    if key:
        headers["Authorization"] = f"Bearer {key}"

    # Deduplicate when both roles point at the same server (single-model doctrine).
    seen: set[str] = set()
    for role, url in checks:
        ok = False
        last_err: Exception | None = None
        for health in _health_candidates(url):
            if health in seen:
                ok = True
                break
            try:
                r = requests.get(health, headers=headers or None, timeout=10)
                r.raise_for_status()
                seen.add(health)
                ok = True
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        if not ok:
            raise RuntimeError(
                f"{role} not reachable for {url}: {last_err}\n"
                "  Check models.*_url in config (and CURSOR_API_KEY for :8788)."
            )
    log(f"models: OK ({', '.join(sorted(seen))})")


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    log(f"→ {' '.join(cmd)}")
    # Pipe stderr so we can classify import/syntax crashes, but tee every line to
    # the console — operators still need the live traceback when a stage fails.
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr_chunks: list[str] = []
    assert proc.stderr is not None
    for line in proc.stderr:
        sys.stderr.write(line)
        stderr_chunks.append(line)
    rc = proc.wait()
    if rc != 0:
        err = "".join(stderr_chunks)
        if any(marker in err for marker in _STAGE_BROKEN_MARKERS):
            last = next(
                (ln.strip() for ln in reversed(err.splitlines()) if ln.strip()),
                f"exit {rc}",
            )
            raise StageBrokenError(
                f"broken import/syntax in {script.name} (exit {rc}): {last}"
            )
        raise RuntimeError(f"failed: {script.name} (exit {rc})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Crystallize on any curriculum dataset under projects/<id>/ "
            "(documents in → Layer-1-backed global report out)"
        )
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Curriculum dataset id under projects/ (data, not a separate product)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run rollup (overwrite pacing-plan)",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Re-run model ingest (organize docs + infer calendars → YAML)",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        help="Source folder for --ingest / Layer 0 (default: projects/<id>/sources)",
    )
    parser.add_argument(
        "--only",
        metavar="UNIT",
        help=(
            "Single unit only: Layer 0 --only UNIT (filename substring); "
            "Layer 1 --only-unit UNIT"
        ),
    )
    parser.add_argument(
        "--skip-rollup",
        action="store_true",
        help="Skip pacing-plan / year-at-a-glance inference",
    )
    parser.add_argument(
        "--skip-layer01",
        action="store_true",
        help=(
            "Skip Layer 0/1 (headline conformance). "
            "GLOBAL-AUDIT.md/DASHBOARD.md will be missing or stale."
        ),
    )
    parser.add_argument(
        "--layer0-no-resume",
        action="store_true",
        help="Pass --no-resume to layer0.py (full re-extract)",
    )
    parser.add_argument(
        "--skip-drive-push",
        action="store_true",
        help="Do not upload GLOBAL-AUDIT-REPORT.pdf to Google Drive after the run",
    )
    parser.add_argument(
        "--with-graph",
        action="store_true",
        help=(
            "Run opt-in graph phase after Layer 0-B (HAS-PART belonging under "
            "e2e/runs/<run>/graph/runs/<model>/). See docs/GRAPH-PHASE.md."
        ),
    )
    parser.add_argument(
        "--graph-backend",
        choices=("local", "cursor"),
        default="local",
        help="Graph model backend: local=config.yaml model_chat; cursor=Cursor SDK (Grok)",
    )
    parser.add_argument(
        "--graph-run",
        help=(
            "E2E + graph run id (default: slug of analyst model). "
            "Writes under projects/<id>/e2e/runs/<id>/."
        ),
    )
    parser.add_argument(
        "--graph-cursor-model",
        default="grok-4.5",
        help="Cursor model id when --graph-backend cursor",
    )
    parser.add_argument(
        "--graph-only",
        action="store_true",
        help=(
            "Run only the graph phase under an E2E tree (requires layer0/ledger.json; "
            "graph-only may symlink curriculum layer0). Does not overwrite Path A–H, "
            "Layer 1/2, or reports."
        ),
    )
    parser.add_argument(
        "--allow-live-root",
        action="store_true",
        help=(
            "Write into the golden projects/<id>/ tree instead of e2e/runs/. "
            "Escape hatch for overnight/golden refresh only — default is E2E."
        ),
    )
    args = parser.parse_args()

    try:
        validate_slug_id(args.project, "project id")
        only_unit = None
        if args.only:
            only_unit = validate_slug_id(args.only.lower().replace(" ", "-"), "unit id")
    except ValueError as e:
        log(f"ERROR: {e}")
        return 2

    # E2E-only default: isolate every pipeline write under e2e/runs/<run_id>/.
    # Best practice: derive the run id from --graph-run or the configured model
    # so operators cannot accidentally clobber the golden curriculum root.
    cfg_models = (load_config().get("models") or {})
    if args.graph_backend == "cursor":
        default_model = args.graph_cursor_model or "grok-4.5"
    else:
        default_model = str(
            cfg_models.get("analyst_model")
            or cfg_models.get("verifier_model")
            or "local-model"
        )
    run_hint = args.graph_run or slugify_run_id(default_model)
    e2e_id = ensure_e2e_env(
        args.project,
        run_id=run_hint,
        model=default_model,
        backend=args.graph_backend,
        graph_only=bool(args.graph_only),
        allow_live_root=bool(args.allow_live_root),
    )
    if e2e_id:
        log(f"e2e: LOOM_E2E_RUN={e2e_id} → projects/{args.project}/e2e/runs/{e2e_id}/")
        if not args.graph_run:
            args.graph_run = e2e_id
    else:
        log("e2e: --allow-live-root — writing into golden projects/ tree")

    root = project_dir(args.project)
    manifest = root / "manifest.yaml"
    sources = args.sources or (root / "sources")
    # Propagate to every subprocess (layer0/1/2, graph, synthesize, …) so
    # model_chat can append to projects/<id>/usage.jsonl without each script
    # wiring its own meter.
    set_usage_project(args.project)

    try:
        if args.graph_only:
            if not args.with_graph:
                args.with_graph = True
            # Graph-only: preserve Path A/L1/reports; only write namespaced graph runs.
            g_args = ["--project", args.project, "--backend", args.graph_backend]
            if only_unit:
                g_args.extend(["--only-unit", only_unit])
            if args.force:
                g_args.append("--force")
            if args.graph_run:
                g_args.extend(["--graph-run", args.graph_run])
            if args.graph_backend == "cursor":
                g_args.extend(["--cursor-model", args.graph_cursor_model])
            # Cursor backend talks to Cursor cloud — local llama health optional.
            if args.graph_backend == "local":
                preflight_models()
            run_stage(GRAPH_PHASE, g_args, args.project)
            usage_summary = write_usage_summary(args.project)
            usage_totals = usage_summary.get("totals") or {}
            print("\n" + "=" * 60)
            print("DONE — graph-only run")
            print("=" * 60)
            if e2e_id:
                print(f"  E2E root:    projects/{args.project}/e2e/runs/{e2e_id}/")
            else:
                print(f"  Dataset:     projects/{args.project}/  (live root)")
            print(f"  Graph runs:  {root / 'graph' / 'runs'}/")
            print(f"  Active:      {root / 'graph' / 'ACTIVE'}")
            print(
                f"  Token usage: {root / 'USAGE-SUMMARY.json'} "
                f"(calls={usage_totals.get('n_calls', 0)} "
                f"total_tokens={usage_totals.get('total_tokens', 0)})"
            )
            print("=" * 60 + "\n")
            return 0

        preflight_models()

        if args.ingest or not manifest.is_file():
            ingest_args = ["--project", args.project]
            if args.sources:
                ingest_args.extend(["--sources", str(args.sources)])
            elif sources.is_dir():
                ingest_args.extend(["--sources", str(sources)])
            else:
                raise RuntimeError(
                    f"No manifest and no sources at {sources}. "
                    "Drop documents in projects/<id>/sources/ or pass --sources"
                )
            run_stage(INGEST, ingest_args, args.project)

        if not args.skip_rollup:
            log("rollup: provisional early spine (authoritative calendars run after assemble)")
            rollup_args = ["--project", args.project]
            if args.force:
                rollup_args.append("--force")
            run_stage(ROLLUP, rollup_args, args.project)

        # Headline path: element-level extraction → placement conformance → globals.
        if not args.skip_layer01:
            if not sources.is_dir() and not args.sources:
                src = sources
            else:
                src = args.sources or sources
            if not src.is_dir():
                raise RuntimeError(
                    f"Layer 0 requires sources at {src}. "
                    "Drop curriculum files there, or pass --skip-layer01."
                )

            l0_args = ["--project", args.project, "--sources", str(src)]
            if only_unit:
                # Filename substring filter — unit slug usually appears in extracts.
                l0_args.extend(["--only", only_unit])
            if args.layer0_no_resume:
                l0_args.append("--no-resume")
            run_stage(LAYER0, l0_args, args.project)

            # Layer 0-B (citation precision): Layer 0-A guarantees every excerpt is a
            # verbatim, contiguous span, but a span wider than WIDE_SPAN_PARAGRAPHS can
            # still be several distinct elements merged under one over-broad citation.
            # This pass reviews only those flagged rows and splits them, so Layer 1
            # sorts real single-purpose elements instead of lumped ones.
            run_stage(
                LAYER0, ["--project", args.project, "--resolve-wide-spans"], args.project
            )

            # Opt-in graph phase (docs/GRAPH-PHASE.md): belonging tree under
            # projects/<id>/graph/runs/<model>/ — before route so Path typing
            # does not freeze org. Each model keeps its own run dir for A/B.
            if args.with_graph:
                g_args = ["--project", args.project, "--backend", args.graph_backend]
                if only_unit:
                    g_args.extend(["--only-unit", only_unit])
                if args.force:
                    g_args.append("--force")
                if args.graph_run:
                    g_args.extend(["--graph-run", args.graph_run])
                if args.graph_backend == "cursor":
                    g_args.extend(["--cursor-model", args.graph_cursor_model])
                run_stage(GRAPH_PHASE, g_args, args.project)

            # Loom router — BEFORE unit placement. Writes layer0/route-map.json.
            run_stage(ROUTE, ["--project", args.project], args.project)

            # Path A–H workflows (lesson / assessment / general / teacher support /
            # student practice / standards & pacing / syllabus / exit ticket).
            if PATH_WORKFLOWS.is_file():
                run_stage(PATH_WORKFLOWS, ["--project", args.project], args.project)
            else:
                log(f"WARN: path workflows missing: {PATH_WORKFLOWS}")

            l1_args = ["--project", args.project]
            if only_unit:
                l1_args.extend(["--only-unit", only_unit])
            # Soft gate: Layer 1 only considers docs present in route-map (see layer1).
            run_stage(LAYER1, l1_args, args.project)

            # Layer 2 (lesson structural completeness): zero new model calls — reads
            # Layer 0's element ledger + Layer 1's just-written FULFILLED findings and
            # checks whether each role-fulfilling document contains the internal
            # instructional-function components a complete document of that role
            # should have (docs/BETS.md note under Bet 10/11).
            l2_args = ["--project", args.project]
            if only_unit:
                l2_args.extend(["--only-unit", only_unit])
            run_stage(LAYER2, l2_args, args.project)

            # Deterministic rungs (offline) + advisory quality/review (model).
            # Educational note: rungs never block; quality is ~6 calls/lesson and
            # writes the UI heatmap plate under project_dir()/output/ (honors
            # LOOM_E2E_RUN so per-model A/B trees stay isolated).
            # StageOutputError is re-raised with StageBrokenError: a stage that
            # "succeeds" while writing nothing must not soft-skip into a green run.
            if LESSON_RUNG.is_file():
                try:
                    run_stage(LESSON_RUNG, ["--project", args.project], args.project)
                except (StageBrokenError, StageOutputError):
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-rung skipped: {e}")
            if ARTIFACT_RUNG.is_file():
                try:
                    run_stage(ARTIFACT_RUNG, ["--project", args.project], args.project)
                except (StageBrokenError, StageOutputError):
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: artifact-rung skipped: {e}")
            if UNIT_RUNG.is_file():
                try:
                    run_stage(UNIT_RUNG, ["--project", args.project], args.project)
                except (StageBrokenError, StageOutputError):
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: unit-rung skipped: {e}")
            if LESSON_QUALITY.is_file():
                try:
                    run_stage(LESSON_QUALITY, ["--project", args.project], args.project)
                except (StageBrokenError, StageOutputError):
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-quality plate skipped: {e}")
            if CURRICULUM_REVIEW.is_file():
                try:
                    run_stage(
                        CURRICULUM_REVIEW, ["--project", args.project], args.project
                    )
                except (StageBrokenError, StageOutputError):
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: curriculum-review skipped: {e}")

            # Model calendars after assemble (authoritative inferred map).
            # Early rollup remains provisional year spine only.
            if CALENDARS.is_file():
                run_stage(
                    CALENDARS,
                    ["--project", args.project, "--model-note"],
                    args.project,
                )
            else:
                log(f"WARN: calendars.py missing: {CALENDARS}")

            run_stage(
                SYNTH,
                ["--project", args.project, "--report", "all", "--delivery", "model"],
                args.project,
            )
        else:
            log("skip-layer01: conformance globals not refreshed")
            try:
                run_stage(
                    SYNTH,
                    [
                        "--project",
                        args.project,
                        "--report",
                        "all",
                        "--delivery",
                        "model",
                    ],
                    args.project,
                )
            except (StageBrokenError, StageOutputError):
                raise
            except RuntimeError as e:
                log(f"WARN: cross-unit synthesis skipped: {e}")
                log(
                    "  Re-run without --skip-layer01, or manually: "
                    f"python3 layer0.py --project {args.project} && "
                    f"python3 layer1.py --project {args.project} && "
                    f"python3 synthesize.py --project {args.project} --report all"
                )

    except RuntimeError as e:
        log(f"ERROR: {e}")
        return 1

    # Default: push the course report PDF to Drive (organized by curriculum id).
    # Soft-fail — a Drive outage must not fail an otherwise successful audit.
    if not args.skip_drive_push:
        if PUSH_DRIVE.is_file():
            log(
                f"→ {' '.join([sys.executable, str(PUSH_DRIVE), '--project', args.project])}"
            )
            rc = subprocess.call(
                [sys.executable, str(PUSH_DRIVE), "--project", args.project],
                cwd=BASE_DIR,
            )
            if rc != 0:
                log(
                    f"WARN: Drive push exited {rc} (reports are still local under output/)"
                )
        else:
            log(f"WARN: Drive push script missing: {PUSH_DRIVE}")
    else:
        log("skip-drive-push: Google Drive upload skipped")

    usage_summary = write_usage_summary(args.project)
    usage_totals = usage_summary.get("totals") or {}

    # Gate the Review UI: only full e2e runs (not live-root / graph-only) publish.
    if e2e_id and not args.graph_only and not args.allow_live_root:
        ready = write_review_ready(
            args.project,
            run_id=e2e_id,
            model=str(default_model),
            with_graph=bool(args.with_graph),
        )
        if ready:
            print(f"  Review UI:   READY ({ready.name})")
        else:
            print("  Review UI:   not ready (incomplete plates — see WARN above)")

    out = root / "output"
    print("\n" + "=" * 60)
    print("DONE — reports ready")
    print("=" * 60)
    print(f"  Dataset:     projects/{args.project}/")
    if e2e_id:
        print(f"  E2E root:    projects/{args.project}/e2e/runs/{e2e_id}/")
    print(f"  Global PDF:  {out / 'GLOBAL-AUDIT-REPORT.pdf'}")
    print(f"  First-pass:  {out / 'FIRST-PASS.md'}")
    print(f"  Global MD:   {out / 'GLOBAL-AUDIT.md'}")
    print(f"  Dashboard:   {out / 'DASHBOARD.md'}")
    teachers = out / "teachers"
    if teachers.is_dir():
        print(f"  Teachers:    {teachers}/<unit>/TEACHER-PACKET.md")
    print(f"  Summary:     {out / 'SUMMARY.md'}")
    print(f"  Layer 0:     {root / 'layer0' / 'ledger.json'}")
    graph_summary = root / "graph" / "PHASE-SUMMARY.json"
    if graph_summary.is_file():
        print(f"  Graph:       {graph_summary}")
    print(f"  Layer 1:     {root / 'layer1' / 'bucket-ledger.json'}")
    l2_findings = root / "layer2" / "findings.json"
    if l2_findings.is_file():
        print(f"  Layer 2:     {l2_findings}")
    pacing = root / "pacing-plan.yaml"
    if pacing.is_file():
        print(f"  Pacing plan: {pacing}")
        print(f"  Year map:    {out / '03-year-calendar-map.md'}")
    print(
        f"  Token usage: {root / 'USAGE-SUMMARY.json'} "
        f"(calls={usage_totals.get('n_calls', 0)} "
        f"total_tokens={usage_totals.get('total_tokens', 0)})"
    )
    if not args.skip_drive_push:
        print(
            f"  Drive:       gdrive:DISD CTE/Crystallize/{args.project}/"
            " (global PDF + teachers/*.pdf + runs/ archive)"
        )
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
