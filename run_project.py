#!/usr/bin/env python3
"""
run_project.py — One command: any curriculum in → solid audit report out.

Program (this repo) + data (projects/<id>/). Drop files in sources/, run once.

  preflight → ingest (if needed) → rollup (provisional; calendars authoritative after assemble)
           → layer0 (0-A decompose → 0-B resolve-wide-spans)
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

INGEST = BASE_DIR / "ingest.py"
ROLLUP = BASE_DIR / "rollup.py"
LAYER0 = BASE_DIR / "layer0.py"
ROUTE = BASE_DIR / "route.py"
TE_PREPASS = BASE_DIR / "te_prepass.py"
PATH_WORKFLOWS = BASE_DIR / "workflows" / "run_paths.py"
LAYER1 = BASE_DIR / "layer1.py"
LAYER2 = BASE_DIR / "layer2.py"
LESSON_RUNG = BASE_DIR / "lesson_rung.py"
ARTIFACT_RUNG = BASE_DIR / "artifact_rung.py"
UNIT_RUNG = BASE_DIR / "unit_rung.py"
LESSON_QUALITY = BASE_DIR / "lesson_quality.py"
CALENDARS = BASE_DIR / "calendars.py"
SYNTH = BASE_DIR / "synthesize.py"
PUSH_DRIVE = BASE_DIR / "tools" / "push_drive_reports.py"


def _health_url(chat_completions_url: str) -> str:
    """Derive a /health URL from an OpenAI-compatible chat completions endpoint."""
    parsed = urlparse(chat_completions_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid model URL: {chat_completions_url!r}")
    return f"{parsed.scheme}://{parsed.netloc}/health"


def preflight_models() -> None:
    """Health-check analyst/verifier endpoints from config.yaml (not hardcoded ports)."""
    cfg = load_config()
    models = cfg.get("models") or {}
    checks: list[tuple[str, str]] = []
    for role in ("analyst", "verifier"):
        url = models.get(f"{role}_url")
        if not url:
            raise RuntimeError(f"config.yaml missing models.{role}_url")
        checks.append((role, str(url)))

    # Deduplicate when both roles point at the same server (single-model doctrine).
    seen: set[str] = set()
    for role, url in checks:
        health = _health_url(url)
        if health in seen:
            continue
        seen.add(health)
        try:
            r = requests.get(health, timeout=10)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"{role} not reachable at {health}: {e}\n"
                "  Check models.*_url in config.yaml and start your local server."
            ) from e
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

    try:
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

            # Loom router — BEFORE unit placement. Writes layer0/route-map.json.
            run_step(ROUTE, ["--project", args.project])

            # Teacher-Edition pre-pass — fan any multi-lesson TE into per-lesson child
            # records (layer_lesson/te_children/) so a TE's lessons can be reviewed as
            # discrete lessons. No-op for corpora without multi-lesson TEs.
            if TE_PREPASS.is_file():
                run_step(TE_PREPASS, ["--project", args.project])

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

            # Lesson rung (locked): the bake-off's winning deterministic scorers over
            # every lesson (incl. TE children) -> layer_lesson/LESSON-RUNG.json, the
            # per-unit rollup the future unit rung consumes. Offline, no model calls;
            # never blocks the run.
            if LESSON_RUNG.is_file():
                try:
                    run_step(LESSON_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-rung skipped: {e}")

            # Artifact rung (Paths B/C): review every NON-lesson doc (quizzes, exit
            # tickets, rubrics, worksheets, ...) with its per-type presence spec ->
            # layer_artifact/ARTIFACT-RUNG.json. Deterministic presence only by
            # default (offline, gates the unit band); the advisory model alignment is
            # opt-in (--with-model on artifact_rung.py). Runs BEFORE the unit rung,
            # which consumes its per-unit gaps. Never blocks the run.
            if ARTIFACT_RUNG.is_file():
                try:
                    run_step(ARTIFACT_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: artifact-rung skipped: {e}")

            # Unit rung: roll the lesson rung + artifact rung + Layer 1/2 + pacing
            # into a per-unit verdict (layer_unit/UNIT-RUNG.json), the hand-off for
            # the future curriculum rung. Deterministic, offline; depends on the
            # rungs above so it runs right after, and never blocks the run.
            if UNIT_RUNG.is_file():
                try:
                    run_step(UNIT_RUNG, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: unit-rung skipped: {e}")

            # Lesson-quality plate (advisory): the decomposed, evidence-first quality
            # scorer over every lesson -> output/LESSON-QUALITY-FEEDBACK.{md,json}, the
            # per-dimension review the UI drills into. Model-based (6 calls/lesson) so it
            # runs AFTER the deterministic rungs; advisory-only (never gates a verdict)
            # and NON-BLOCKING so an offline model or a bad lesson can't sink the audit.
            if LESSON_QUALITY.is_file():
                try:
                    run_step(LESSON_QUALITY, ["--project", args.project])
                except Exception as e:  # noqa: BLE001
                    log(f"WARN: lesson-quality plate skipped: {e}")

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
    print(f"  Layer 1:     {root / 'layer1' / 'bucket-ledger.json'}")
    l2_findings = root / "layer2" / "findings.json"
    if l2_findings.is_file():
        print(f"  Layer 2:     {l2_findings}")
    pacing = root / "pacing-plan.yaml"
    if pacing.is_file():
        print(f"  Pacing plan: {pacing}")
        print(f"  Year map:    {out / '03-year-calendar-map.md'}")
    if not args.skip_drive_push:
        print(
            f"  Drive:       gdrive:DISD CTE/Crystallize/{args.project}/"
            " (global PDF + teachers/*.pdf + runs/ archive)"
        )
    # Honest degradation line: if any docs were routed best-effort (unknown type or
    # low confidence), say so here instead of implying a clean pass. One line, not
    # one flag per doc — the same noise-reduction discipline as the reports.
    try:
        from route import degraded_summary

        deg = degraded_summary(args.project)
        if deg["count"]:
            by_type = ", ".join(
                f"{t}×{n}"
                for t, n in sorted(deg["by_type"].items(), key=lambda x: -x[1])
            )
            print(
                f"  DEGRADED:    {deg['count']} doc(s) ran best-effort ({by_type}) — "
                "output limited, tickets in _loom_feedback.yaml"
            )
    except Exception:
        pass
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
