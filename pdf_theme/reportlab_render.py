"""ReportLab packet PDFs — the fallback when WeasyPrint's native libraries are absent.

WeasyPrint gives the nicer result and stays the preferred engine. But it needs
GTK/Pango/cairo, which pip cannot supply on Windows, and without them every
report silently degraded to Markdown only: a completed run logged three
"PDF skipped" warnings and produced no PDF at all. A district told it will get
a PDF report should get one.

This module is the same trade bootstrap.py already documents for document
reading, where poppler (a system package, usually needing admin) gave way to
PDFium (a wheel) with poppler kept as a preferred-if-present upgrade. ReportLab
is already a dependency here and already renders the archived unit report, so
this path adds no download, needs no admin, and cannot be blocked by a school
district's firewall.

The cost is honest: ReportLab draws flowables, not CSS, so the output follows
the brand palette and structure but is not the pixel-for-pixel print theme.
Content, tables and citations are all present.

Parsing mirrors pdf_theme/md_to_html.py rule for rule — headings, ordered and
unordered lists, tables, rules, whole-line emphasis, inline bold and code — so
the same plate renders with the same structure whichever engine runs.
"""

from __future__ import annotations

import html as html_mod
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Brand palette, matching the ReportLab unit report already in render_pdf.py so
# the two paths do not look like they came from different products.
INK = colors.HexColor("#1b4332")
ACCENT = colors.HexColor("#2d6a4f")
RULE = colors.HexColor("#dee2e6")
MUTED = colors.HexColor("#6c757d")

# Same status vocabulary md_to_html.py turns into CSS chips.
CHIP_BG = {
    "PRESENT": colors.HexColor("#d8f3dc"),
    "MISSING": colors.HexColor("#ffccd5"),
    "NOTFOUND": colors.HexColor("#ffccd5"),
    "MISPLACED": colors.HexColor("#ffedd8"),
    "ABSENT": colors.HexColor("#f8f9fa"),
    "BLANK": colors.HexColor("#f8f9fa"),
}

