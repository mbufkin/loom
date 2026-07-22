#!/usr/bin/env python3
"""
ui/server.py — Loom Run Review, local-only API.

A deliberately tiny, dependency-light (stdlib-only) HTTP server that lets a local
browser review the artifacts a completed Loom run wrote under projects/<id>/. It
does NOT run the model or interpret curriculum; it just lists, serves, and (on
request) launches a local `./run-audit`. Local-only by design: no auth, binds to
127.0.0.1, and every file read is confined to the requested project directory.

Endpoints (all under /api):
  GET  /api/projects                      -> [{id, tier, has_output, ...}]
  GET  /api/projects/{id}/outputs         -> grouped tree of reviewable files
  GET  /api/projects/{id}/file?path=REL   -> raw bytes of one file (guarded)
  GET  /api/projects/{id}/stats           -> output/aggregate-stats.json
  POST /api/projects/{id}/run             -> {runId}  (spawns ./run-audit)
  GET  /api/runs/{runId}                  -> {status, exitCode, log}
  GET  /api/config                        -> read-only config.yaml summary

Run:  python3 ui/server.py [--port 8770]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Repo root = parent of this ui/ directory. Everything is resolved against it.
ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
RUN_AUDIT = ROOT / "run-audit"
CONFIG = ROOT / "config.yaml"
RUNS_DIR = ROOT / "ui" / ".runs"  # per-run log files (gitignored)

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


def _status_tiers() -> dict[str, str]:
    """Parse projects/STATUS.md's markdown table into {project_id: tier}. Best-effort:
    the review site still works if STATUS.md is missing or reformatted."""
    tiers: dict[str, str] = {}
    status = PROJECTS / "STATUS.md"
    if not status.is_file():
        return tiers
    # Rows look like: | `dallas-career-2026` | **Golden** | Yes | Yes | ... |
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
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "outputs":
                return self._json(_outputs_tree(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "stats":
                return self._bytes(_safe_file(parts[2], "output/aggregate-stats.json"))
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
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b"{}"
                flags = (json.loads(body or b"{}") or {}).get("flags", [])
                run_id = _start_run(parts[2], flags)
                return self._json({"runId": run_id})
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
