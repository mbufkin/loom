"""Per-stage accountability helpers for intake goldens.

Implements the extract (S1) slice of the contract from wayfinder #7:
every curriculum candidate must appear with extract_ok | extract_failed |
extract_empty (or be omitted from expected when a host tool is absent).
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import yaml

from audit_lib import scrub_document
from doc_extract import iter_source_files

GOLDENS_ROOT = Path(__file__).resolve().parent


def _load_generate():
    path = GOLDENS_ROOT / "generate.py"
    spec = importlib.util.spec_from_file_location("intake_goldens_generate", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def discover_packs() -> list[Path]:
    return [p.parent for p in sorted((GOLDENS_ROOT / "packs").glob("*/pack.yaml"))]


def load_pack(pack_dir: Path) -> dict:
    return yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))


def pdftotext_available() -> bool:
    return shutil.which("pdftotext") is not None


def materialize_sources(pack_dir: Path, dest: Path) -> list[str]:
    """Build sources/ tree; return skip reasons from generators."""
    cfg = load_pack(pack_dir)
    formats = list(cfg.get("required_formats") or [])
    return _load_generate().materialize_pack(pack_dir, dest, formats=formats)


def classify_extract(sources: Path) -> dict[str, dict]:
    """Return rel_path → {status, char_count_clean, extraction_error?}."""
    out: dict[str, dict] = {}
    for path in iter_source_files(sources):
        rel = path.relative_to(sources).as_posix()
        ev = scrub_document(path)
        err = ev.get("extraction_error")
        chars = int(ev.get("char_count_clean") or 0)
        if err:
            status = "extract_failed"
        elif chars <= 0:
            status = "extract_empty"
        else:
            status = "extract_ok"
        out[rel] = {
            "status": status,
            "char_count_clean": chars,
            "extraction_error": err,
        }
    return out


def assert_extract_accountability(pack_dir: Path, sources: Path) -> None:
    """Fail closed if any expected candidate is missing or has the wrong status."""
    expected_cands = json.loads(
        (pack_dir / "expected" / "candidates.json").read_text(encoding="utf-8")
    )
    expected_extract = json.loads(
        (pack_dir / "expected" / "extract.json").read_text(encoding="utf-8")
    )
    actual = classify_extract(sources)

    for rel, row in actual.items():
        assert row["status"] in {
            "extract_ok",
            "extract_failed",
            "extract_empty",
        }, f"{rel}: unlabeled status {row['status']!r}"

    expected_paths = {c["path"] for c in expected_cands["candidates"]}
    expected_files = dict(expected_extract["files"])
    # Soft-skip PDF expectations when pdftotext is missing (host tool policy).
    if not pdftotext_available():
        expected_paths = {p for p in expected_paths if not p.endswith(".pdf")}
        expected_files = {
            k: v for k, v in expected_files.items() if not k.endswith(".pdf")
        }

    missing = sorted(expected_paths - set(actual))
    extra = sorted(set(actual) - expected_paths)
    assert not missing, f"candidates missing from extract inventory: {missing}"
    assert not extra, f"unexpected candidates (update expected/): {extra}"

    for rel, want in expected_files.items():
        got = actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: expected extract status {want['status']!r}, got {got!r} "
            f"(err={actual[rel].get('extraction_error')!r})"
        )
