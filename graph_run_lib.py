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
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path


def _is_link(p: Path) -> bool:
    """True for a symlink and, on Windows, for a directory junction too.

    Path.is_symlink() answers False for a junction, so code that asks only
    that question sees a junction as an ordinary directory full of real data.
    set_active_graph_run asks it before deciding whether graph/units is
    pre-namespace data worth preserving -- so once junctions became the
    Windows fallback, the second call of a single run "migrated" its own
    junction into runs/legacy-pre-namespace, and that phantom run then showed
    up beside the real one in the review UI's run picker.
    """
    if p.is_symlink():
        return True
    try:
        attrs = getattr(p.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _remove_link(p: Path) -> None:
    """Remove a link without touching what it points at.

    A junction is a directory to the Windows API, so unlink refuses it and
    rmdir is the call that removes the link itself rather than its contents.
    """
    try:
        p.unlink()
    except OSError:
        os.rmdir(p)


def _point_at(link: Path, target_rel: Path, *, is_dir: bool) -> str:
    """Make `link` resolve to `target_rel`, however the platform permits.

    Returns the mechanism used, for the caller's log.

    Windows refuses os.symlink unless the process is elevated or Developer
    Mode is on, and raises WinError 1314 otherwise. That killed a whole audit
    on the machine this was first run on: Layer 0 and Layer 0-B had finished,
    the graph phase had written every unit, and the run then aborted creating
    a convenience link. Nothing that matters depends on these links --
    graph/ACTIVE records which run is current, and the review UI reads
    graph/runs/<id>/units/... directly -- so they are worth attempting and
    never worth failing a run over.

    A directory junction is the Windows equivalent that needs no privilege;
    for the small JSON pointer a plain copy is truthful enough, since it is
    rewritten on every run.
    """
    target_abs = (link.parent / target_rel).resolve()
    try:
        os.symlink(target_rel, link, target_is_directory=is_dir)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass
    if is_dir and os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(target_abs), str(link))
            return "junction"
        except Exception:
            pass
    if not is_dir and target_abs.is_file():
        shutil.copy2(target_abs, link)
        return "copy"
    return "skipped"


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
    if _is_link(link):
        _remove_link(link)
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
        how = _point_at(link, target, is_dir=True)
        if how == "skipped":
            from audit_lib import log

            log(
                f"NOTE: could not create {link} (no symlink or junction support). "
                f"graph/ACTIVE still names the run; only legacy graph/units readers "
                f"are affected."
            )

    # Also expose PHASE-SUMMARY at graph/ for run_project DONE banner.
    phase = run_dir / "PHASE-SUMMARY.json"
    phase_link = graph / "PHASE-SUMMARY.json"
    if phase.is_file():
        if _is_link(phase_link) or phase_link.exists():
            _remove_link(phase_link)
        _point_at(phase_link, Path("runs") / rid / "PHASE-SUMMARY.json", is_dir=False)


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
