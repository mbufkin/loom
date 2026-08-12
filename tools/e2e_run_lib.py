#!/usr/bin/env python3
"""Per-model full-pipeline A/B trees under projects/<id>/e2e/runs/<run_id>/.

Educational note: **E2E is the canonical write root.** Set LOOM_E2E_RUN=<run_id>
so audit_lib.project_dir() resolves into this tree; symlink sources/ +
manifest.yaml from the curriculum root (shared inputs). Nested graph artifacts
land at e2e/runs/<id>/graph/runs/<id>/ — do not start new bare
projects/<id>/graph/runs/ writes (legacy archive only).

Best practice: call ensure_e2e_env() from run_project / queues so a missing
LOOM_E2E_RUN cannot silently clobber the golden curriculum tree.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def slugify_run_id(label: str) -> str:
    s = (label or "model").strip().replace("\\", "/").split("/")[-1]
    s = re.sub(r"\.gguf$", "", s, flags=re.I)
    s = re.sub(r"[^\w.\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return (s or "model")[:80]


def curriculum_root(project_id: str) -> Path:
    return ROOT / "projects" / project_id


def e2e_runs_root(project_id: str) -> Path:
    return curriculum_root(project_id) / "e2e" / "runs"


def e2e_run_dir(project_id: str, run_id: str) -> Path:
    return e2e_runs_root(project_id) / slugify_run_id(run_id)


def prepare_e2e_run(
    project_id: str,
    run_id: str,
    *,
    model: str,
    backend: str,
    lane: str = "e2e",
    link_layer0_from_curriculum: bool = False,
) -> Path:
    """Create isolated run dir with symlinked sources + manifest. Idempotent.

    When ``link_layer0_from_curriculum`` is True (graph-only A/B under E2E),
    symlink curriculum ``layer0/`` so HAS-PART can run without re-extracting.
    Full E2E leaves layer0 writable inside the run (do not pass the flag).
    """
    rid = slugify_run_id(run_id)
    base = curriculum_root(project_id)
    if not base.is_dir():
        raise FileNotFoundError(base)
    run = e2e_run_dir(project_id, rid)
    run.mkdir(parents=True, exist_ok=True)

    # Shared inputs — never copy the corpus; one sources/units tree for all A/B runs.
    # Writable outputs (layer0/1/2, output, path_*, graph, usage) stay inside `run`.
    required = ("sources", "manifest.yaml", "units")
    optional = (
        "school-calendar.yaml",
        "pacing-plan.yaml",
        "calendars_inferred",
        "reference",
        "_loom_feedback.yaml",
    )
    for name in required + optional:
        src = base / name
        dst = run / name
        if dst.exists() or dst.is_symlink():
            continue
        if not src.exists():
            if name in required:
                raise FileNotFoundError(f"missing {src}")
            continue
        dst.symlink_to(os.path.relpath(src, start=run))

    # Graph-only under E2E: reuse curriculum Layer 0 ledger (read-mostly).
    if link_layer0_from_curriculum:
        src = base / "layer0"
        dst = run / "layer0"
        if not (dst.exists() or dst.is_symlink()) and src.is_dir():
            dst.symlink_to(os.path.relpath(src, start=run))

    meta_path = run / "RUN.json"
    prev: dict = {}
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    now = datetime.now(timezone.utc).isoformat()
    meta = {
        **prev,
        "run_id": rid,
        "project_id": project_id,
        "model": model,
        "backend": backend,
        "lane": lane,
        "updated_at": now,
    }
    if "started_at" not in meta:
        meta["started_at"] = now
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return run


def ensure_e2e_env(
    project_id: str,
    *,
    run_id: str | None = None,
    model: str = "unknown",
    backend: str = "local",
    graph_only: bool = False,
    allow_live_root: bool = False,
) -> str | None:
    """Ensure LOOM_E2E_RUN is set and the e2e tree exists.

    Returns the active run id, or None when ``allow_live_root`` opts into the
    golden curriculum tree (overnight / intentional live writes only).

    Best practice: never rely on callers remembering the env var — defaulting
    here is what keeps graph/layer/output out of projects/<id>/ root.
    """
    if allow_live_root or os.environ.get("LOOM_ALLOW_LIVE_ROOT", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return None

    existing = (os.environ.get("LOOM_E2E_RUN") or "").strip()
    rid = slugify_run_id(existing or run_id or model or "model")
    os.environ["LOOM_E2E_RUN"] = rid
    prepare_e2e_run(
        project_id,
        rid,
        model=model,
        backend=backend,
        lane="e2e-graph-only" if graph_only else "e2e",
        link_layer0_from_curriculum=graph_only,
    )
    return rid
