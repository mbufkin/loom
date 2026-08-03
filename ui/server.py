#!/usr/bin/env python3
"""
ui/server.py — Loom Run Review, local-only API.

A deliberately tiny, dependency-light HTTP server that lets a local browser
review the artifacts a completed Loom run wrote under projects/<id>/. It does
NOT invent curriculum in the auditor path; create-after-audit endpoints live
alongside and write only under projects/<id>/create/. Local-only by design:
no auth, binds to 127.0.0.1, and every file read is confined to the project dir.

Endpoints (all under /api):
  GET  /api/projects                      -> [{id, tier, has_output, ...}]
  GET  /api/projects/{id}/outputs         -> grouped tree of reviewable files
  GET  /api/projects/{id}/file?path=REL   -> raw bytes of one file (guarded)
  GET  /api/projects/{id}/stats           -> output/aggregate-stats.json
  GET  /api/projects/{id}/graph/runs      -> model graph runs under graph/runs/*
  GET  /api/projects/{id}/graph/runs/{run_id}/overview -> per-unit HAS-PART rollup
  GET  /api/projects/{id}/graph/runs/{run_id}/units/{unit_id} -> HAS-PART + SUMMARY
  POST /api/projects/{id}/run             -> {runId}  (spawns ./run-audit)
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
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Repo root = parent of this ui/ directory. Everything is resolved against it.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROJECTS = ROOT / "projects"
RUN_AUDIT = ROOT / "run-audit"
CONFIG = ROOT / "config.yaml"
RUNS_DIR = ROOT / "ui" / ".runs"  # per-run log files (gitignored)
PACKET_TYPES_SPEC = ROOT / "workflows" / "packet_types.yaml"
UNIT_RUNG_SCRIPT = ROOT / "unit_rung.py"

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
    ("Artifact rung — Paths B/C", "layer_artifact/ARTIFACT-RUNG.md"),
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


def _list_graph_runs(project_id: str) -> dict:
    """List model-namespaced graph runs for the curriculum picker."""
    from graph_run_lib import read_active_run

    root = _project_dir(project_id)
    runs_root = root / "graph" / "runs"
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
    return {"project_id": project_id, "active": active, "runs": runs}


def _graph_overview(project_id: str, run_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id or ""):
        raise ValueError("invalid run id")
    root = _project_dir(project_id)
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
        "model": (meta or {}).get("model") if isinstance(meta, dict) else run_id,
        "backend": (meta or {}).get("backend") if isinstance(meta, dict) else None,
        "units": units,
    }


def _graph_unit_detail(project_id: str, run_id: str, unit_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id or ""):
        raise ValueError("invalid run id")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", unit_id or ""):
        raise ValueError("invalid unit id")
    root = _project_dir(project_id)
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


def _status_tiers() -> dict[str, str]:
    """Parse projects/STATUS.md's markdown table into {project_id: tier}. Best-effort:
    the review site still works if STATUS.md is missing or reformatted."""
    tiers: dict[str, str] = {}
    status = PROJECTS / "STATUS.md"
    if not status.is_file():
        return tiers
    # Rows look like: | `dallas-career-2026` | Active | Yes | Yes | ... |
    row = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*\*{0,2}([^*|]+?)\*{0,2}\s*\|")
    for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
        m = row.match(line.strip())
        if m:
            tiers[m.group(1).strip()] = m.group(2).strip()
    return tiers


def _list_projects() -> list[dict]:
    tiers = _status_tiers()
    out: list[dict] = []
    if not PROJECTS.is_dir():
        return out
    for child in sorted(PROJECTS.iterdir()):
        # Skip files (STATUS.md, README.md) and private/underscore shelves.
        if not child.is_dir() or child.name.startswith("_"):
            continue
        pid = child.name
        out.append(
            {
                "id": pid,
                "tier": tiers.get(pid, "Unknown"),
                "has_output": (child / "output").is_dir(),
                "has_stats": (child / "output" / "aggregate-stats.json").is_file(),
                "has_unit_rung": (child / "layer_unit" / "UNIT-RUNG.md").is_file(),
            }
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


def _safe_file(pid: str, rel: str) -> Path:
    """Resolve REL inside the project dir, rejecting any escape. This is the single
    choke point for every file read the browser can request."""
    base = _project_dir(pid)
    target = (base / rel).resolve()
    if base not in target.parents and target != base:
        raise PermissionError(rel)
    if not target.is_file():
        raise FileNotFoundError(rel)
    return target


def _exists(pid_dir: Path, rel: str) -> bool:
    return (pid_dir / rel).is_file()


def _outputs_tree(pid: str) -> dict:
    base = _project_dir(pid)
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
    if out_dir.is_dir():
        for unit_dir in sorted(out_dir.iterdir()):
            if not unit_dir.is_dir() or unit_dir.name == "teachers":
                continue
            files = [
                {"label": lbl, "path": f"output/{unit_dir.name}/{fn}", "type": typ}
                for lbl, fn, typ in UNIT_FILE_SPECS
                if (unit_dir / fn).is_file()
            ]
            if not files:
                continue
            teacher_dir = teachers_dir / unit_dir.name
            teacher_files = []
            if teacher_dir.is_dir():
                for tf in sorted(teacher_dir.iterdir()):
                    if tf.is_file() and tf.suffix in (".md", ".pdf", ".json"):
                        teacher_files.append(
                            {
                                "label": tf.name,
                                "path": f"output/teachers/{unit_dir.name}/{tf.name}",
                                "type": tf.suffix.lstrip("."),
                            }
                        )
            units.append(
                {
                    "unit_id": unit_dir.name,
                    "title": titles.get(unit_dir.name, unit_dir.name),
                    "files": files,
                    "teacher_files": teacher_files,
                }
            )
    return {"plates": plates, "layers": layers, "pdfs": pdfs, "units": units}


def _config_summary() -> dict:
    """Read-only, curated view of config.yaml — never the raw secrets-ish blob."""
    if not CONFIG.is_file():
        return {"error": "config.yaml not found"}
    try:
        import yaml  # PyYAML ships with the Loom engine deps.

        cfg = yaml.safe_load(CONFIG.read_text()) or {}
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

        data = yaml.safe_load(PACKET_TYPES_SPEC.read_text()) or {}
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
    """Spawn ./run-audit <pid> <flags>, streaming combined output to a per-run log.
    Returns a runId the client polls. Flags are whitelisted to a safe few."""
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
        ["bash", str(RUN_AUDIT), pid, *clean],
        cwd=str(ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
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
        try:
            if parts == ["api", "projects"]:
                return self._json(_list_projects())
            if parts == ["api", "config"]:
                return self._json(_config_summary())
            if parts == ["api", "packet-types"]:
                return self._json(_packet_types())
            if parts == ["api", "create", "status"]:
                return self._json(_create_status())
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "outputs":
                return self._json(_outputs_tree(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "stats":
                return self._bytes(_safe_file(parts[2], "output/aggregate-stats.json"))
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:5] == ["graph", "runs"]
            ):
                return self._json(_list_graph_runs(parts[2]))
            if (
                len(parts) == 7
                and parts[:2] == ["api", "projects"]
                and parts[3] == "graph"
                and parts[4] == "runs"
                and parts[6] == "overview"
            ):
                return self._json(_graph_overview(parts[2], parts[5]))
            if (
                len(parts) == 8
                and parts[:2] == ["api", "projects"]
                and parts[3] == "graph"
                and parts[4] == "runs"
                and parts[6] == "units"
            ):
                return self._json(_graph_unit_detail(parts[2], parts[5], parts[7]))
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
                return self._bytes(_safe_file(parts[2], rel))
            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                res = _run_status(parts[2])
                return self._json(res) if res else self._json({"error": "no such run"}, 404)
            return self._json({"error": "not found"}, 404)
        except FileNotFoundError as e:
            return self._json({"error": f"not found: {e}"}, 404)
        except (PermissionError, ValueError) as e:
            return self._json({"error": f"forbidden: {e}"}, 403)
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
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)


def main() -> int:
    ap = argparse.ArgumentParser(description="Loom Run Review local API")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[loom-review] API on http://{args.host}:{args.port}  (root: {ROOT})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[loom-review] bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
