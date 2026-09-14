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


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _sheet_xml(rows: list[str]) -> str:
    body = "".join(rows)
    return (
        f'<?xml version="1.0"?><worksheet xmlns="{MAIN_NS}">'
        f"<sheetData>{body}</sheetData></worksheet>"
    )


def _write_xlsx(
    path: Path,
    sheets: list[tuple[str, str]],
    shared: str | None = None,
    with_rels: bool = True,
) -> Path:
    """
    Build a workbook by hand, as the two spreadsheet writers in the wild do.

    Raw OOXML rather than openpyxl on purpose: openpyxl only ever emits inline
    strings, so a fixture built with it could not show that the shared-string
    path still works, which is the half of the format Excel itself produces.
    """
    with zipfile.ZipFile(path, "w") as zf:
        if shared is not None:
            zf.writestr("xl/sharedStrings.xml", shared)

        sheet_entries = []
        for i, (name, xml) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)
            sheet_entries.append((i, name))

        if with_rels:
            tabs = "".join(
                f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                for i, name in sheet_entries
            )
            zf.writestr(
                "xl/workbook.xml",
                f'<?xml version="1.0"?>'
                f'<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}">'
                f"<sheets>{tabs}</sheets></workbook>",
            )
            links = "".join(
                f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
                for i, _ in sheet_entries
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                f'<?xml version="1.0"?>'
                f'<Relationships xmlns="{PKG_REL_NS}">{links}</Relationships>',
            )
    return path


def test_xlsx_inline_strings_are_read(tmp_path: Path) -> None:
    """
    A workbook whose text is stored in the cells, not in a shared-string table.

    The table is only an optimisation for repeated values, so it is legal to
    omit entirely -- and openpyxl, pandas .to_excel() and Google Sheets exports
    all do. Reading only the table meant these workbooks extracted to the empty
    string and were reported as "no text extracted", which looks to a teacher
    like their file was accepted and then ignored.
    """
    def cell(ref: str, value: str) -> str:
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    xlsx = _write_xlsx(
        tmp_path / "inventory.xlsx",
        [
            (
                "Welding booths",
                _sheet_xml(
                    [
                        f'<row r="1">{cell("A1", "Booth")}{cell("B1", "Condition")}</row>',
                        f'<row r="2">{cell("A2", "8")}{cell("B2", "Out of service")}</row>',
                    ]
                ),
            )
        ],
    )
    text, method = extract_text(xlsx)
    assert method == "xlsx"
    assert "Out of service" in text
    # The sheet name is content too: it says what the rows beneath it are.
    assert "Welding booths" in text
    # Cells stay on the row they belong to, so "8" and "Out of service" remain
    # a fact about booth 8 rather than two loose fragments.
    assert "8 | Out of service" in text


def test_xlsx_shared_strings_survive_a_styled_cell(tmp_path: Path) -> None:
    """
    The Excel-flavoured workbook, including a cell whose text is styled.

    A styled string is stored as one <r> run per formatting change, each with
    its own <t>. Collecting every <t> in the file into one flat list therefore
    produces more entries than there are strings, and since sheets refer to
    strings by position, every index after the styled cell resolves to the
    wrong value -- a corruption that reads as plausible content.
    """
    shared = (
        f'<?xml version="1.0"?><sst xmlns="{MAIN_NS}">'
        "<si><t>Booth</t></si>"
        "<si><r><t>Out of </t></r><r><t>service</t></r></si>"
        "<si><t>Condition</t></si>"
        "</sst>"
    )
    xlsx = _write_xlsx(
        tmp_path / "excel-style.xlsx",
        [
            (
                "Booths",
                _sheet_xml(
                    [
                        '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                        '<c r="B1" t="s"><v>2</v></c></row>',
                        '<row r="2"><c r="A2" t="n"><v>8</v></c>'
                        '<c r="B2" t="s"><v>1</v></c></row>',
                    ]
                ),
            )
        ],
        shared=shared,
    )
    text, _ = extract_text(xlsx)
    # The styled runs rejoin with no separator inserted between them.
    assert "Out of service" in text
    # Index 2 must still be "Condition". Flattening would have returned
    # "service" here, silently.
    assert "Booth | Condition" in text


def test_xlsx_sheets_come_back_in_tab_order(tmp_path: Path) -> None:
    """
    Tab order comes from workbook.xml, not from the filenames in the zip.

    sheet1.xml is not reliably the first tab once sheets have been reordered or
    deleted, so the relationships are what decide.
    """
    first = _sheet_xml(['<row r="1"><c r="A1" t="inlineStr"><is><t>Alpha</t></is></c></row>'])
    second = _sheet_xml(['<row r="1"><c r="A1" t="inlineStr"><is><t>Beta</t></is></c></row>'])
    xlsx = _write_xlsx(
        tmp_path / "ordered.xlsx", [("Second tab", first), ("First tab", second)]
    )
    text, _ = extract_text(xlsx)
    assert text.index("Second tab") < text.index("First tab")

    # With no workbook.xml to consult, numeric filename order is still better
    # than giving up and returning nothing.
    bare = _write_xlsx(
        tmp_path / "bare.xlsx",
        [("ignored", first), ("ignored", second)],
        with_rels=False,
    )
    text, _ = extract_text(bare)
    assert text.index("Alpha") < text.index("Beta")


def test_xlsx_blank_and_broken_cells_are_dropped(tmp_path: Path) -> None:
    """Formatting-only trailing columns and #REF! errors are not content."""
    xlsx = _write_xlsx(
        tmp_path / "ragged.xlsx",
        [
            (
                "Sheet",
                _sheet_xml(
                    [
                        '<row r="1"><c r="A1" t="inlineStr"><is><t>Item</t></is></c>'
                        '<c r="B1"/><c r="C1"/></row>',
                        '<row r="2"><c r="A2"/><c r="B2"/></row>',
                        '<row r="3"><c r="A3" t="e"><v>#REF!</v></c>'
                        '<c r="B3" t="inlineStr"><is><t>Striker</t></is></c></row>',
                    ]
                ),
            )
        ],
    )
    text, _ = extract_text(xlsx)
    assert "Item" in text and "Striker" in text
    assert "#REF!" not in text
    # The row that held nothing but empty cells contributes no blank line.
    assert "\n\n\n" not in text
    assert not any(line.strip(" |") == "" for line in text.splitlines())


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
        test_xlsx_inline_strings_are_read(root)
        print("OK test_xlsx_inline_strings_are_read")
        test_xlsx_shared_strings_survive_a_styled_cell(root)
        print("OK test_xlsx_shared_strings_survive_a_styled_cell")
        test_xlsx_sheets_come_back_in_tab_order(root)
        print("OK test_xlsx_sheets_come_back_in_tab_order")
        test_xlsx_blank_and_broken_cells_are_dropped(root)
        print("OK test_xlsx_blank_and_broken_cells_are_dropped")
        test_iter_sources_temp(root)
        print("OK test_iter_sources_temp")
    test_private_osint_corpus_optional()
    print("ALL doc_extract TESTS PASSED")
