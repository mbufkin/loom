#!/usr/bin/env python3
"""
ui/server.py — Loom Run Review, local-only API.

A deliberately tiny, dependency-light HTTP server that lets a local browser
review the artifacts a completed Loom run wrote under projects/<id>/. It does
NOT invent curriculum in the auditor path; create-after-audit endpoints live
alongside and write only under projects/<id>/create/. Local-only by design:
no auth, binds to 127.0.0.1, and every file read is confined to the project dir.

Endpoints (all under /api):
  GET  /api/projects                      -> [{id, title, kind, has_output, ...}]
  GET  /api/projects/{id}/outputs[?e2e_run=] -> grouped tree of reviewable files
  GET  /api/projects/{id}/file?path=REL[&e2e_run=] -> raw bytes of one file (guarded)
  GET  /api/projects/{id}/stats[?e2e_run=] -> output/aggregate-stats.json
  GET  /api/projects/{id}/e2e/runs        -> full-pipeline snapshots under e2e/runs/*
  GET  /api/projects/{id}/graph/runs[?e2e_run=] -> model graph runs under graph/runs/*
  GET  /api/projects/{id}/graph/runs/{run_id}/overview[?e2e_run=] -> per-unit HAS-PART rollup
  GET  /api/projects/{id}/graph/runs/{run_id}/units/{unit_id}[?e2e_run=] -> HAS-PART + SUMMARY
  POST /api/projects/{id}/run             -> {runId}  (spawns run_project.py)
  POST /api/projects/{id}/packet-type     -> declare packet_type; regen unit rung
  GET  /api/projects/{id}/gaps            -> GapItem work queue (create chapter)
  GET  /api/projects/{id}/create/matrix   -> Unit matrix + UbD stage rollups (primary)
  GET  /api/projects/{id}/create/tree     -> Systemic patterns by role (secondary)
  GET  /api/projects/{id}/create/tree/{role} -> By-element L2 unit inventory
  GET  /api/projects/{id}/create/units    -> By-unit L1 (legacy)
  GET  /api/projects/{id}/create/units/{unit_id} -> Unit detail + UbD stages
  POST /api/projects/{id}/gaps/{gid}/decision
  POST /api/projects/{id}/gaps/{gid}/brief
  GET  /api/projects/{id}/gaps/{gid}/brief
  POST /api/projects/{id}/gaps/{gid}/draft  -> Cursor SDK supervised draft
  GET  /api/projects/{id}/gaps/{gid}/draft
  GET  /api/create/status                 -> Cursor key source / sdk ready
  GET  /api/runs/{runId}                  -> {status, exitCode, log}
  GET  /api/packet-types                  -> declarable packet-type registry
  GET  /api/config                        -> read-only config.yaml summary

Run:  .venv/bin/python ui/server.py [--port 8770]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Install root = parent of this ui/ directory. Holds the program itself, and
# must be importable before anything below can load loom_paths.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The install/data split (see loom_paths). On a developer checkout these are the
# same directory and nothing below behaves differently; on an installed copy the
# curricula live under the user's own data directory instead of inside the
# program folder, so one district never sees another's work — or ours.
from loom_paths import DATA_DIR as DATA_ROOT  # noqa: E402
from loom_paths import ensure_data_dirs, is_legacy_in_repo  # noqa: E402

# --- Ships with the program. Read-only in normal use. ---
# Built SPA bundle (npm run ui:build). Present only in production mode; when it
# is absent this server stays a pure JSON API and the Vite dev server on 5173
# serves the app, so the development flow is completely unaffected.
DIST = ROOT / "ui" / "dist"
# The pipeline entry point, invoked directly rather than through the ./run-audit
# shell wrapper. run-audit is one line -- `exec python3 run_project.py ...` -- so
# going through it bought nothing and cost two dependencies the app cannot
# assume: `bash`, which Windows does not ship, and `python3`, which on Windows
# is `python` or `py`. We are already inside a Python process, so sys.executable
# is the interpreter to use, and it is correct on Windows, macOS and Linux alike.
RUN_PROJECT = ROOT / "run_project.py"
PACKET_TYPES_SPEC = ROOT / "workflows" / "packet_types.yaml"
UNIT_RUNG_SCRIPT = ROOT / "unit_rung.py"

# --- Belongs to whoever is using the program. Survives an upgrade. ---
PROJECTS = DATA_ROOT / "projects"
CONFIG = DATA_ROOT / "config.yaml"
# Per-run log files. Deliberately not under ui/, which is program territory and
# may be read-only once this is packaged.
RUNS_DIR = DATA_ROOT / "logs" / "runs"

# Top-level "course plates" a reviewer wants first, in priority order. Only those
# that actually exist for a project are surfaced.
PLATE_FILES = [
    ("Dashboard", "output/DASHBOARD.md"),
    ("First pass", "output/FIRST-PASS.md"),
    ("Summary", "output/SUMMARY.md"),
    ("Review queue", "output/REVIEW-QUEUE.md"),
    ("Lesson quality feedback", "output/LESSON-QUALITY-FEEDBACK.md"),
    ("Global audit", "output/GLOBAL-AUDIT.md"),
    ("Year calendar map", "output/03-year-calendar-map.md"),
]
LAYER_FILES = [
    ("Layer 0 — decompose", "layer0/REPORT.md"),
    ("Layer 1 — organize", "layer1/REPORT.md"),
    ("Layer 1 — review queue", "layer1/REVIEW-QUEUE.md"),
    ("Layer 2 — completeness", "layer2/REPORT.md"),
    ("Artifact rung — Paths B–H", "layer_artifact/ARTIFACT-RUNG.md"),
    ("Unit rung", "layer_unit/UNIT-RUNG.md"),
]
PDF_FILES = [("Global audit PDF", "output/GLOBAL-AUDIT-REPORT.pdf")]
# Per-unit files, tried in this order under output/<unit>/.
UNIT_FILE_SPECS = [
    ("Report", "REPORT.md", "md"),
    ("Gap report", "02-gap-report.md", "md"),
    ("Calendar map", "01-calendar-map.md", "md"),
    ("Audit PDF", "AUDIT-REPORT.pdf", "pdf"),
]

# The eight review lenses, in router-cascade order. Labels mirror docs/PATHS.md;
# route-map.json also ships its own `lenses` map, which wins when present so a
# renamed lens does not need a UI change.
PATH_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H"]
PATH_LENSES = {
    "A": ("Lesson", "lesson_plan"),
    "B": ("Assessment", "quiz"),
    "C": ("General feedback", "general"),
    "D": ("Teacher support", "teacher_support"),
    "E": ("Student practice", "student_practice"),
    "F": ("Standards & pacing", "standards_pacing"),
    "G": ("Syllabus", "syllabus"),
    "H": ("Exit ticket", "exit_ticket"),
}
# Ordered so the UI can render a stable status legend / stacked bar. STUB marks
# the *5/*6 one-pager emit steps that are deliberately not implemented yet.
# OPTIONAL_ABSENT is an all-optional checklist step with no hit — advisory, not
# a finding (distinct from MISSING, which means a required field failed).
STEP_STATUSES = [
    "PRESENT",
    "PARTIAL",
    "MISSING",
    "OPTIONAL_ABSENT",
    "NOT_APPLICABLE",
    "STUB",
]

# In-memory run registry. Local single-user tool, so a dict + lock is plenty.
_RUNS: dict[str, dict] = {}
_RUNS_LOCK = threading.Lock()


def _read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _graph_unit_stats(has_part: dict, summary: dict | None) -> dict:
    """Compact belonging stats for heatmap / unit rows."""
    nodes = has_part.get("nodes") or []
    edges = has_part.get("edges") or []
    n_materials = sum(1 for n in nodes if n.get("type") == "Material")
    n_assessments = sum(1 for n in nodes if n.get("type") == "Assessment")
    lesson_ids = {n["id"] for n in nodes if n.get("type") == "Lesson" and n.get("id")}
    if not lesson_ids:
        # Some rebuilds attach via lesson: edges without Lesson nodes yet.
        for e in edges:
            for k in ("from", "to"):
                v = str(e.get(k) or "")
                if v.startswith("lesson:"):
                    lesson_ids.add(v)
    soft = []
    if isinstance(summary, dict):
        soft = list(summary.get("skipped_no_evidence") or [])
        n_lessons = int(summary.get("n_lessons") or len(lesson_ids))
    else:
        n_lessons = len(lesson_ids)
    # Materials with no lesson span are "soft-queued" for belonging review.
    attached = set()
    for e in edges:
        if e.get("rel") in ("spanIn", "hasPart") and str(e.get("to") or "").startswith(
            "material:"
        ):
            if str(e.get("from") or "").startswith("lesson:"):
                attached.add(e["to"])
        if e.get("rel") == "spanIn" and str(e.get("from") or "").startswith("lesson:"):
            attached.add(str(e.get("to") or ""))
    mat_ids = {n["id"] for n in nodes if n.get("type") == "Material" and n.get("id")}
    soft_queue = sorted(mat_ids - attached) if mat_ids else []
    return {
        "n_lessons": n_lessons,
        "n_materials": n_materials,
        "n_assessments": n_assessments,
        "n_soft_queue": len(soft_queue),
        "skipped_no_evidence": soft,
        "has_haspart": True,
    }


def _validate_run_id(run_id: str, label: str = "run id") -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id or ""):
        raise ValueError(f"invalid {label}")
    return run_id


def _workspace(project_id: str, e2e_run: str | None = None) -> Path:
    """Project root, or e2e/runs/<id>/ when reviewing a full-pipeline snapshot.

    Best practice: treat an E2E folder as a self-contained project mirror so
    plates, layers, teachers, and nested graph/runs all resolve the same way
    as the live tree — just rooted one level deeper.
    """
    root = _project_dir(project_id)
    if not e2e_run:
        return root
    rid = _validate_run_id(e2e_run, "e2e run id")
    ws = (root / "e2e" / "runs" / rid).resolve()
    # Stay strictly under the project (no symlink escapes outside projects/<id>).
    if root not in ws.parents or not ws.is_dir():
        raise FileNotFoundError(rid)
    return ws


def _list_e2e_runs(project_id: str) -> dict:
    """List reviewable E2E snapshots under e2e/runs/* (never e2e/archive/).

    Educational note: the Review UI only lists runs with REVIEW-READY.json so
    incomplete / other-model trees never appear as the product surface. Ops can
    still inspect archived or in-flight folders on disk.
    """
    root = _project_dir(project_id)
    runs_root = root / "e2e" / "runs"
    runs: list[dict] = []
    if runs_root.is_dir():
        for d in sorted(runs_root.iterdir()):
            if not d.is_dir():
                continue
            # Archive lives under e2e/archive/; never treat nested junk as a run.
            if d.name.startswith("."):
                continue
            out = d / "output"
            review_ready = (d / "REVIEW-READY.json").is_file()
            # Website contract: only completed runs are listed.
            if not review_ready:
                continue
            has_dashboard = (out / "DASHBOARD.md").is_file()
            has_quality = (out / "LESSON-QUALITY-FEEDBACK.json").is_file()
            # Nested graph run (often same id) for belonging panel wiring.
            nested_graph = d / "graph" / "runs"
            n_graph = 0
            if nested_graph.is_dir():
                n_graph = sum(1 for x in nested_graph.iterdir() if x.is_dir())
            # Prefer teacher packet count (common E2E shape); else output/<unit>/.
            teachers = out / "teachers"
            if teachers.is_dir():
                n_units = sum(1 for x in teachers.iterdir() if x.is_dir())
            elif out.is_dir():
                n_units = sum(
                    1
                    for x in out.iterdir()
                    if x.is_dir() and x.name not in ("teachers", "raw")
                )
            else:
                n_units = 0
            # When the audit finished, so the picker can label runs by date
            # instead of by internal run id. REVIEW-READY.json is written last,
            # which makes its mtime the closest thing to a completion time.
            try:
                finished = (d / "REVIEW-READY.json").stat().st_mtime
            except OSError:
                finished = None
            runs.append(
                {
                    "run_id": d.name,
                    "has_dashboard": has_dashboard,
                    "has_quality": has_quality,
                    "review_ready": True,
                    "n_output_units": n_units,
                    "n_graph_runs": n_graph,
                    "finished_at": finished,
                }
            )
    return {"project_id": project_id, "runs": runs}


def _list_graph_runs(project_id: str, e2e_run: str | None = None) -> dict:
    """List model-namespaced graph runs for the curriculum picker.

    Prefer nested graph under e2e/runs/<id>/ when reviewing an E2E snapshot.
    Bare projects/<id>/graph/runs is legacy archive (pre-E2E-only contract).
    """
    from graph_run_lib import read_active_run

    root = _workspace(project_id, e2e_run)
    runs_root = root / "graph" / "runs"
    # ACTIVE follows the workspace: e2e mirror when selected, else live root.
    active = read_active_run(root)
    runs: list[dict] = []
    if runs_root.is_dir():
        for d in sorted(runs_root.iterdir()):
            if not d.is_dir():
                continue
            meta = _read_json(d / "RUN.json") or {}
            units_dir = d / "units"
            unit_ids = []
            n_haspart = 0
            if units_dir.is_dir():
                for ud in sorted(units_dir.iterdir()):
                    if not ud.is_dir():
                        continue
                    unit_ids.append(ud.name)
                    if (ud / "HAS-PART.json").is_file():
                        n_haspart += 1
            if n_haspart == 0 and not meta:
                continue
            model = meta.get("model") if isinstance(meta, dict) else None
            runs.append(
                {
                    "run_id": d.name,
                    "model": model or d.name,
                    "backend": (meta or {}).get("backend") if isinstance(meta, dict) else None,
                    "started_at": (meta or {}).get("started_at") if isinstance(meta, dict) else None,
                    "updated_at": (meta or {}).get("updated_at") if isinstance(meta, dict) else None,
                    "n_units": len(unit_ids),
                    "n_haspart": n_haspart,
                    "active": d.name == active,
                }
            )
    return {
        "project_id": project_id,
        "active": active,
        "e2e_run": e2e_run,
        "runs": runs,
    }


def _graph_overview(
    project_id: str, run_id: str, e2e_run: str | None = None
) -> dict:
    run_id = _validate_run_id(run_id)
    root = _workspace(project_id, e2e_run)
    run_dir = root / "graph" / "runs" / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(run_id)
    meta = _read_json(run_dir / "RUN.json") or {}
    units: list[dict] = []
    units_dir = run_dir / "units"
    if units_dir.is_dir():
        for ud in sorted(units_dir.iterdir()):
            if not ud.is_dir():
                continue
            hp = _read_json(ud / "HAS-PART.json")
            if not isinstance(hp, dict):
                units.append(
                    {
                        "unit_id": ud.name,
                        "has_haspart": False,
                        "n_lessons": 0,
                        "n_materials": 0,
                        "n_assessments": 0,
                        "n_soft_queue": 0,
                    }
                )
                continue
            summary = _read_json(ud / "SUMMARY.json")
            stats = _graph_unit_stats(hp, summary if isinstance(summary, dict) else None)
            units.append({"unit_id": ud.name, **stats})
    return {
        "project_id": project_id,
        "run_id": run_id,
        "e2e_run": e2e_run,
        "model": (meta or {}).get("model") if isinstance(meta, dict) else run_id,
        "backend": (meta or {}).get("backend") if isinstance(meta, dict) else None,
        "units": units,
    }


def _graph_unit_detail(
    project_id: str, run_id: str, unit_id: str, e2e_run: str | None = None
) -> dict:
    run_id = _validate_run_id(run_id)
    unit_id = _validate_run_id(unit_id, "unit id")
    root = _workspace(project_id, e2e_run)
    ud = root / "graph" / "runs" / run_id / "units" / unit_id
    hp = _read_json(ud / "HAS-PART.json")
    if not isinstance(hp, dict):
        raise FileNotFoundError(f"{run_id}/{unit_id}")
    summary = _read_json(ud / "SUMMARY.json")
    findings = _read_json(ud / "review-findings.json")
    stats = _graph_unit_stats(hp, summary if isinstance(summary, dict) else None)
    materials = [
        {
            "id": n.get("id"),
            "source_file": n.get("source_file") or n.get("name"),
            "role": n.get("role"),
        }
        for n in (hp.get("nodes") or [])
        if n.get("type") == "Material"
    ]
    assessments = [
        {
            "id": n.get("id"),
            "name": n.get("name") or n.get("id"),
            "source_file": n.get("source_file"),
        }
        for n in (hp.get("nodes") or [])
        if n.get("type") == "Assessment"
    ]
    # Prefer Lesson nodes; fall back to lesson: edge endpoints (Dallas HAS-PART
    # often has materials/assessments + lesson edges without Lesson nodes yet).
    lessons = [
        {"id": n.get("id"), "name": n.get("name") or n.get("id")}
        for n in (hp.get("nodes") or [])
        if n.get("type") == "Lesson"
    ]
    if not lessons:
        seen: set[str] = set()
        for e in hp.get("edges") or []:
            for k in ("from", "to"):
                v = str(e.get(k) or "")
                if v.startswith("lesson:") and v not in seen:
                    seen.add(v)
                    lessons.append({"id": v, "name": v.split(":", 1)[-1]})
    return {
        "project_id": project_id,
        "run_id": run_id,
        "unit_id": unit_id,
        "stats": stats,
        "summary": summary,
        "materials": materials,
        "assessments": assessments,
        "lessons": lessons,
        "has_part": hp,
        "findings": findings,
    }


def _project_title(project_dir: Path, pid: str) -> str:
    """Human label from manifest when present; otherwise the folder id."""
    manifest = project_dir / "manifest.yaml"
    if not manifest.is_file():
        return pid
    try:
        import yaml

        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception:
        return pid
    if isinstance(data.get("project"), dict):
        name = data["project"].get("name") or data["project"].get("title")
        if isinstance(name, str) and name.strip():
            return name.strip()
    title = data.get("title") or data.get("name")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return pid


def _project_kind(pid: str, has_manifest: bool) -> str:
    """curriculum = has an ingested manifest; lab = lab-* forks; other = the rest.

    Derived from what is on disk. This used to read projects/STATUS.md, a
    hand-maintained table describing our own sample corpora — so on any machine
    but a developer's it listed nothing, and every curriculum a district
    ingested was classified "other" and disappeared from a picker that shows
    kind == "curriculum". The manifest is the honest signal: ingest writes one
    once it has organised the documents into units.
    """
    if pid.startswith("lab-"):
        return "lab"
    if has_manifest:
        return "curriculum"
    return "other"


def _latest_review_run(project: Path) -> float | None:
    """When the most recent finished audit completed, or None if never audited.

    Serves two purposes: the "is there anything to review?" signal, and the
    picker's sort key. REVIEW-READY.json is written last, which makes its mtime
    the closest thing to a completion time we have.
    """
    runs_root = project / "e2e" / "runs"
    if not runs_root.is_dir():
        return None
    stamps: list[float] = []
    for d in runs_root.iterdir():
        if not d.is_dir():
            continue
        try:
            stamps.append((d / "REVIEW-READY.json").stat().st_mtime)
        except OSError:
            continue  # unfinished run, or a file we cannot read — not reviewable
    return max(stamps) if stamps else None


def _list_projects() -> list[dict]:
    """List reviewable project dirs with picker metadata (kind / title / sort).

    Curriculum dropdown uses kind=curriculum (an ingested manifest). Lab forks
    stay loadable by id but are opt-in in the UI (kind=lab).
    """
    out: list[dict] = []
    if not PROJECTS.is_dir():
        return out
    for child in PROJECTS.iterdir():
        # Skip files (README.md and friends) and private/underscore shelves.
        if not child.is_dir() or child.name.startswith("_"):
            continue
        pid = child.name
        has_manifest = (child / "manifest.yaml").is_file()
        kind = _project_kind(pid, has_manifest)
        title = _project_title(child, pid)
        last_audit = _latest_review_run(child)
        out.append(
            {
                "id": pid,
                "title": title,
                "kind": kind,
                "has_output": (child / "output").is_dir(),
                "has_stats": (child / "output" / "aggregate-stats.json").is_file(),
                "has_unit_rung": (child / "layer_unit" / "UNIT-RUNG.md").is_file(),
                # Has ingest organised the documents into units yet? Distinguishes
                # "set up, ready to audit" from "documents dropped in, nothing read".
                "has_manifest": has_manifest,
                # A district calendar is optional input, not a prerequisite:
                # with one, rollup dates the pacing plan; without one it places
                # units sequentially and everything else is identical. Reported
                # so the UI can say which mode a curriculum is in and offer to
                # upgrade it, rather than leaving that invisible.
                "has_calendar": (child / "school-calendar.yaml").is_file(),
                # Does the review console have anything to show for this
                # project? The console only renders REVIEW-READY e2e runs, so
                # without this the picker cannot avoid landing a first-time
                # user on a curriculum that renders an empty page.
                "has_review_run": last_audit is not None,
                "last_audit": last_audit,
            }
        )
    # Most recently audited first: the curriculum somebody last worked on is the
    # one they most likely want back. Never-audited trees sort to the bottom
    # alphabetically.
    out.sort(
        key=lambda p: (
            -(p["last_audit"] or 0.0),
            (p["title"] or p["id"]).lower(),
            p["id"],
        )
    )
    return out


def _project_dir(pid: str) -> Path:
    """Resolve + validate a project directory strictly under projects/. Guards the
    id itself against traversal (e.g. '../../etc')."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", pid or ""):
        raise ValueError("invalid project id")
    p = (PROJECTS / pid).resolve()
    if p.parent != PROJECTS.resolve() or not p.is_dir():
        raise FileNotFoundError(pid)
    return p


def _safe_file(pid: str, rel: str, e2e_run: str | None = None) -> Path:
    """Resolve REL inside the review workspace, rejecting any escape.

    When e2e_run is set, REL is relative to e2e/runs/<id>/ (same plate paths as
    the live tree: output/DASHBOARD.md, layer0/REPORT.md, …). Always confine the
    resolved path under the live project dir so e2e cannot escape projects/<id>.
    """
    project = _project_dir(pid)
    base = _workspace(pid, e2e_run)
    # Reject absolute / empty / traversal in the relative path string itself.
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PermissionError(rel)
    target = (base / rel).resolve()
    if project not in target.parents and target != project:
        raise PermissionError(rel)
    if not target.is_file():
        raise FileNotFoundError(rel)
    return target


def _safe_static(url_path: str) -> Path | None:
    """Resolve a request path inside ui/dist, or None when there is nothing to send.

    Single-origin production mode: the desktop window loads this server
    directly, so it has to serve the built app as well as /api — which removes
    the Vite proxy, the second port, and CORS from the shipped product.

    Two rules worth knowing:
      * A path that escapes dist is a hard PermissionError, never a fallback.
      * Only navigation paths (no file extension) fall back to index.html. A
        missing *asset* must 404 instead of quietly returning HTML, which
        otherwise shows up as the baffling "Unexpected token '<'" script error.
    """
    if not DIST.is_dir():
        return None
    dist = DIST.resolve()
    rel = url_path.lstrip("/") or "index.html"
    if ".." in Path(rel).parts:
        raise PermissionError(rel)
    target = (dist / rel).resolve()
    if target != dist and dist not in target.parents:
        raise PermissionError(rel)
    if target.is_file():
        return target
    if Path(rel).suffix:
        return None
    index = dist / "index.html"
    return index if index.is_file() else None


def _exists(pid_dir: Path, rel: str) -> bool:
    return (pid_dir / rel).is_file()


# Per-document notes on presence steps are field tallies ("0/2 fields present"),
# which are meaningless as a column header. Structural steps (inventory, pairing,
# emit) carry a real description, so those are worth keeping as a fallback label.
_FIELD_TALLY_NOTE = re.compile(r"^\d+/\d+ fields present$")


def _checklist_labels(checklist_rel: str | None) -> dict[str, str]:
    """Step -> human label from a workflow checklist, e.g. 'B3 Answer key signal'.

    Only covers the presence steps a checklist defines; structural steps fall back
    to their finding note. Returns {} when the checklist is missing or unreadable
    so an older run without one still renders.
    """
    if not checklist_rel:
        return {}
    spec = (ROOT / checklist_rel).resolve()
    if ROOT not in spec.parents or not spec.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - a bad checklist must not break the panel
        return {}
    labels: dict[str, str] = {}
    for section in (data.get("sections") or {}).values():
        step, label = section.get("step"), section.get("label")
        if step and label:
            # Labels are stored as "B3 Answer key signal"; drop the redundant id.
            labels[step] = str(label).removeprefix(f"{step} ").strip()
    return labels


def _path_step_rollup(inventory: list, checklist_rel: str | None = None) -> list[dict]:
    """Collapse a findings inventory into per-step status counts.

    Each inventory row is one document carrying a `<LETTER><N>` key per checklist
    step (e.g. B3) whose value is `{"status": ..., "note": ...}`. Reviewers care
    about the shape of the column, not the individual cells, so count statuses per
    step. Steps come back in checklist order.
    """
    counts: dict[str, Counter] = {}
    notes: dict[str, str] = {}
    for row in inventory:
        if not isinstance(row, dict):
            continue
        for key, val in row.items():
            if not (isinstance(val, dict) and "status" in val):
                continue
            # Step keys look like B3 / G12 — a lens letter plus a number.
            if not (len(key) >= 2 and key[0].isalpha() and key[1:].isdigit()):
                continue
            counts.setdefault(key, Counter())[val.get("status") or "UNKNOWN"] += 1
            note = str(val.get("note") or "")
            if key not in notes and note and not _FIELD_TALLY_NOTE.match(note):
                notes[key] = note

    labels = _checklist_labels(checklist_rel)
    return [
        {
            "step": sid,
            "label": labels.get(sid) or notes.get(sid, ""),
            "total": sum(counts[sid].values()),
            "counts": {
                s: counts[sid].get(s, 0) for s in STEP_STATUSES if counts[sid].get(s)
            },
            # The headline number: how many documents lack this element entirely.
            "missing": counts[sid].get("MISSING", 0),
        }
        for sid in sorted(counts, key=lambda k: (k[0], int(k[1:])))
    ]


def _paths_summary(pid: str, e2e_run: str | None = None) -> dict:
    """A-H review lenses for one workspace: routing, findings status, step rollups.

    Reads only artifacts already on disk (layer0/route-map.json and each
    path_<letter>/findings.json), so it works for a live project tree and for a
    frozen e2e/runs/<id>/ snapshot alike. Paths with no routed documents are
    reported rather than hidden — a `skipped` path is a meaningful result.
    """
    base = _workspace(pid, e2e_run)
    route_map = _read_json(base / "layer0" / "route-map.json") or {}
    routes = route_map.get("routes") or []
    lens_names = route_map.get("lenses") or {}

    routed: dict[str, list[dict]] = {L: [] for L in PATH_LETTERS}
    reasons: dict[str, Counter] = {L: Counter() for L in PATH_LETTERS}
    for r in routes:
        letter = (r.get("path") or "").upper()
        if letter not in routed:
            continue
        routed[letter].append(
            {
                "doc_id": r.get("doc_id"),
                "doc_type": r.get("doc_type"),
                "source_file": r.get("source_file"),
                "confidence": r.get("confidence"),
                "reason": r.get("reason"),
                "element_count": r.get("element_count"),
            }
        )
        # Group reasons by their prefix ("filename prior", "graph Assessment link")
        # so the UI can show *why* the router chose this lens without a long tail.
        reasons[letter][str(r.get("reason") or "unknown").split(" \u2192")[0]] += 1

    paths = []
    for letter in PATH_LETTERS:
        label, workflow_id = PATH_LENSES[letter]
        findings = _read_json(base / f"path_{letter.lower()}" / "findings.json")
        inventory = (findings or {}).get("inventory") or []
        steps = _path_step_rollup(inventory, (findings or {}).get("checklist"))
        docs = (findings or {}).get("doc_ids") or []
        # Every path findings file carries status (ok|skipped). Absent means
        # the lens has not run in this workspace yet.
        status = (findings or {}).get("status") if findings is not None else None
        paths.append(
            {
                "letter": letter,
                "label": lens_names.get(workflow_id) or label,
                "workflow_id": workflow_id,
                "has_findings": findings is not None,
                "status": status or "absent",
                "routed": len(routed[letter]),
                "n_docs": len(docs),
                "findings_path": f"path_{letter.lower()}/findings.json",
                "steps": steps,
                "missing_total": sum(s["missing"] for s in steps),
                "top_reasons": [
                    {"reason": k, "count": v} for k, v in reasons[letter].most_common(4)
                ],
                "docs": routed[letter],
                "inventory": inventory,
            }
        )

    return {
        "project_id": pid,
        "e2e_run": e2e_run,
        "generated_at": route_map.get("generated_at"),
        "total_routed": len(routes),
        "unrouted": len(route_map.get("unrouted_ledger_doc_ids") or []),
        "step_statuses": STEP_STATUSES,
        "paths": paths,
    }



def _outputs_tree(pid: str, e2e_run: str | None = None) -> dict:
    base = _workspace(pid, e2e_run)
    plates = [
        {"label": lbl, "path": rel} for lbl, rel in PLATE_FILES if _exists(base, rel)
    ]
    layers = [
        {"label": lbl, "path": rel} for lbl, rel in LAYER_FILES if _exists(base, rel)
    ]
    pdfs = [
        {"label": lbl, "path": rel} for lbl, rel in PDF_FILES if _exists(base, rel)
    ]

    # Unit titles from the stats rollup when available, else the folder name.
    titles: dict[str, str] = {}
    stats_path = base / "output" / "aggregate-stats.json"
    if stats_path.is_file():
        try:
            stats = json.loads(stats_path.read_text())
            for u in stats.get("unit_rollup", []) or []:
                titles[u.get("unit_id")] = u.get("title") or u.get("unit_id")
        except (json.JSONDecodeError, OSError):
            pass

    units: list[dict] = []
    out_dir = base / "output"
    teachers_dir = out_dir / "teachers"
    # Unit ids from output/<unit>/ reports and/or output/teachers/<unit>/
    # packets. E2E mirrors often ship teachers without per-unit REPORT.md.
    unit_ids: set[str] = set()
    if out_dir.is_dir():
        for unit_dir in out_dir.iterdir():
            if unit_dir.is_dir() and unit_dir.name not in ("teachers", "raw"):
                unit_ids.add(unit_dir.name)
    if teachers_dir.is_dir():
        for teacher_dir in teachers_dir.iterdir():
            if teacher_dir.is_dir():
                unit_ids.add(teacher_dir.name)

    for unit_id in sorted(unit_ids):
        unit_dir = out_dir / unit_id
        files = [
            {"label": lbl, "path": f"output/{unit_id}/{fn}", "type": typ}
            for lbl, fn, typ in UNIT_FILE_SPECS
            if (unit_dir / fn).is_file()
        ]
        teacher_files = []
        teacher_dir = teachers_dir / unit_id
        if teacher_dir.is_dir():
            for tf in sorted(teacher_dir.iterdir()):
                # Include .html so usefulness-test one-pagers can open in-browser
                # with their own contrast styles (not forced through the MD viewer).
                if tf.is_file() and tf.suffix in (".md", ".pdf", ".json", ".html"):
                    teacher_files.append(
                        {
                            "label": tf.name,
                            "path": f"output/teachers/{unit_id}/{tf.name}",
                            "type": tf.suffix.lstrip("."),
                        }
                    )
        if not files and not teacher_files:
            continue
        units.append(
            {
                "unit_id": unit_id,
                "title": titles.get(unit_id, unit_id),
                "files": files,
                "teacher_files": teacher_files,
            }
        )
    return {
        "plates": plates,
        "layers": layers,
        "pdfs": pdfs,
        "units": units,
        "e2e_run": e2e_run,
    }


def _config_summary() -> dict:
    """Read-only, curated view of config.yaml — never the raw secrets-ish blob."""
    if not CONFIG.is_file():
        return {"error": "config.yaml not found"}
    try:
        import yaml  # PyYAML ships with the Loom engine deps.

        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - degrade to a note, never 500 the UI
        return {"error": f"config.yaml unreadable: {e}"}
    models = cfg.get("models", {}) or {}
    return {
        "models": {
            "analyst_url": models.get("analyst_url"),
            "verifier_url": models.get("verifier_url"),
            "analyst_model": models.get("analyst_model"),
        },
        "keys": sorted(cfg.keys()),
    }


def _packet_types() -> dict:
    """The declarable packet-type registry (id/label/short/description/components),
    read straight from workflows/packet_types.yaml. Powers the start-point selector.
    Degrades to an error note rather than 500-ing the whole UI."""
    if not PACKET_TYPES_SPEC.is_file():
        return {"error": "packet_types.yaml not found", "default": None, "types": []}
    try:
        import yaml

        data = yaml.safe_load(PACKET_TYPES_SPEC.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return {"error": f"packet_types.yaml unreadable: {e}", "default": None, "types": []}
    types = []
    for tid, spec in (data.get("types") or {}).items():
        types.append(
            {
                "id": tid,
                "label": spec.get("label", tid),
                "short": spec.get("short", ""),
                "description": (spec.get("description") or "").strip(),
                "expected_components": [
                    c.get("label") for c in (spec.get("components") or [])
                ],
            }
        )
    return {"default": data.get("default"), "types": types}


def _set_packet_type(pid: str, type_id: str) -> dict:
    """DECLARE a project's packet type: validate the id, write `packet_type:` into
    the manifest (preserving comments via a targeted line edit, not a YAML rewrite),
    then regenerate the deterministic unit rung so the heatmap reflects it at once."""
    base = _project_dir(pid)
    valid = {t["id"] for t in _packet_types().get("types", [])}
    if type_id not in valid:
        raise ValueError(f"unknown packet_type {type_id!r} (have {sorted(valid)})")

    manifest = base / "manifest.yaml"
    if not manifest.is_file():
        raise FileNotFoundError("manifest.yaml")
    lines = manifest.read_text(encoding="utf-8").splitlines()

    # Replace an existing top-level `packet_type:` line if present, else insert one
    # after `sources_dir:` (or at the top). A line edit keeps the file's comments.
    key_re = re.compile(r"^packet_type:\s*.*$")
    new_line = f"packet_type: {type_id}"
    for i, line in enumerate(lines):
        if key_re.match(line):
            lines[i] = new_line
            break
    else:
        insert_at = next(
            (i + 1 for i, ln in enumerate(lines) if ln.startswith("sources_dir:")), 0
        )
        lines.insert(insert_at, new_line)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Regenerate the unit rung (fast, deterministic, offline) so completeness +
    # bands update immediately without a full re-run.
    proc = subprocess.run(
        ["python3", str(UNIT_RUNG_SCRIPT), "--project", pid],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "packet_type": type_id,
        "regenerated": proc.returncode == 0,
        "detail": (proc.stdout + proc.stderr).strip()[-500:],
    }


def _start_run(pid: str, flags: list[str]) -> str:
    """Run the pipeline for <pid>, streaming combined output to a per-run log.

    Returns a runId the client polls. Flags are whitelisted to a safe few.
    Invokes run_project.py with sys.executable -- the interpreter already
    running this server -- so an audit needs no `bash` and no `python3` on
    PATH, and starts the same way on all three platforms.
    """
    _project_dir(pid)  # validate before spawning
    allowed = {"--ingest", "--force", "--only", "--skip-drive-push"}
    clean: list[str] = []
    for f in flags or []:
        # Allow the whitelisted flags and bare values following --only.
        if f in allowed or (clean and clean[-1] == "--only"):
            clean.append(f)
    run_id = uuid.uuid4().hex[:12]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUNS_DIR / f"{run_id}.log"
    log_fh = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - closed in waiter
    proc = subprocess.Popen(
        [sys.executable, str(RUN_PROJECT), "--project", pid, *clean],
        cwd=str(ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
        # The pipeline writes curriculum text -- em dashes, curly quotes,
        # accented names -- and Windows still defaults to cp1252, which turns
        # those into mojibake or a hard UnicodeEncodeError mid-run.
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    with _RUNS_LOCK:
        _RUNS[run_id] = {
            "pid": pid,
            "proc": proc,
            "log_path": str(log_path),
            "status": "running",
            "exit_code": None,
            "started": time.time(),
        }

    def _wait() -> None:
        code = proc.wait()
        log_fh.close()
        with _RUNS_LOCK:
            _RUNS[run_id]["status"] = "done" if code == 0 else "error"
            _RUNS[run_id]["exit_code"] = code

    threading.Thread(target=_wait, daemon=True).start()
    return run_id


_WEASYPRINT_OK: bool | None = None


def _weasyprint_ok() -> bool:
    """Can WeasyPrint load its native libraries (Pango/GObject)?

    Cached, because the import is slow and prints a wall of warnings when it
    fails, and because native libraries cannot appear without a restart of this
    process anyway. `find_spec` is not enough: the Python package installs
    cleanly and only fails at import time when the C libraries are absent,
    which is the usual situation on Windows.
    """
    global _WEASYPRINT_OK
    if _WEASYPRINT_OK is None:
        try:
            import weasyprint  # noqa: F401

            _WEASYPRINT_OK = True
        except Exception:
            _WEASYPRINT_OK = False
    return _WEASYPRINT_OK


def _missing_packages() -> list[str]:
    """Required third-party imports that are not available."""
    out: list[str] = []
    for mod, dist in (("yaml", "PyYAML"), ("requests", "requests"), ("jinja2", "Jinja2")):
        if importlib.util.find_spec(mod) is None:
            out.append(dist)
    return out


def _model_reachable() -> tuple[bool, str]:
    """Is the configured analyst endpoint answering? (ok, detail).

    Short timeout on purpose: this runs on a settings screen, and a model that
    takes longer than a couple of seconds to say hello is not going to make an
    audit anyone enjoys. Any HTTP answer counts -- a 404 on /health still means
    something is listening, which is what we are actually asking.
    """
    try:
        import yaml  # Imported here: its absence is itself one of the checks.

        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"config.yaml could not be read: {e}"
    url = ((cfg.get("models") or {}).get("analyst_url") or "").strip()
    if not url:
        return False, "no analyst_url is set in config.yaml"
    base = url.split("/v1/")[0].rstrip("/")
    for probe in (f"{base}/health", f"{base}/healthz", base):
        try:
            with urllib.request.urlopen(probe, timeout=2.0):
                return True, url
        except urllib.error.HTTPError:
            return True, url  # answering, just not with 200
        except Exception:
            continue
    return False, f"nothing is answering at {base}"


def _requirements() -> list[dict]:
    """Everything an audit needs, what it is for, and how to install it.

    Three severities, because lumping them together is what produced the
    unhelpful "missing bash and python3":

      required   the audit cannot run at all
      pdf        the audit cannot read PDF documents (it crashes on the first
                 one: doc_extract raises RuntimeError and extract_with_meta
                 only catches ValueError). Fine if the sources are Word or text
      optional   an output is unavailable, everything else works

    `fix` is keyed by sys.platform so each machine is told what to type on it,
    rather than being shown three sets of instructions to choose between.
    """
    pip = f'"{sys.executable}" -m pip install -r requirements.txt'
    packages = _missing_packages()
    model_ok, model_detail = _model_reachable()

    return [
        {
            "id": "program",
            "label": "Loom’s pipeline",
            "why": "Reads the documents and produces the audit.",
            "severity": "required",
            "ok": RUN_PROJECT.is_file(),
            "detail": str(RUN_PROJECT),
            "fix": {
                "all": "This part of Loom is missing from the installation. "
                "Reinstalling should restore it.",
            },
        },
        {
            "id": "packages",
            "label": "Python support libraries",
            "why": "Reading calendars and manifests, and talking to the model.",
            "severity": "required",
            "ok": not packages,
            "detail": ", ".join(packages) if packages else "all present",
            "fix": {"all": pip},
        },
        {
            "id": "model",
            "label": "A language model",
            "why": "Does the actual reading. Loom sends it your documents "
            "and it answers with what it found.",
            "severity": "required",
            "ok": model_ok,
            "detail": model_detail,
            "fix": {
                "all": "Start your local model server, or point Loom at one in "
                "config.yaml under models.analyst_url.",
            },
        },
        {
            "id": "poppler",
            "label": "PDF text extraction (poppler)",
            "why": "Gets the text out of PDF documents. Most curriculum "
            "arrives as PDF, and Loom stops on the first one without it.",
            "severity": "pdf",
            "ok": bool(shutil.which("pdftotext")),
            "detail": shutil.which("pdftotext") or "pdftotext is not on PATH",
            "fix": {
                "win32": "choco install poppler    (or: scoop install poppler)\n"
                "Or download a build from\n"
                "https://github.com/oschwartz10612/poppler-windows/releases\n"
                "and add its bin folder to PATH.",
                "darwin": "brew install poppler",
                "linux": "sudo apt install poppler-utils      (Debian/Ubuntu)\n"
                "sudo dnf install poppler-utils      (Fedora/RHEL)",
            },
        },
        {
            "id": "weasyprint",
            "label": "PDF report output (WeasyPrint)",
            "why": "Turns the finished reports into PDFs. Without it every "
            "report is still written, just as Markdown instead of PDF.",
            "severity": "optional",
            "ok": _weasyprint_ok(),
            "detail": "ready" if _weasyprint_ok() else "native libraries not found",
            "fix": {
                "win32": "Needs the GTK/Pango libraries. Follow\n"
                "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html",
                "darwin": "brew install pango gdk-pixbuf libffi",
                "linux": "sudo apt install libpango-1.0-0 libpangoft2-1.0-0",
            },
        },
        {
            "id": "antiword",
            "label": "Legacy .doc support (antiword)",
            "why": "Only needed for old Word .doc files. .docx works without it.",
            "severity": "optional",
            "ok": bool(shutil.which("antiword")),
            "detail": shutil.which("antiword") or "not installed",
            "fix": {
                "win32": "Rarely needed. Re-saving the files as .docx avoids it.",
                "darwin": "brew install antiword",
                "linux": "sudo apt install antiword",
            },
        },
    ]


def _run_preflight() -> dict:
    """Can this machine run an audit, and if not, what would make it able to?

    This used to check for `bash` and `python3` and report their absence, which
    was both unhelpful and wrong: those were needed only because the server
    shelled out through a one-line shell wrapper. It now reports the real
    requirements, each with a platform-appropriate fix, so the UI can walk
    somebody through setup instead of naming a missing command.
    """
    checks = _requirements()
    blocking = [c for c in checks if c["severity"] == "required" and not c["ok"]]
    pdf_blocked = [c for c in checks if c["severity"] == "pdf" and not c["ok"]]
    return {
        "can_run": not blocking,
        "can_read_pdf": not pdf_blocked,
        # Kept for older clients: a flat list of what is not satisfied.
        "missing": [c["label"] for c in checks if not c["ok"]],
        "platform": sys.platform,
        "checks": checks,
    }


def _storage_summary() -> dict:
    """Where this copy keeps curricula, config and logs.

    Worth surfacing in the UI rather than hiding: "where did my work go?" is a
    question people genuinely need answered, and an install sharing its folder
    with the program (`legacy_in_repo`) is a developer setup, not something a
    district should end up in silently.
    """
    return {
        "data_root": str(DATA_ROOT),
        "install_root": str(ROOT),
        "projects_root": str(PROJECTS),
        "legacy_in_repo": is_legacy_in_repo(),
        # An explicit LOOM_HOME outranks every default, so say when it is set —
        # otherwise a pinned data directory looks indistinguishable from the
        # per-OS default and is very confusing to debug.
        "pinned_by_env": bool((os.environ.get("LOOM_HOME") or "").strip()),
        "config_present": CONFIG.is_file(),
    }


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw or b"{}") or {}
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON body: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _create_status() -> dict:
    """Health for the create chapter's Cursor draft path (never returns the key)."""
    from create.auth import key_source

    sdk_ok = False
    sdk_error = None
    try:
        import cursor_sdk  # noqa: F401

        sdk_ok = True
    except ImportError as e:
        sdk_error = str(e)
    src = key_source()
    return {
        "cursor_key_source": src,
        "cursor_key_present": src != "none",
        "cursor_sdk": sdk_ok,
        "cursor_sdk_error": sdk_error,
        "default_model": "composer-2.5",
        "note": "Draft assist uses Pi ~/.pi/agent/auth.json or CURSOR_API_KEY for now.",
    }


def _run_status(run_id: str, tail_bytes: int = 16000) -> dict | None:
    with _RUNS_LOCK:
        rec = _RUNS.get(run_id)
        if not rec:
            return None
        status, code, log_path = rec["status"], rec["exit_code"], rec["log_path"]
    log_text = ""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            log_text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        pass
    return {"runId": run_id, "status": status, "exitCode": code, "log": log_text}


class Handler(BaseHTTPRequestHandler):
    server_version = "LoomReview/1.0"

    # --- response helpers ---------------------------------------------------
    def _cors(self) -> None:
        # Local-only tool: Vite dev server (5173) talks to this API (8770).
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, path: Path) -> None:
        ctype, _ = mimetypes.guess_type(str(path))
        # Markdown/JSON go as UTF-8 text so the browser fetch() gets a string.
        if path.suffix in (".md", ".json", ".yaml", ".yml", ".txt"):
            ctype = "text/plain; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self._cors()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args) -> None:  # quieter console
        return

    # --- routing ------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        qs = parse_qs(parsed.query)
        # Optional workspace: e2e_run=<id> scopes outputs/file/stats/graph to
        # projects/<id>/e2e/runs/<e2e_run>/ (full-pipeline review snapshot).
        e2e_raw = (qs.get("e2e_run") or [""])[0].strip()
        e2e_run = e2e_raw or None
        try:
            if parts == ["api", "projects"]:
                return self._json(_list_projects())
            if parts == ["api", "config"]:
                return self._json(_config_summary())
            if parts == ["api", "can-run"]:
                return self._json(_run_preflight())
            if parts == ["api", "storage"]:
                return self._json(_storage_summary())
            if parts == ["api", "packet-types"]:
                return self._json(_packet_types())
            if parts == ["api", "create", "status"]:
                return self._json(_create_status())
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "outputs":
                return self._json(_outputs_tree(parts[2], e2e_run))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "paths":
                return self._json(_paths_summary(parts[2], e2e_run))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "stats":
                return self._bytes(
                    _safe_file(parts[2], "output/aggregate-stats.json", e2e_run)
                )
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["e2e", "runs"]
            ):
                return self._json(_list_e2e_runs(parts[2]))
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["graph", "runs"]
            ):
                return self._json(_list_graph_runs(parts[2], e2e_run))
            if (
                len(parts) == 7
                and parts[:2] == ["api", "projects"]
                and parts[3] == "graph"
                and parts[4] == "runs"
                and parts[6] == "overview"
            ):
                return self._json(_graph_overview(parts[2], parts[5], e2e_run))
            if (
                len(parts) == 8
                and parts[:2] == ["api", "projects"]
                and parts[3] == "graph"
                and parts[4] == "runs"
                and parts[6] == "units"
            ):
                return self._json(
                    _graph_unit_detail(parts[2], parts[5], parts[7], e2e_run)
                )
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["create", "matrix"]
            ):
                from create.tree import list_matrix

                pid = parts[2]
                return self._json(list_matrix(pid, _project_dir(pid)))
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["create", "tree"]
            ):
                from create.tree import list_roles

                pid = parts[2]
                return self._json(list_roles(pid, _project_dir(pid)))
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["create", "tree"]
            ):
                from create.tree import list_role_units

                pid, role = parts[2], parts[5]
                if not re.fullmatch(r"[A-Za-z0-9._-]+", role or ""):
                    raise ValueError("invalid role")
                return self._json(list_role_units(pid, _project_dir(pid), role))
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["create", "units"]
            ):
                from create.tree import list_units

                pid = parts[2]
                return self._json(list_units(pid, _project_dir(pid)))
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["create", "units"]
            ):
                from create.tree import list_unit_slots

                pid, unit_id = parts[2], parts[5]
                if not re.fullmatch(r"[A-Za-z0-9._-]+", unit_id or ""):
                    raise ValueError("invalid unit id")
                return self._json(list_unit_slots(pid, _project_dir(pid), unit_id))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "gaps":
                from create.gaps import list_gaps

                pid = parts[2]
                gaps = list_gaps(pid, _project_dir(pid))
                return self._json({"project_id": pid, "count": len(gaps), "gaps": gaps})
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3] == "gaps"
                and parts[5] in ("brief", "draft")
            ):
                from create.brief import read_brief
                from create.draft import read_draft
                from create.gaps import get_gap

                pid, gid, kind = parts[2], parts[4], parts[5]
                base = _project_dir(pid)
                if not get_gap(pid, base, gid):
                    return self._json({"error": f"unknown gap {gid}"}, 404)
                text = read_brief(base, gid) if kind == "brief" else read_draft(base, gid)
                if text is None:
                    return self._json({"error": f"no {kind} yet"}, 404)
                return self._json({"gap_id": gid, "kind": kind, "text": text})
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "file":
                rel = (qs.get("path") or [""])[0]
                return self._bytes(_safe_file(parts[2], rel, e2e_run))
            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                res = _run_status(parts[2])
                return self._json(res) if res else self._json({"error": "no such run"}, 404)
            # Anything that is not an /api route is a request for the app
            # itself. Only reachable in production mode, where ui/dist exists.
            if not parts or parts[0] != "api":
                static = _safe_static(parsed.path)
                if static is not None:
                    return self._bytes(static)
                if not DIST.is_dir():
                    return self._json(
                        {
                            "error": "no ui/dist bundle: this server is API-only. "
                            "Run `npm run ui:build`, or use the Vite dev server."
                        },
                        501,
                    )
            return self._json({"error": "not found"}, 404)
        except FileNotFoundError as e:
            return self._json({"error": f"not found: {e}"}, 404)
        except (PermissionError, ValueError) as e:
            return self._json({"error": f"forbidden: {e}"}, 403)
        except ModuleNotFoundError as e:
            # The `create` chapter is gitignored and absent on most machines.
            # 501 says "this build does not have that feature", which the UI can
            # explain honestly; a 500 would read as "Loom is broken".
            return self._json({"error": f"not installed: {e.name}"}, 501)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "run":
                body = _read_json_body(self)
                run_id = _start_run(parts[2], body.get("flags", []))
                return self._json({"runId": run_id})
            if (
                len(parts) == 4
                and parts[:2] == ["api", "projects"]
                and parts[3] == "packet-type"
            ):
                body = _read_json_body(self)
                type_id = body.get("packet_type", "")
                return self._json(_set_packet_type(parts[2], type_id))
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3] == "gaps"
                and parts[5] == "decision"
            ):
                from create.decisions import save_decision
                from create.gaps import get_gap

                pid, gid = parts[2], parts[4]
                base = _project_dir(pid)
                if not get_gap(pid, base, gid):
                    return self._json({"error": f"unknown gap {gid}"}, 404)
                body = _read_json_body(self)
                decision = body.get("decision", None)
                if decision == "":
                    decision = None
                row = save_decision(
                    base,
                    gid,
                    decision,
                    note=str(body.get("note") or ""),
                    actor=str(body.get("actor") or "operator"),
                )
                return self._json(row)
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3] == "gaps"
                and parts[5] == "brief"
            ):
                from create.brief import read_brief, save_brief_text, write_brief
                from create.gaps import get_gap

                pid, gid = parts[2], parts[4]
                base = _project_dir(pid)
                gap = get_gap(pid, base, gid)
                if not gap:
                    return self._json({"error": f"unknown gap {gid}"}, 404)
                body = _read_json_body(self)
                # { "text": "..." } saves edits; omit text (or generate:true) to rebuild.
                if "text" in body and body.get("generate") is not True:
                    path = save_brief_text(base, gid, str(body.get("text") or ""))
                    return self._json(
                        {
                            "gap_id": gid,
                            "path": str(path.relative_to(base)),
                            "text": read_brief(base, gid),
                            "saved": True,
                        }
                    )
                path = write_brief(base, gap)
                return self._json(
                    {
                        "gap_id": gid,
                        "path": str(path.relative_to(base)),
                        "text": read_brief(base, gid),
                    }
                )
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3] == "gaps"
                and parts[5] == "draft"
            ):
                from create.draft import draft_gap, save_draft_text
                from create.gaps import get_gap

                pid, gid = parts[2], parts[4]
                base = _project_dir(pid)
                gap = get_gap(pid, base, gid)
                if not gap:
                    return self._json({"error": f"unknown gap {gid}"}, 404)
                body = _read_json_body(self)
                # { "text": "..." } saves operator edits; otherwise generate.
                if "text" in body and body.get("generate") is not True:
                    path = save_draft_text(base, gid, str(body.get("text") or ""))
                    return self._json(
                        {
                            "gap_id": gid,
                            "path": str(path.relative_to(base)),
                            "saved": True,
                        }
                    )
                result = draft_gap(
                    base,
                    gap,
                    context=str(body.get("context") or ""),
                    model=str(body.get("model") or "composer-2.5"),
                )
                return self._json(result)
            return self._json({"error": "not found"}, 404)
        except (PermissionError, ValueError) as e:
            return self._json({"error": f"forbidden: {e}"}, 403)
        except ModuleNotFoundError as e:
            return self._json({"error": f"not installed: {e.name}"}, 501)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)


def main() -> int:
    ap = argparse.ArgumentParser(description="Loom Run Review local API")
    ap.add_argument(
        "--port",
        type=int,
        default=8770,
        help="0 lets the OS pick a free port; the chosen one is printed below",
    )
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    # Report the *bound* port, not the requested one: with --port 0 the OS
    # assigns it, and the caller has no other way to learn where we ended up.
    # flush so a launcher reading our output is not blocked by stdio buffering.
    port = httpd.server_address[1]
    # Create the data skeleton at startup rather than on first write, so a fresh
    # install has somewhere to put things and the path shown below always exists.
    ensure_data_dirs()
    print(f"[loom-review] API on http://{args.host}:{port}  (install: {ROOT})", flush=True)
    print(f"[loom-review] data root: {DATA_ROOT}", flush=True)
    if DIST.is_dir():
        print(f"[loom-review] serving app from {DIST}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[loom-review] bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
