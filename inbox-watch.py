#!/usr/bin/env python3
"""
inbox-watch.py — Watch ~/g10-sync/inbox/ for new curriculum files.

When a new file (PDF, DOCX, TXT, PPTX) or a URL file (*.url) lands in the
inbox, it:
  1. Creates a project folder under projects/ (name derived from filename)
  2. Moves the source file into projects/<id>/sources/
  3. Runs the full Crystallize pipeline (ingest + audit)
  4. Copies all output PDFs + SUMMARY.md into ~/g10-sync/reports/<id>/

Usage:
  python3 inbox-watch.py                # run in foreground
  python3 inbox-watch.py --daemon       # run as daemon

Best practice: run as a systemd user service (see g10-inbox-watch.service).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

INBOX = Path.home() / "g10-sync" / "inbox"
REPORTS = Path.home() / "g10-sync" / "reports"
G10 = Path.home() / "g10-control-center-loom"
PYTHON = sys.executable

# File types Crystallize can ingest
SUPPORTED_EXTS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".pptx",
    ".xlsx",
    ".odt",
    ".rtf",
    ".html",
}

# ── Logging ───────────────────────────────────────────────────────────────────

# Runtime logs live under logs/ (Zone A), not the repo root.
LOG_FILE = G10 / "logs" / "inbox-watch.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[inbox-watch] %(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────


def slug(name: str, max_len: int = 40) -> str:
    """Convert a filename into a safe project slug."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return (s[:max_len] or "inbox-project").strip("-")


def date_prefix() -> str:
    return datetime.now().strftime("%Y%m%d")


def project_id_for(p: Path) -> str:
    return f"{slug(p.name)}-{date_prefix()}"


def fingerprint(p: Path) -> str:
    """SHA256 of first 64K — fast dedup check."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()[:16]


STATE_FILE = INBOX / ".processed.json"


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── URL file support ───────────────────────────────────────────────────────────


def extract_url(p: Path) -> str | None:
    """Read a *.url drop file (plain URL or Windows .url format)."""
    text = p.read_text(errors="replace").strip()
    if text.startswith("http"):
        return text.split()[0]
    # Windows .url format: URL=https://...
    m = re.search(r"URL\s*=\s*(https?://\S+)", text, re.I)
    return m.group(1) if m else None


# ── Core pipeline ─────────────────────────────────────────────────────────────


def run_audit(project_id: str, extra_args: list[str] | None = None) -> bool:
    """Run the Crystallize pipeline; return True on success."""
    cmd = [
        PYTHON,
        str(G10 / "run_project.py"),
        "--project",
        project_id,
        "--ingest",
        "--force",
    ]
    if extra_args:
        cmd.extend(extra_args)
    log.info("Running audit: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=G10, capture_output=False)
    return result.returncode == 0


def copy_reports(project_id: str) -> list[Path]:
    """Copy output PDFs + SUMMARY.md into ~/g10-sync/reports/<project_id>/."""
    src = G10 / "projects" / project_id / "output"
    dst = REPORTS / project_id
    dst.mkdir(parents=True, exist_ok=True)

    copied = []
    if not src.is_dir():
        log.warning("No output dir found: %s", src)
        return copied

    # Copy global Layer-1 deliverables only (unit AUDIT-REPORT.pdf is archived path).
    for name in (
        "GLOBAL-AUDIT-REPORT.pdf",
        "SUMMARY.md",
        "DASHBOARD.md",
        "GLOBAL-AUDIT.md",
    ):
        f = src / name
        if f.is_file():
            shutil.copy2(f, dst / name)
            copied.append(dst / name)

    # Write a quick index for easy browsing
    (dst / "INDEX.txt").write_text(
        f"Project: {project_id}\n"
        f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
        + "\n".join(str(p.relative_to(dst)) for p in copied)
    )
    log.info("Copied %d files to %s", len(copied), dst)
    return copied


def process_file(p: Path, state: dict) -> None:
    """Ingest one file from inbox, run audit, push reports."""
    fp = fingerprint(p)
    key = f"{p.name}::{fp}"
    if key in state:
        log.info("Skipping already-processed: %s", p.name)
        return

    pid = project_id_for(p)
    log.info("New file detected: %s → project %s", p.name, pid)

    # Create project sources dir and move file in
    sources = G10 / "projects" / pid / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    dest = sources / p.name
    shutil.copy2(p, dest)
    log.info("Copied to sources: %s", dest)

    ok = run_audit(pid)
    if ok:
        copy_reports(pid)
        state[key] = {"project": pid, "ts": datetime.now().isoformat(), "status": "ok"}
        log.info("✓ Done: %s → reports/%s/", p.name, pid)
    else:
        state[key] = {
            "project": pid,
            "ts": datetime.now().isoformat(),
            "status": "failed",
        }
        log.error("✗ Audit failed for %s — check %s/runs/", p.name, pid)

    save_state(state)


def process_url_file(p: Path, state: dict) -> None:
    """Handle a *.url drop file — crawl the URL and audit."""
    url = extract_url(p)
    if not url:
        log.warning("Could not parse URL from %s", p.name)
        return

    fp = hashlib.sha256(url.encode()).hexdigest()[:16]
    key = f"url::{fp}"
    if key in state:
        log.info("Skipping already-processed URL: %s", url)
        return

    pid = project_id_for(p)
    log.info("URL drop detected: %s → project %s", url, pid)

    sources = G10 / "projects" / pid / "sources"
    sources.mkdir(parents=True, exist_ok=True)

    # Write the URL into a plain text file so ingest can see it
    (sources / "source-url.txt").write_text(
        f"Source URL: {url}\nDropped: {datetime.now().isoformat()}\n"
    )

    ok = run_audit(pid)
    if ok:
        copy_reports(pid)
        state[key] = {
            "project": pid,
            "url": url,
            "ts": datetime.now().isoformat(),
            "status": "ok",
        }
    else:
        state[key] = {
            "project": pid,
            "url": url,
            "ts": datetime.now().isoformat(),
            "status": "failed",
        }

    save_state(state)


# ── Main loop ─────────────────────────────────────────────────────────────────


def watch(poll_seconds: int = 5) -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    log.info("Watching inbox: %s (poll every %ds)", INBOX, poll_seconds)
    log.info("Reports land in: %s", REPORTS)

    while True:
        state = load_state()
        for p in sorted(INBOX.iterdir()):
            # Skip hidden files, the state file, and directories
            if p.name.startswith(".") or p.is_dir():
                continue
            if p.suffix.lower() in {".url", ".txt"} and "url" in p.name.lower():
                process_url_file(p, state)
            elif p.suffix.lower() in SUPPORTED_EXTS:
                process_file(p, state)
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch G10 inbox and auto-run Crystallize"
    )
    parser.add_argument(
        "--poll", type=int, default=5, help="Poll interval in seconds (default 5)"
    )
    args = parser.parse_args()

    try:
        watch(poll_seconds=args.poll)
    except KeyboardInterrupt:
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
