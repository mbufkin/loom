#!/usr/bin/env python3
"""
workflows/findings_io.py — single write path for path_*/findings.json.

Every Path A–H runner builds a findings dict and lands here. Validation runs
before the atomic write so a malformed payload fails the run instead of
reaching the dashboard or artifact rung as a quietly wrong file.
"""

from __future__ import annotations

import json
from pathlib import Path

from audit_lib import atomic_write
from schema_validate import raise_on_errors, validate_path_findings


def write_path_findings(dest: Path, findings: dict) -> None:
    """Validate then atomically write one path findings file."""
    raise_on_errors(validate_path_findings(findings), f"path findings {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(findings, indent=2, ensure_ascii=False))
