#!/usr/bin/env python3
"""Tests for the ReportLab PDF fallback (no models, no GTK, no network).

Context: WeasyPrint needs GTK/Pango, which pip cannot supply on Windows. Before
this fallback existed a completed audit produced no PDF at all -- the import
failure took down the whole pdf_theme package, so even the ReportLab path, which
has no native dependencies, never got a chance to run.
"""

import io
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from pdf_theme.reportlab_render import (
    _appendix_flowables,
    _safe_text,
    _styles,
    md_to_flowables,
    render_packet_pdf_reportlab,
)


def test_pdf_theme_imports_without_gtk():
    """The regression that mattered most: a missing native library must not
    take down the package that contains the working fallback."""
    import pdf_theme
    from pdf_theme.render import render_packet_pdf

    assert callable(render_packet_pdf)
    assert callable(pdf_theme.render_packet_pdf)


def test_glyphs_outside_winansi_are_replaced_not_mangled():
    """ReportLab's built-in fonts are WinAnsi-only and the bundled brand fonts
    are PostScript-outline OTFs it refuses to register, so anything outside
    Latin-1 silently corrupts. The year grid rendered "â—" where it meant "●"."""
    assert _safe_text("\u25cf") == "\u2022"  # ● -> •
    assert _safe_text("a \u2192 b") == "a -> b"
    assert _safe_text("\u2713 done") == "yes done"

    # Characters WinAnsi does cover must pass through untouched.
    assert _safe_text("caf\u00e9 \u2014 r\u00e9sum\u00e9") == "caf\u00e9 \u2014 r\u00e9sum\u00e9"
    assert _safe_text("plain ascii") == "plain ascii"

    # An unmapped, undecomposable character degrades visibly rather than
    # corrupting the file.
    assert _safe_text("\u4e2d") == "?"
    # Decomposable ones keep their ASCII base.
    assert _safe_text("\u01ce") == "a"


def test_markdown_constructs_all_produce_flowables():
    styles = _styles()
    md = (
        "# Skipped title\n\n"
        "## Section\n\n"
        "Body text with **bold** and `code`.\n\n"
        "### Subsection\n\n"
        "- first bullet\n- second bullet\n\n"
        "1. first step\n2. second step\n\n"
        "| Unit | Status |\n|---|---|\n| immune | MISSING |\n\n"
        "---\n\n"
        "*an italic note*\n"
    )
    flowables = md_to_flowables(md, styles, skip_h1=True)
    assert len(flowables) >= 12, f"expected a flowable per construct, got {len(flowables)}"

    from reportlab.platypus import Table

    assert any(isinstance(f, Table) for f in flowables), "markdown table was dropped"


def test_table_cells_with_pipes_and_markup_do_not_break_rendering():
    """Report tables quote curriculum text, so angle brackets and ampersands
    are ordinary content and must not be read as ReportLab markup."""
    styles = _styles()
    md = "| Doc | Note |\n|---|---|\n| a<b>c | Tom & Jerry |\n"
    flowables = md_to_flowables(md, styles)
    from reportlab.platypus import Table

    assert any(isinstance(f, Table) for f in flowables)


def test_appendix_table_is_recovered_from_generated_html():
    """The year grid has no Markdown equivalent inside the report, so it is
    lifted out of the HTML we generate ourselves in year_at_a_glance_html."""
    styles = _styles()
    from pdf_theme.render import year_at_a_glance_html

    html = year_at_a_glance_html(
        {
            "school_year": "2026-2027",
            "summary": {"units_placed": 2, "instructional_days_consumed": 4},
            "year_at_a_glance": {
                "grading_period_columns": [{"id": "gp1", "label": "Q1"}],
                "unit_rows": [
                    {
                        "unit_id": "immune",
                        "title": "Immune",
                        "grading_periods_spanned": ["gp1"],
                    }
                ],
            },
        }
    )
    assert html, "fixture should produce appendix html"
    flowables = _appendix_flowables(html, styles)
    from reportlab.platypus import Table

    assert any(isinstance(f, Table) for f in flowables)

    # No appendix means no page break and no empty heading.
    assert _appendix_flowables("", styles) == []
    assert _appendix_flowables("<section><p>no table here</p></section>", styles) == []


def test_writes_a_real_pdf_with_the_expected_text(tmp_path=None):
    import tempfile

    tmp = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    pdf = tmp / "packet.pdf"
    render_packet_pdf_reportlab(
        pdf_path=pdf,
        project_id="sample-cte-demo",
        unit_id="immune",
        title="Teacher packet \u2014 Immune",
        doc_kind="Teacher packet",
        md_text="## Findings\n\nOne element was **unverified**.\n\n"
        "| Unit | Missing |\n|---|---|\n| immune | 2 |\n",
    )
    assert pdf.is_file(), "no PDF written"
    head = io.open(pdf, "rb").read(5)
    assert head == b"%PDF-", f"not a PDF: {head!r}"
    assert pdf.stat().st_size > 1500, "suspiciously small PDF"

    # Read it back so the test fails if the page is blank.
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    doc = pdfium.PdfDocument(str(pdf))
    text = doc[0].get_textpage().get_text_range()
    assert "Findings" in text
    assert "unverified" in text
    assert "immune" in text
    assert "page 1" in text, "page furniture missing"


if __name__ == "__main__":
    for fn in [
        test_pdf_theme_imports_without_gtk,
        test_glyphs_outside_winansi_are_replaced_not_mangled,
        test_markdown_constructs_all_produce_flowables,
        test_table_cells_with_pipes_and_markup_do_not_break_rendering,
        test_appendix_table_is_recovered_from_generated_html,
        test_writes_a_real_pdf_with_the_expected_text,
    ]:
        fn()
        print(f"OK {fn.__name__}")
    print("ALL TESTS PASSED")
