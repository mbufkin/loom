#!/usr/bin/env python3
"""
bootstrap.py — get a fresh copy of Loom ready to run, on any platform.

Run once after downloading:

    python bootstrap.py

This exists because the alternative was a README telling a curriculum director
to install a package manager. Everything Loom genuinely needs is now an
ordinary Python package with prebuilt wheels for Windows, macOS and Linux on
both Intel and ARM, so provisioning is a single pip call and no admin rights.

Two things are deliberately *not* installed here:

  * A language model. Loom does not ship one and cannot choose one for you --
    which model, and whether it runs on this machine or on a server the
    district approves, is a policy decision, not a setup step.
  * WeasyPrint's native GTK/Pango libraries. These are the one dependency pip
    cannot supply on Windows, and they are optional: PDFs are rendered with
    ReportLab when they are absent, so every report is still produced. GTK buys
    the full print theme, not the PDF itself.

Design note for anyone extending this: prefer a Python package with wheels
over a system package every time, even if the system tool is marginally
better. A dependency your users cannot install is worse than a slightly worse
dependency they already have. That reasoning is why PDF reading moved from
poppler (a system package, usually needing admin) to PDFium (a wheel), with
poppler kept only as a preferred-if-present upgrade. PDF *writing* now follows
the same shape: ReportLab (a wheel) always works, WeasyPrint is the
preferred-if-present upgrade for the print theme.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"

# (import name, human name, what breaks without it)
REQUIRED = [
    ("yaml", "PyYAML", "reading manifests and calendars"),
    ("requests", "requests", "talking to the model"),
    ("jinja2", "Jinja2", "report templates"),
    ("reportlab", "reportlab", "report layout"),
    ("pypdfium2", "pypdfium2", "reading PDF documents"),
]


def _can_import(module: str) -> bool:
    """Real import, not find_spec.

    A package can be installed and still fail to load when its native
    libraries are missing -- exactly WeasyPrint's failure mode on Windows --
    and reporting that as "installed" is how people end up debugging a
    mysterious crash three steps later.

    Output is muted at file-descriptor level for the duration of the import.
    WeasyPrint prints a multi-line "follow the installation steps before
    reporting an issue" banner to stdout when its libraries are missing, which
    would otherwise land in the middle of this checklist and read as a failure,
    directly above the line saying PDFs still work without it.
    """
    saved = (os.dup(1), os.dup(2))
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        try:
            __import__(module)
            return True
        except Exception:
            return False
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(devnull)
        os.close(saved[0])
        os.close(saved[1])


def install_requirements() -> bool:
    """pip install -r requirements.txt using this very interpreter.

    `sys.executable -m pip` rather than a bare `pip`: on a machine with more
    than one Python, bare `pip` routinely installs into a different one than
    the one that will run the program, and the packages appear to vanish.
    """
    if not REQUIREMENTS.is_file():
        print(f"! requirements.txt not found at {REQUIREMENTS}")
        return False
    print(f"Installing dependencies with {sys.executable}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=str(ROOT),
    )
    return result.returncode == 0


def report() -> bool:
    """Print what is ready and what is not. Returns True if Loom can run."""
    print()
    print("Required")
    ready = True
    for module, name, why in REQUIRED:
        ok = _can_import(module)
        ready = ready and ok
        print(f"  [{'ok' if ok else '--'}] {name:<12} {why}")

    print()
    print("Optional")
    weasy = _can_import("weasyprint")
    print(
        f"  [{'ok' if weasy else '--'}] {'WeasyPrint':<12} "
        "full PDF print theme (ReportLab still writes every PDF without it)"
    )
    poppler = shutil.which("pdftotext")
    print(
        f"  [{'ok' if poppler else '--'}] {'poppler':<12} "
        "preferred PDF text extraction (PDFium is used when absent)"
    )
    return ready


def main() -> int:
    print(f"Loom bootstrap — {sys.platform}, Python {sys.version.split()[0]}")
    if not install_requirements():
        print()
        print("! Dependency installation failed. The output above says why;")
        print("  a proxy or a read-only Python installation are the usual causes.")
        return 1

    ready = report()
    print()
    if ready:
        print("Loom is ready to read a curriculum.")
        print("Next: start your language model, then run  python ui/window.py")
    else:
        print("! Something required is still missing — see the list above.")
    # A missing model is not a bootstrap failure: it is started separately and
    # may legitimately not be running yet.
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
