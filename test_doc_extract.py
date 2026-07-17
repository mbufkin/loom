#!/usr/bin/env python3
"""Tests for multi-format document extraction."""

import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from doc_extract import extract_text, iter_source_files
from audit_lib import scrub_document


def test_txt_still_works():
    p = BASE / "data/career-curriculum/osint/doc_4b97944cd264_Engineering_Lesson.txt"
    text, method = extract_text(p)
    assert method == "text"
    assert "Day 1" in text


def test_minimal_docx(tmp_path: Path):
    docx = tmp_path / "lesson.docx"
    # Minimal valid docx zip
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


def test_iter_sources():
    files = iter_source_files(BASE / "data/career-curriculum/osint")
    assert len(files) == 111
    assert any(f.suffix == ".txt" for f in files)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        test_txt_still_works()
        test_minimal_docx(Path(td))
        test_iter_sources()
    print("ALL doc_extract TESTS PASSED")
