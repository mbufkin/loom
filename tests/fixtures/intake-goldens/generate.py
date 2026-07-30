"""Deterministic office-format generators for intake goldens.

Best practice: keep binary formats out of git; rebuild them in pytest setup from
fixed strings so CI stays small and reproducible. Text seeds (md/txt/html) are
committed under each pack's seeds/ directory.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def write_docx(path: Path, text: str) -> None:
    """Minimal OOXML docx with one paragraph of text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Escape XML special chars so generator input can include <>& safely.
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{safe}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_DOCX)
        zf.writestr("word/document.xml", document_xml)


def write_pptx(path: Path, text: str) -> None:
    """Minimal pptx with one slide containing text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/>"
        "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>"
        "<p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Title\"/><p:cNvSpPr/>"
        "<p:nvPr/></p:nvSpPr><p:spPr/>"
        f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{safe}</a:t></a:r></a:p>"
        "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_PPTX)
        zf.writestr("ppt/slides/slide1.xml", slide)
        zf.writestr("ppt/presentation.xml", _PPT_PRESENTATION)
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            _PPT_RELS,
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            "</Relationships>",
        )


def write_xlsx(path: Path, text: str) -> None:
    """Minimal xlsx with sharedStrings so Loom's extractor returns text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'count="1" uniqueCount="1">'
        f"<si><t>{safe}</t></si></sst>"
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>'
        "</worksheet>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XLSX)
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets>'
            '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )


def write_pdf(path: Path, text: str) -> None:
    """Write a one-page PDF via reportlab (runtime dep) so pdftotext can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Simple wrapping: put text near top-left; goldens only need extractable chars.
    y = 720
    for line in text.splitlines() or [text]:
        c.drawString(72, y, line[:100])
        y -= 14
        if y < 72:
            break
    c.save()
    path.write_bytes(buf.getvalue())


def materialize_pack(pack_dir: Path, dest_sources: Path, *, formats: list[str]) -> list[str]:
    """Copy seeds/ into dest_sources and generate requested office files.

    Returns relative paths of files that were skipped because a tool/lib was missing.
    """
    import shutil

    seeds = pack_dir / "seeds"
    dest_sources.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []

    if seeds.is_dir():
        for src in seeds.rglob("*"):
            if not src.is_file() or src.name.startswith("."):
                continue
            rel = src.relative_to(seeds)
            target = dest_sources / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    # One short curriculum snippet per generated format (deterministic content).
    snippets = {
        "docx": "Day 1 Lesson Plan — DOCX seed for intake golden.",
        "pptx": "Day 1 Slides — PPTX seed for intake golden.",
        "xlsx": "Day 1 Roster — XLSX seed for intake golden.",
        "pdf": "Day 1 Overview — PDF seed for intake golden.",
    }
    writers = {
        "docx": write_docx,
        "pptx": write_pptx,
        "xlsx": write_xlsx,
        "pdf": write_pdf,
    }
    for fmt in formats:
        if fmt in ("md", "txt", "html", "markdown"):
            continue  # committed seeds
        writer = writers.get(fmt)
        if writer is None:
            skipped.append(f"unsupported_format:{fmt}")
            continue
        out = dest_sources / f"generated-day1.{fmt}"
        try:
            writer(out, snippets[fmt])
        except Exception as e:  # noqa: BLE001 — surface as skip, don't abort pack
            skipped.append(f"{fmt}:{e}")
            if out.exists():
                out.unlink()
    return skipped


_CONTENT_TYPES_DOCX = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

_CONTENT_TYPES_PPTX = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
</Types>
"""

_CONTENT_TYPES_XLSX = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
"""

_PPT_PRESENTATION = """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>
"""

_PPT_RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
"""
