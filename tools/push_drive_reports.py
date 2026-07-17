#!/usr/bin/env python3
"""
push_drive_reports.py — Upload Crystallize report PDFs (+ unit files) to Google Drive.

Default layout (creates folders as needed):

  <remote>:<base>/<project_id>/
    GLOBAL-AUDIT-REPORT.pdf                         # course first-pass (latest)
    runs/<stamp>-GLOBAL-AUDIT-REPORT.pdf            # archive
    <Unit Title>/                                   # human unit name (not slug)
      TEACHER-PACKET.pdf                            # auditor punch list
      UNIT-PLAN.pdf                                 # CTAT discovery Unit Plan (blank = not found)
      LESSON-PLAN.pdf                               # Lesson structure inventory, test draft (blank = not found)
      files/
        <Readable Document Title>.txt               # source extracts, teacher-openable names
      README.txt                                    # what to open first

Env overrides:
  CRYSTALLIZE_DRIVE_REMOTE   default: gdrive
  CRYSTALLIZE_DRIVE_BASE     default: Loom
  RCLONE                     default: rclone on PATH or ~/.local/bin/rclone

Exit codes: 0 success or soft-skip; 1 hard misconfiguration when --strict.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 tools/push_drive_reports.py` from any cwd.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audit_lib import BASE_DIR, load_yaml, log, project_dir, validate_slug_id
from synthesize import readable_title_from_filename

DEFAULT_REMOTE = os.environ.get("CRYSTALLIZE_DRIVE_REMOTE", "gdrive")
DEFAULT_BASE = os.environ.get("CRYSTALLIZE_DRIVE_BASE", "Loom")
REPORT_PDF = "GLOBAL-AUDIT-REPORT.pdf"
TEACHER_PDF = "TEACHER-PACKET.pdf"
UNIT_PLAN_PDF = "UNIT-PLAN.pdf"
LESSON_PLAN_PDF = "LESSON-PLAN.pdf"


def _rclone_bin() -> str | None:
    env = os.environ.get("RCLONE")
    if env and Path(env).is_file() and os.access(env, os.X_OK):
        return env
    which = shutil.which("rclone")
    if which:
        return which
    local = Path.home() / ".local" / "bin" / "rclone"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return None


def _run(
    rclone: str, args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    cmd = [rclone, *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def remote_configured(rclone: str, remote: str) -> bool:
    try:
        out = _run(rclone, ["listremotes"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return f"{remote}:" in {line.strip() for line in out.stdout.splitlines()}


def ensure_dir(rclone: str, dest_dir: str) -> None:
    """Create Drive folder path if missing (rclone mkdir is idempotent enough)."""
    _run(rclone, ["mkdir", dest_dir], check=False)


def _safe_drive_name(name: str, *, max_len: int = 80) -> str:
    """Drive-friendly folder/file stem: keep spaces, drop path junk."""
    name = (name or "untitled").strip() or "untitled"
    name = re.sub(r'[\\/:*?"<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len] or "untitled"


def collect_pdf(project_id: str) -> Path | None:
    pdf = project_dir(project_id) / "output" / REPORT_PDF
    return pdf if pdf.is_file() else None


def _unit_title(manifest: dict, unit_id: str) -> str:
    unit = (manifest.get("units") or {}).get(unit_id) or {}
    return _safe_drive_name(str(unit.get("title") or unit_id))


def _copyto(rclone: str, src: Path, dest: str) -> None:
    _run(rclone, ["copyto", str(src), dest], check=True)


def push_project(
    project_id: str,
    *,
    remote: str = DEFAULT_REMOTE,
    base: str = DEFAULT_BASE,
    rclone: str | None = None,
    archive: bool = True,
    strict: bool = False,
) -> bool:
    """
    Push course PDF + per-unit teacher folders (packet PDF + readable source files).
    Returns True if anything uploaded; False on soft failure.
    """
    validate_slug_id(project_id, "project id")
    rclone = rclone or _rclone_bin()
    if not rclone:
        msg = "rclone not found — skip Drive push (install or set RCLONE=)"
        if strict:
            raise RuntimeError(msg)
        log(f"WARN: {msg}")
        return False
    if not remote_configured(rclone, remote):
        msg = (
            f"rclone remote '{remote}' not configured — skip Drive push "
            f"(see docs/images/setup-gdrive-rclone.sh)"
        )
        if strict:
            raise RuntimeError(msg)
        log(f"WARN: {msg}")
        return False

    root = project_dir(project_id)
    manifest_path = root / "manifest.yaml"
    manifest = load_yaml(manifest_path) if manifest_path.is_file() else {"units": {}}
    sources = root / "sources"
    pdf = collect_pdf(project_id)
    teachers_root = root / "output" / "teachers"

    if not pdf and not (
        teachers_root.is_dir() and any(teachers_root.glob(f"*/{TEACHER_PDF}"))
    ):
        msg = f"no report PDFs for {project_id} — skip Drive push"
        if strict:
            raise RuntimeError(msg)
        log(f"WARN: {msg}")
        return False

    dest_root = f"{remote}:{base.rstrip('/')}/{project_id}"
    ensure_dir(rclone, dest_root)
    uploaded = 0

    if pdf:
        dest_latest = f"{dest_root}/{REPORT_PDF}"
        log(f"Drive push → {dest_latest}")
        try:
            _copyto(rclone, pdf, dest_latest)
            uploaded += 1
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            if strict:
                raise RuntimeError(f"Drive push failed: {err}") from e
            log(f"WARN: Drive push failed for {project_id} global PDF: {err}")
            return False

        if archive:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            runs_dir = f"{dest_root}/runs"
            ensure_dir(rclone, runs_dir)
            dest_arch = f"{runs_dir}/{stamp}-{REPORT_PDF}"
            try:
                _copyto(rclone, pdf, dest_arch)
                log(f"Drive archive → {dest_arch}")
            except subprocess.CalledProcessError as e:
                log(f"WARN: Drive archive copy failed: {(e.stderr or str(e)).strip()}")

    # Per-unit folders named for humans, with packet + source files.
    if teachers_root.is_dir():
        for unit_dir in sorted(p for p in teachers_root.iterdir() if p.is_dir()):
            unit_id = unit_dir.name
            packet = unit_dir / TEACHER_PDF
            if not packet.is_file():
                continue
            folder_name = _unit_title(manifest, unit_id)
            unit_dest = f"{dest_root}/{folder_name}"
            files_dest = f"{unit_dest}/files"
            ensure_dir(rclone, unit_dest)
            ensure_dir(rclone, files_dest)
            try:
                _copyto(rclone, packet, f"{unit_dest}/{TEACHER_PDF}")
                uploaded += 1
            except subprocess.CalledProcessError as e:
                log(
                    f"WARN: Drive push failed for teacher {unit_id}: "
                    f"{(e.stderr or str(e)).strip()}"
                )
                continue

            unit_plan = unit_dir / UNIT_PLAN_PDF
            if unit_plan.is_file():
                try:
                    _copyto(rclone, unit_plan, f"{unit_dest}/{UNIT_PLAN_PDF}")
                    uploaded += 1
                except subprocess.CalledProcessError as e:
                    log(
                        f"WARN: Drive push failed for unit plan {unit_id}: "
                        f"{(e.stderr or str(e)).strip()}"
                    )

            lesson_plan = unit_dir / LESSON_PLAN_PDF
            if lesson_plan.is_file():
                try:
                    _copyto(rclone, lesson_plan, f"{unit_dest}/{LESSON_PLAN_PDF}")
                    uploaded += 1
                except subprocess.CalledProcessError as e:
                    log(
                        f"WARN: Drive push failed for lesson plan {unit_id}: "
                        f"{(e.stderr or str(e)).strip()}"
                    )

            unit_meta = (manifest.get("units") or {}).get(unit_id) or {}
            rels = unit_meta.get("documents") or unit_meta.get("source_files") or []
            with tempfile.TemporaryDirectory(prefix="crystallize-drive-") as tmp:
                tmp_path = Path(tmp)
                readme = tmp_path / "README.txt"
                has_unit_plan = unit_plan.is_file()
                has_lesson_plan = lesson_plan.is_file()
                steps = [
                    "1. Open TEACHER-PACKET.pdf — auditor punch list for this unit.\n"
                ]
                n = 2
                if has_unit_plan:
                    steps.append(
                        f"{n}. Open UNIT-PLAN.pdf — CTAT Unit Plan (blank = not found).\n"
                    )
                    n += 1
                if has_lesson_plan:
                    steps.append(
                        f"{n}. Open LESSON-PLAN.pdf — lesson structure inventory "
                        "(test draft; blank = not found).\n"
                    )
                    n += 1
                steps.append(
                    f"{n}. Open files/ for the curriculum documents named in the packet.\n"
                    "   File names match the packet — no internal hash ids.\n"
                )
                readme.write_text(
                    f"Crystallize / Loom — {folder_name}\n"
                    f"Dataset: {project_id}\n\n" + "".join(steps),
                    encoding="utf-8",
                )
                try:
                    _copyto(rclone, readme, f"{unit_dest}/README.txt")
                except subprocess.CalledProcessError:
                    pass

                for rel in rels:
                    src = sources / rel
                    if not src.is_file():
                        # Manifest paths are sometimes already basename-only under sources/
                        alt = sources / Path(rel).name
                        src = alt if alt.is_file() else src
                    if not src.is_file():
                        log(f"WARN: missing source for Drive files/: {rel}")
                        continue
                    human = _safe_drive_name(readable_title_from_filename(str(rel)))
                    ext = src.suffix or ".txt"
                    local_copy = tmp_path / f"{human}{ext}"
                    # Avoid collisions within the unit
                    n = 2
                    while local_copy.exists():
                        local_copy = tmp_path / f"{human} ({n}){ext}"
                        n += 1
                    shutil.copy2(src, local_copy)
                    try:
                        _copyto(rclone, local_copy, f"{files_dest}/{local_copy.name}")
                        uploaded += 1
                    except subprocess.CalledProcessError as e:
                        log(
                            f"WARN: Drive file push failed ({local_copy.name}): "
                            f"{(e.stderr or str(e)).strip()}"
                        )

        log(
            f"Drive push unit folders → {dest_root}/ (<Unit Title>/TEACHER-PACKET.pdf + files/)"
        )

    log(f"Drive push OK — {project_id} ({uploaded} file(s))")
    return uploaded > 0


def list_projects_with_pdf() -> list[str]:
    """All projects/<id>/output/GLOBAL-AUDIT-REPORT.pdf under the shelf."""
    projects = BASE_DIR / "projects"
    ids: list[str] = []
    if not projects.is_dir():
        return ids
    for p in sorted(projects.iterdir()):
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if (p / "output" / REPORT_PDF).is_file():
            ids.append(p.name)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push Crystallize report PDFs + unit file folders to Google Drive (rclone)"
    )
    parser.add_argument(
        "--project",
        help="One dataset id (default with --all: every project that has a report PDF)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Push every projects/*/output/GLOBAL-AUDIT-REPORT.pdf (+ teachers if present)",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"rclone remote (default {DEFAULT_REMOTE})",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Drive folder base (default {DEFAULT_BASE!r})",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Only update latest PDF; skip runs/<stamp>- copy",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on missing rclone/PDF/upload failure (default: soft WARN)",
    )
    args = parser.parse_args()

    if args.all and args.project:
        log("ERROR: use --project or --all, not both")
        return 2
    if not args.all and not args.project:
        log("ERROR: pass --project ID or --all")
        return 2

    ids = list_projects_with_pdf() if args.all else [args.project]
    if args.all and not ids:
        log("WARN: no projects with GLOBAL-AUDIT-REPORT.pdf found")
        return 0

    ok_any = False
    for pid in ids:
        try:
            if push_project(
                pid,
                remote=args.remote,
                base=args.base,
                archive=not args.no_archive,
                strict=args.strict,
            ):
                ok_any = True
        except (RuntimeError, ValueError) as e:
            log(f"ERROR: {e}")
            return 1
    return 0 if ok_any or not args.strict else 1


if __name__ == "__main__":
    sys.exit(main())
