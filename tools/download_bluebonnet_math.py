#!/usr/bin/env python3
"""Download TEA Bluebonnet Math PDFs from TEA Learn Canvas (files API).

Default scope: Grade 5 (9543) + Algebra I (9546).
Skips duplicate full-volume binders (Volume 1/2.pdf) — prefer per-module TE/SE.

Usage:
  python3 tools/download_bluebonnet_math.py --project bluebonnet-math-2026
  python3 tools/download_bluebonnet_math.py --dest projects/bluebonnet-math-2026/_corpus
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

COURSES = {
    "grade-5": 9543,
    "algebra-1": 9546,
}

# Full-volume binders duplicate per-module TE/SE packs (~300 MB of overlap).
BINDER_RE = re.compile(
    r"Teacher Edition,\s*Volume\s+[12]\.pdf$"
    r"|Student Edition,\s*Volume\s+[12]\.pdf$"
    r"|Teacher Edition,\s*Volume\s+[12]\.pdf"
    r"|_Volume_[12]\.pdf$",
    re.I,
)


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return s[:160]


def is_binder(display_name: str) -> bool:
    """True for course-wide Volume 1/2 binders (not Module N Volume 1 Module N)."""
    n = display_name
    if re.search(r"Volume\s+[12]\s+Module\s+\d+", n, re.I):
        return False
    if re.search(r"Volume_[12]_Module_\d+", n, re.I):
        return False
    # Exact-style binders: "... Teacher Edition, Volume 1.pdf"
    if re.search(r"Volume\s+[12]\.pdf\s*$", n, re.I) and "Module" not in n:
        return True
    if re.search(r"_Volume_[12]\.pdf$", n, re.I) and "Module" not in n:
        return True
    return bool(BINDER_RE.search(n) and "Module" not in n)


def list_files(course_id: int) -> list[dict]:
    files: list[dict] = []
    url = (
        f"https://tealearn.instructure.com/api/v1/courses/{course_id}/files"
        f"?per_page=100"
    )
    while url:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            batch = json.loads(resp.read().decode())
            link = resp.headers.get("Link", "")
        files.extend(batch)
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part[part.find("<") + 1 : part.find(">")]
        url = next_url
    return files


def download(f: dict, dest: Path) -> bool:
    url = f.get("url")
    if not url:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return True  # already present
    req = urllib.request.Request(url, headers={"User-Agent": "loom-bluebonnet/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="bluebonnet-math-2026")
    ap.add_argument(
        "--dest",
        type=Path,
        help="Destination root (default: projects/<id>/_corpus)",
    )
    ap.add_argument(
        "--include-binders",
        action="store_true",
        help="Also download full Volume 1/2 binders (not recommended)",
    )
    args = ap.parse_args()
    dest_root = args.dest or (BASE / "projects" / args.project / "_corpus")
    dest_root.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for folder, course_id in COURSES.items():
        files = list_files(course_id)
        print(f"{folder} (course {course_id}): {len(files)} files on Canvas")
        for f in files:
            name = f.get("display_name") or f.get("filename") or "unknown.pdf"
            if not name.lower().endswith(".pdf"):
                continue
            if not args.include_binders and is_binder(name):
                print(f"  skip binder: {name}")
                manifest.append(
                    {
                        "course": course_id,
                        "name": name,
                        "skipped": "binder",
                        "bytes": f.get("size"),
                    }
                )
                continue
            out = dest_root / folder / slug(name)
            if not out.suffix:
                out = out.with_suffix(".pdf")
            print(f"  get {name} -> {out.relative_to(dest_root)}", flush=True)
            ok = download(f, out)
            manifest.append(
                {
                    "course": course_id,
                    "folder": folder,
                    "name": name,
                    "path": str(out.relative_to(dest_root)),
                    "bytes": out.stat().st_size if ok and out.is_file() else 0,
                    "ok": ok,
                }
            )

    man_path = dest_root / "download-manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    got = sum(1 for m in manifest if m.get("ok"))
    skipped = sum(1 for m in manifest if m.get("skipped"))
    print(f"DONE: {got} downloaded/present, {skipped} binders skipped -> {dest_root}")
    print(f"manifest: {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