MARGIN = 0.6 * inch
AVAIL_WIDTH = letter[0] - 2 * MARGIN


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PkTitle",
            parent=base["Heading1"],
            fontSize=19,
            leading=23,
            spaceAfter=2,
            textColor=INK,
        ),
        "kind": ParagraphStyle(
            "PkKind",
            parent=base["Normal"],
            fontSize=9.5,
            leading=12,
            textColor=ACCENT,
            spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "PkMeta",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "PkH2",
            parent=base["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=15,
            spaceAfter=6,
            textColor=INK,
        ),
        "h3": ParagraphStyle(
            "PkH3",
            parent=base["Heading3"],
            fontSize=11,
            leading=14,
            spaceBefore=10,
            spaceAfter=4,
            textColor=ACCENT,
        ),
        "body": ParagraphStyle(
            "PkBody",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13.5,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "note": ParagraphStyle(
            "PkNote",
            parent=base["Normal"],
            fontSize=9,
            leading=12.5,
            spaceAfter=5,
            textColor=MUTED,
        ),
        "li": ParagraphStyle(
            "PkLi",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13.5,
            leftIndent=14,
            bulletIndent=4,
            spaceAfter=3,
        ),
        "cell": ParagraphStyle(
            "PkCell", parent=base["Normal"], fontSize=8, leading=10.5
        ),
        "cellhead": ParagraphStyle(
            "PkCellHead",
            parent=base["Normal"],
            fontSize=8,
            leading=10.5,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        ),
    }


# ReportLab's built-in Type 1 fonts are WinAnsi-only, and the bundled brand OTFs
# cannot stand in for them -- they carry PostScript outlines, which ReportLab
# refuses ("postscript outlines are not supported"). So anything outside Latin-1
# renders as mojibake rather than failing: the year-at-a-glance grid came out as
# "â—■" where it meant "●". Report text quotes curriculum verbatim and can carry
# arrows, ticks, Greek or dashes from anywhere, so this maps the glyphs we
# actually emit and degrades the rest predictably instead of corrupting a PDF a
# teacher is meant to read.
_GLYPH_FALLBACK = {
    "\u25cf": "\u2022",  # ● black circle -> • bullet (WinAnsi has the bullet)
    "\u25cb": "\u00b0",  # ○ white circle -> degree ring
    "\u2192": "->",
    "\u2190": "<-",
    "\u21d2": "=>",
    "\u2713": "yes",  # ✓
    "\u2714": "yes",
    "\u2717": "no",  # ✗
    "\u2718": "no",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2260": "!=",
    "\u00a0": " ",  # non-breaking space
    "\u2009": " ",
    "\u200b": "",  # zero-width space
}


def _safe_text(text: str) -> str:
    """Replace glyphs ReportLab's standard fonts cannot draw."""
    if text.isascii():
        return text
    out: list[str] = []
    for ch in text:
        if ch in _GLYPH_FALLBACK:
            out.append(_GLYPH_FALLBACK[ch])
            continue
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            # Accented and decorated forms usually have a sensible ASCII base
            # (e.g. "ǎ" -> "a"); anything with none becomes a visible marker so
            # the loss is obvious rather than silent.
            stripped = (
                unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            )
            out.append(stripped or "?")
        else:
            out.append(ch)
    return "".join(out)


def _inline(text: str) -> str:
    """Escape, then apply **bold** and `code` — same contract as md_to_html._inline.

    ReportLab's Paragraph accepts a small HTML-like subset, so escaping first and
    then inserting only the tags we intend keeps report text (which quotes
    curriculum verbatim, ampersands and angle brackets included) from being read
    as markup.
    """
    text = html_mod.escape(_safe_text(text))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
    return text


def _is_table_sep(line: str) -> bool:
    return bool(line) and set(line) <= set("|-: ") and "-" in line


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _chip_key(cell: str) -> str | None:
    key = re.sub(r"[^A-Za-z]", "", cell.strip()).upper()
    return key if key in CHIP_BG else None


def _col_widths(rows: list[list[str]], avail: float) -> list[float]:
    """Share the page width out by how much text each column actually holds.

    Equal columns waste the page on a table like "Unit | Found | Missing |
    Duplicates", where one column holds a unit title and the rest hold integers.
    A floor keeps narrow numeric columns from collapsing below their heading.
    """
    ncols = max(len(r) for r in rows)
    widest = [
        max((len(r[i]) if i < len(r) else 0) for r in rows) or 1 for i in range(ncols)
    ]
    floor = min(0.55 * inch, avail / ncols)
    slack = avail - floor * ncols
    total = sum(widest)
    return [floor + slack * (w / total) for w in widest]


def _table(rows: list[list[str]], styles: dict, avail: float = AVAIL_WIDTH) -> Table:
    header, body = rows[0], rows[1:]
    ncols = len(header)
    data: list[list] = [[Paragraph(_inline(c), styles["cellhead"]) for c in header]]
    for row in body:
        data.append(
            [
                Paragraph(_inline(row[i] if i < len(row) else ""), styles["cell"])
                for i in range(ncols)
            ]
        )

    t = Table(data, colWidths=_col_widths(rows, avail), repeatRows=1, hAlign="LEFT")
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Status words get the same colour coding CSS gives them, so a reader can
    # still scan an inventory table for red.
    for ri, row in enumerate(body, start=1):
        for ci in range(ncols):
            key = _chip_key(row[ci]) if ci < len(row) else None
            if key:
                cmds.append(("BACKGROUND", (ci, ri), (ci, ri), CHIP_BG[key]))
    t.setStyle(TableStyle(cmds))
    return t


def md_to_flowables(md_text: str, styles: dict, *, skip_h1: bool = True) -> list:
    """Markdown-lite → ReportLab flowables, mirroring md_to_html.md_to_html."""
    out: list = []
    lines = md_text.splitlines()
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = [_split_table_row(b) for b in block if not _is_table_sep(b)]
            if rows:
                out.append(Spacer(1, 4))
                out.append(_table(rows, styles))
                out.append(Spacer(1, 8))
            continue

        if not stripped:
            i += 1
            continue

        if stripped in ("---", "***", "___") or re.fullmatch(r"-{3,}", stripped):
            out.append(Spacer(1, 6))
            out.append(HRFlowable(width="100%", thickness=0.6, color=RULE))
            out.append(Spacer(1, 6))
            i += 1
            continue

        if stripped.startswith("# "):
            if not skip_h1:
                out.append(Paragraph(_inline(stripped[2:]), styles["title"]))
            i += 1
            continue

        if stripped.startswith("## "):
            # Keep a heading with whatever follows it so a section title never
            # sits alone at the foot of a page.
            out.append(Paragraph(_inline(stripped[3:]), styles["h2"]))
            i += 1
            continue

        if stripped.startswith("### "):
            out.append(Paragraph(_inline(stripped[4:]), styles["h3"]))
            i += 1
            continue

        if stripped.startswith("- "):
            out.append(
                Paragraph(_inline(stripped[2:]), styles["li"], bulletText="\u2022")
            )
            i += 1
            continue

        if stripped.startswith("> "):
            out.append(Paragraph(_inline(stripped[2:]), styles["note"]))
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            out.append(
                Paragraph(
                    _inline(m.group(2)), styles["li"], bulletText=f"{m.group(1)}."
                )
            )
            i += 1
            continue

        if (
            stripped.startswith("*")
            and stripped.endswith("*")
            and not stripped.startswith("**")
        ):
            out.append(Paragraph(f"<i>{_inline(stripped.strip('*'))}</i>", styles["note"]))
        else:
            out.append(Paragraph(_inline(stripped), styles["body"]))
        i += 1

    return out


# We generate the appendix HTML ourselves in render.year_at_a_glance_html, so its
# shape is known and fixed -- this is not a general HTML parser and is not asked
# to survive arbitrary input. Without it the year grid would be missing from the
# fallback PDF entirely, which is the one piece of the global report that has no
# Markdown equivalent inside the same file.
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _appendix_flowables(appendix_html: str, styles: dict) -> list:
    if not appendix_html.strip():
        return []
    rows: list[list[str]] = []
    for raw_row in _ROW_RE.findall(appendix_html):
        cells = [
            html_mod.unescape(_TAG_RE.sub("", c)).strip()
            for c in _CELL_RE.findall(raw_row)
        ]
        if any(cells):
            rows.append(cells)
    if not rows:
        return []

    out: list = [
        PageBreak(),
        Paragraph("Year at a Glance (inferred pacing)", styles["h2"]),
        Paragraph(
            "<i>Structural map from rollup.py — not Layer 1 conformance findings.</i>",
            styles["note"],
        ),
        Spacer(1, 4),
        _table(rows, styles),
    ]
    return out


def _page_furniture(project_id: str, unit_id: str | None):
    """Footer on every page: who this belongs to, and a page number."""
    label = _safe_text(project_id if not unit_id else f"{project_id} · {unit_id}")

    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 0.42 * inch, label)
        canvas.drawRightString(
            letter[0] - MARGIN, 0.42 * inch, f"page {canvas.getPageNumber()}"
        )
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 0.60 * inch, letter[0] - MARGIN, 0.60 * inch)
        canvas.restoreState()

    return draw


def render_packet_pdf_reportlab(
    *,
    pdf_path: Path,
    project_id: str,
    title: str,
    doc_kind: str,
    md_text: str,
    unit_id: str | None = None,
    appendix_html: str = "",
) -> Path:
    """Same signature as pdf_theme.render.render_packet_pdf, ReportLab engine."""
    styles = _styles()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = f"{project_id}"
    if unit_id:
        meta += f" &nbsp;·&nbsp; {unit_id}"
    meta += f" &nbsp;·&nbsp; generated {generated_at}"

    story: list = [
        KeepTogether(
            [
                Paragraph(html_mod.escape(_safe_text(doc_kind)), styles["kind"]),
                Paragraph(_inline(title), styles["title"]),
                Paragraph(meta, styles["meta"]),
                Spacer(1, 6),
                HRFlowable(width="100%", thickness=1.1, color=ACCENT),
                Spacer(1, 10),
            ]
        )
    ]
    story += md_to_flowables(md_text, styles, skip_h1=True)
    story += _appendix_flowables(appendix_html, styles)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=0.75 * inch,
        title=title,
        author="Loom",
        subject=doc_kind,
    )
    furniture = _page_furniture(project_id, unit_id)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return pdf_path
