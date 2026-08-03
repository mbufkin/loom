#!/usr/bin/env python3
"""
run_project.py — One command: any curriculum in → solid audit report out.

Program (this repo) + data (projects/<id>/). Drop files in sources/, run once.

  preflight → ingest (if needed) → rollup (provisional; calendars authoritative after assemble)
           → layer0 (0-A decompose → 0-B resolve-wide-spans)
           → graph_phase.py (opt-in --with-graph: HAS-PART belonging)
           → route.py (Loom Path A/B/C map — BEFORE unit placement)
           → path workflows (A lesson / B quiz stub / C general stub)
           → layer1 → layer2 → calendars.py (model day/year after assemble)
           → synthesize --report all --delivery model (+ first-pass PDF)
           → push reports to Google Drive (default; --skip-drive-push to opt out)

Usage:
  python3 run_project.py --project my-district
  python3 run_project.py --project my-district --force
  python3 run_project.py --project my-district --skip-layer01   # rollup + ingest only; Layer 0/1/2 + conformance globals skipped
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

from audit_lib import BASE_DIR, load_config, log, project_dir, validate_slug_id
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
    rc = subprocess.call(cmd, cwd=BASE_DIR)
    if rc != 0:
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
            "projects/<id>/graph/runs/<model>/). See docs/GRAPH-PHASE.md."
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
        help="Graph A/B run id (default: slug of model name under graph/runs/)",
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
            "Run only the graph phase (requires existing layer0/ledger.json). "
            "Does not overwrite Path A/B/C, Layer 1/2, or reports."
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
            run_step(GRAPH_PHASE, g_args)
            usage_summary = write_usage_summary(args.project)
            usage_totals = usage_summary.get("totals") or {}
            print("\n" + "=" * 60)
            print("DONE — graph-only run")
            print("=" * 60)
            print(f"  Dataset:     projects/{args.project}/")
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
            run_step(INGEST, ingest_args)

        if not args.skip_rollup:
            log("rollup: provisional early spine (authoritative calendars run after assemble)")
            rollup_args = ["--project", args.project]
            if args.force:
                rollup_args.append("--force")
            run_step(ROLLUP, rollup_args)

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
            run_step(LAYER0, l0_args)

            # Layer 0-B (citation precision): Layer 0-A guarantees every excerpt is a
            # verbatim, contiguous span, but a span wider than WIDE_SPAN_PARAGRAPHS can
            # still be several distinct elements merged under one over-broad citation.
            # This pass reviews only those flagged rows and splits them, so Layer 1
            # sorts real single-purpose elements instead of lumped ones.
            run_step(LAYER0, ["--project", args.project, "--resolve-wide-spans"])

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
                run_step(GRAPH_PHASE, g_args)

            # Loom router — BEFORE unit placement. Writes layer0/route-map.json.
            run_step(ROUTE, ["--project", args.project])

            # Path A/B/C workflows (A = full lesson; B/C stubs until built out).
            if PATH_WORKFLOWS.is_file():
                run_step(PATH_WORKFLOWS, ["--project", args.project])
            else:
                log(f"WARN: path workflows missing: {PATH_WORKFLOWS}")

            l1_args = ["--project", args.project]
            if only_unit:
                l1_args.extend(["--only-unit", only_unit])
            # Soft gate: Layer 1 only considers docs present in route-map (see layer1).
            run_step(LAYER1, l1_args)

            # Layer 2 (lesson structural completeness): zero new model calls — reads
            # Layer 0's element ledger + Layer 1's just-written FULFILLED findings and
            # checks whether each role-fulfilling document contains the internal
            # instructional-function components a complete document of that role
            # should have (docs/BETS.md note under Bet 10/11).
            l2_args = ["--project", args.project]
            if only_unit:
                l2_args.extend(["--only-unit", only_unit])
            run_step(LAYER2, l2_args)

            # Deterministic rungs (offline) + advisory quality/review (model).
            # Educational note: rungs never block; quality is ~6 calls/lesson and
            # writes the UI heatmap plate under project_dir()/output/ (honors
            # LOOM_E2E_RUN so per-model A/B trees stay isolated).
            if LESSON_RUNG.is_file():
                try:
                    run_step(LESSON_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-rung skipped: {e}")
            if ARTIFACT_RUNG.is_file():
                try:
                    run_step(ARTIFACT_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: artifact-rung skipped: {e}")
            if UNIT_RUNG.is_file():
                try:
                    run_step(UNIT_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: unit-rung skipped: {e}")
            if LESSON_QUALITY.is_file():
                try:
                    run_step(LESSON_QUALITY, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-quality plate skipped: {e}")
            if CURRICULUM_REVIEW.is_file():
                try:
                    run_step(CURRICULUM_REVIEW, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: curriculum-review skipped: {e}")

            # Model calendars after assemble (authoritative inferred map).
            # Early rollup remains provisional year spine only.
            if CALENDARS.is_file():
                run_step(CALENDARS, ["--project", args.project, "--model-note"])
            else:
                log(f"WARN: calendars.py missing: {CALENDARS}")

            run_step(
                SYNTH,
                ["--project", args.project, "--report", "all", "--delivery", "model"],
            )
        else:
            log("skip-layer01: conformance globals not refreshed")
            try:
                run_step(
                    SYNTH,
                    [
                        "--project",
                        args.project,
                        "--report",
                        "all",
                        "--delivery",
                        "model",
                    ],
                )
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

    out = root / "output"
    print("\n" + "=" * 60)
    print("DONE — reports ready")
    print("=" * 60)
    print(f"  Dataset:     projects/{args.project}/")
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
