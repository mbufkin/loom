"""Model-namespaced graph run directories for A/B comparisons.

Educational note: with LOOM_E2E_RUN set, paths resolve under
``projects/<id>/e2e/runs/<e2e_id>/graph/runs/<run_id>/`` (canonical). Bare
``projects/<id>/graph/runs/`` is a legacy archive. ``graph/ACTIVE`` records
which nested run is current; ``graph/units`` is a convenience symlink.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def slugify_run_id(label: str) -> str:
    """Turn a model path/id into a filesystem-safe run id."""
    s = (label or "model").strip()
    # Drop directory prefixes from gguf paths.
    s = s.replace("\\", "/").split("/")[-1]
    s = re.sub(r"\.gguf$", "", s, flags=re.I)
    s = re.sub(r"[^\w.\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return (s or "model")[:80]


def graph_runs_root(project_root: Path) -> Path:
    return project_root / "graph" / "runs"


def graph_run_dir(project_root: Path, run_id: str) -> Path:
    return graph_runs_root(project_root) / slugify_run_id(run_id)


def graph_unit_dir(project_root: Path, run_id: str, unit_id: str) -> Path:
    return graph_run_dir(project_root, run_id) / "units" / unit_id


def active_run_path(project_root: Path) -> Path:
    return project_root / "graph" / "ACTIVE"


def read_active_run(project_root: Path) -> str | None:
    p = active_run_path(project_root)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text or None


def write_run_meta(
    project_root: Path,
    run_id: str,
    *,
    backend: str,
    model: str,
    extra: dict | None = None,
) -> Path:
    """Write/update RUN.json inside the run directory."""
    rid = slugify_run_id(run_id)
    run_dir = graph_run_dir(project_root, rid)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path = run_dir / "RUN.json"
    prev = {}
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    meta = {
        **prev,
        "run_id": rid,
        "backend": backend,
        "model": model,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if "started_at" not in meta:
        meta["started_at"] = meta["updated_at"]
    if extra:
        meta.update(extra)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta_path


def set_active_graph_run(project_root: Path, run_id: str) -> None:
    """Point graph/ACTIVE and graph/units → this run (non-destructive to other runs)."""
    rid = slugify_run_id(run_id)
    run_dir = graph_run_dir(project_root, rid)
    units = run_dir / "units"
    units.mkdir(parents=True, exist_ok=True)

    graph = project_root / "graph"
    graph.mkdir(parents=True, exist_ok=True)
    active_run_path(project_root).write_text(rid + "\n", encoding="utf-8")

    # Convenience symlink for legacy readers of graph/units/...
    link = graph / "units"
    target = Path("runs") / rid / "units"
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        # Preserve pre-namespaced data once: move into runs/legacy-units.
        legacy = graph_run_dir(project_root, "legacy-pre-namespace")
        legacy_units = legacy / "units"
        if not legacy_units.exists():
            legacy_units.parent.mkdir(parents=True, exist_ok=True)
            link.rename(legacy_units)
            write_run_meta(
                project_root,
                "legacy-pre-namespace",
                backend="unknown",
                model="unknown",
                extra={"note": "auto-migrated from graph/units before namespacing"},
            )
        else:
            raise RuntimeError(
                f"{link} exists as a real directory and legacy run already present; "
                "move it aside manually before continuing"
            )
    if not link.exists():
        os.symlink(target, link)

    # Also expose PHASE-SUMMARY at graph/ for run_project DONE banner.
    phase = run_dir / "PHASE-SUMMARY.json"
    phase_link = graph / "PHASE-SUMMARY.json"
    if phase.is_file():
        if phase_link.is_symlink() or phase_link.exists():
            phase_link.unlink()
        os.symlink(Path("runs") / rid / "PHASE-SUMMARY.json", phase_link)


def resolve_run_id(
    *,
    explicit: str | None,
    backend: str,
    model_label: str,
) -> str:
    if explicit:
        return slugify_run_id(explicit)
    if backend == "cursor":
        return slugify_run_id(model_label or "cursor-grok")
    return slugify_run_id(model_label or "local-model")
