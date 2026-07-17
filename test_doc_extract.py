#!/usr/bin/env python3
"""Tests for multi-format document extraction.

Offline-safe by default (temp fixtures). Optional private-corpus checks run
only when local `data/career-curriculum/osint/` is present.
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from audit_lib import scrub_document
from doc_extract import extract_text, iter_source_files

PRIVATE_OSINT = BASE / "data/career-curriculum/osint"


def test_minimal_txt(tmp_path: Path) -> None:
    p = tmp_path / "lesson.txt"
    p.write_text("Day 1 Lesson Plan\nObjective: learn.\n", encoding="utf-8")
    text, method = extract_text(p)
    assert method == "text"
    assert "Day 1" in text


def test_minimal_docx(tmp_path: Path) -> None:
    docx = tmp_path / "lesson.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Day 1 Lesson Plan</w:t></w:r></w:p></w:body></w:document>",
        )
    text, method = extract_text(docx)
    assert method == "docx"
    assert "Day 1" in text
    ev = scrub_document(docx)
    assert ev["day_hints"] == [1]


def test_iter_sources_temp(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "b.md").write_text("# hi", encoding="utf-8")
    files = iter_source_files(tmp_path)
    assert len(files) >= 2


def test_private_osint_corpus_optional() -> None:
    """Skipped in public clones — private curriculum is not redistributed."""
    if not PRIVATE_OSINT.is_dir():
        print("SKIP test_private_osint_corpus_optional (no local osint corpus)")
        return
    sample = next(PRIVATE_OSINT.glob("doc_*.txt"), None)
    assert sample is not None, "expected doc_*.txt under osint"
    text, method = extract_text(sample)
    assert method == "text"
    assert len(text) > 20
    files = iter_source_files(PRIVATE_OSINT)
    assert len(files) >= 1


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        test_minimal_txt(root)
        print("OK test_minimal_txt")
        test_minimal_docx(root)
        print("OK test_minimal_docx")
        test_iter_sources_temp(root)
        print("OK test_iter_sources_temp")
    test_private_osint_corpus_optional()
    print("ALL doc_extract TESTS PASSED")
