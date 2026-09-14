"""
doc_extract.py — Extract plain text from any common curriculum file type.

Used before scrub/ingest. Adds formats without changing the audit pipeline.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

# Extensions we attempt to read (lowercase). Add new types here.
TEXT_EXTENSIONS = {".txt", ".text", ".md", ".markdown", ".csv", ".log", ".rst"}
HTML_EXTENSIONS = {".html", ".htm"}
ZIP_XML_EXTENSIONS = {
    ".docx": "word/document.xml",
    ".pptx": "ppt/slides",
    ".odt": "content.xml",
}
PDF_EXTENSIONS = {".pdf"}
LEGACY_EXTENSIONS = {".doc", ".ppt", ".xls", ".rtf"}

SUPPORTED_EXTENSIONS = (
    TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | set(ZIP_XML_EXTENSIONS)
    | PDF_EXTENSIONS
    | LEGACY_EXTENSIONS
    | {".xlsx"}
)

SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp3",
    ".mp4",
    ".wav",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".gguf",
    ".pyc",
    ".py",
}


def iter_source_files(sources: Path, recursive: bool = True) -> list[Path]:
    """Curriculum files under sources/ (optionally nested folders)."""
    if not sources.is_dir():
        return []
    iterator = sources.rglob("*") if recursive else sources.iterdir()
    out = []
    for p in sorted(iterator):
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext in SKIP_EXTENSIONS:
            continue
        out.append(p)
    return out


def _xml_texts(root: ET.Element, tag_local: str) -> list[str]:
    parts = []
    for el in root.iter():
        if el.tag.endswith(tag_local) and el.text:
            parts.append(el.text)
        if el.tag.endswith(tag_local) and el.tail:
            parts.append(el.tail)
    return parts


def _extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(_xml_texts(root, "t"))


def _extract_pptx(path: Path) -> str:
    chunks = []
    with zipfile.ZipFile(path) as zf:
        slide_names = sorted(
            n
            for n in zf.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        for name in slide_names:
            root = ET.fromstring(zf.read(name))
            chunks.append("\n".join(_xml_texts(root, "t")))
    return "\n\n".join(chunks)


def _extract_odt(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("content.xml")
    root = ET.fromstring(xml)
    return "\n".join(_xml_texts(root, "p")) or "\n".join(_xml_texts(root, "span"))


def _local(tag: str) -> str:
    """Tag name without its namespace: '{...spreadsheetml/2006/main}c' -> 'c'."""
    return tag.rpartition("}")[2]


def _rich_text(el: ET.Element) -> str:
    """
    Flatten one OOXML string element -- an <si> from the shared-string table or
    an <is> from a cell -- into the string a reader would see.

    Only direct children are walked, which is the point rather than an
    optimisation. A styled string is stored as one <r> run per formatting
    change, each carrying its own <t>, and those runs are one value that
    happens to be bold in the middle -- so they concatenate with no separator.
    Walking the whole subtree instead would also pick up <rPh>, the phonetic
    guide used for Japanese text, and interleave pronunciation hints into the
    content.
    """
    parts = []
    for child in el:
        name = _local(child.tag)
        if name == "t":
            parts.append(child.text or "")
        elif name == "r":
            parts.extend(t.text or "" for t in child if _local(t.tag) == "t")
    return "".join(parts)


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """
    The workbook's shared-string table, indexed as the sheets expect.

    One entry per <si>, built whole. Collecting every <t> in the file into one
    flat list instead would silently shift every index after the first styled
    cell, because a styled string contributes several <t> elements and the
    sheets refer to strings by position.
    """
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except ET.ParseError:
        return []
    return [_rich_text(si) for si in root if _local(si.tag) == "si"]


def _sheet_parts(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """
    (sheet name, zip part) for each worksheet, in the tab order Excel shows.

    Resolved through workbook.xml and its relationships rather than by globbing
    worksheets/, because sheet names are content in their own right -- a tab
    called "Cutting bays and consumables" says what the numbers under it are --
    and because sheet1.xml is not reliably the first tab once sheets have been
    reordered or deleted. Falls back to numeric filename order if either part
    is missing or unreadable, which still beats returning nothing.
    """
    parts = [
        n
        for n in zf.namelist()
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    ]

    def by_number(name: str) -> tuple[int, str]:
        digits = re.search(r"(\d+)", Path(name).stem)
        return (int(digits.group(1)) if digits else 0, name)

    fallback = [("", n) for n in sorted(parts, key=by_number)]

    try:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError):
        return fallback

    # Relationship targets are written relative to xl/, but absolute forms
    # ("/xl/worksheets/sheet1.xml") are also valid, so normalise both.
    targets = {}
    for rel in rels:
        target = rel.get("Target", "").lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        targets[rel.get("Id")] = target

    out = []
    for sheet in workbook.iter():
        if _local(sheet.tag) != "sheet":
            continue
        rid = next((v for k, v in sheet.attrib.items() if _local(k) == "id"), None)
        part = targets.get(rid)
        if part in zf.namelist():
            out.append((sheet.get("name", ""), part))
    return out or fallback


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    """One cell's value as text, whichever way the writer chose to store it."""
    kind = cell.get("t", "n")

    if kind == "inlineStr":
        # Text written straight into the cell instead of into the shared-string
        # table. Both are valid OOXML and the table is only an optimisation for
        # repeated values, so a reader that handles one and not the other works
        # on some files and comes back empty on others. Excel prefers the
        # table; openpyxl, pandas .to_excel() and Google Sheets exports write
        # inline -- which is to say, most spreadsheets that were not last saved
        # by Excel itself.
        inline = next((c for c in cell if _local(c.tag) == "is"), None)
        return _rich_text(inline) if inline is not None else ""

    value = next((c for c in cell if _local(c.tag) == "v"), None)
    raw = (value.text or "") if value is not None else ""

    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "TRUE" if raw.strip() == "1" else "FALSE"
    if kind == "e":
        # An error value such as #REF! or #DIV/0!. Dropped rather than
        # reported: it is a broken formula, not something a teacher wrote.
        return ""

    # "n" (number) and "str" (a formula's string result) both keep their text
    # in <v>. Numbers come through as stored, so a date-formatted cell reads as
    # its serial number -- resolving that would mean parsing styles.xml for the
    # cell's number format, which is a larger job than this and has not been
    # needed yet. Dates typed as text, which is how they usually arrive in a
    # hand-kept inventory, are unaffected.
    return raw


def _extract_xlsx(path: Path) -> str:
    """
    Text from a workbook, one line per row, sheet names kept as headings.

    Rows are joined with " | " rather than split onto separate lines so that a
    value stays attached to the row it describes. "Booth 8 | Out of service |
    Primary lead insulation cracked" is a fact about booth 8; the same words
    one per line are three unrelated fragments, and that distinction is the
    whole reason a curriculum inventory is worth reading at all.
    """
    chunks = []
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        for sheet_name, part in _sheet_parts(zf):
            try:
                root = ET.fromstring(zf.read(part))
            except (KeyError, ET.ParseError):
                continue

            rows = []
            for row in root.iter():
                if _local(row.tag) != "row":
                    continue
                cells = [
                    _cell_text(c, shared) for c in row if _local(c.tag) == "c"
                ]
                # Trailing blanks are formatting, not data -- a row styled to
                # the edge of the used range should not end in empty columns.
                while cells and not cells[-1].strip():
                    cells.pop()
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))

            if rows:
                body = "\n".join(rows)
                chunks.append(f"## {sheet_name}\n{body}" if sheet_name else body)

    return "\n\n".join(chunks)


def _extract_pdf(path: Path) -> str:
    # Deliberately NOT using pdftotext's `-layout` flag. `-layout` tells poppler to
    # preserve each line of text at its literal physical X position on the page —
    # useful for a simple single-column report with whitespace-aligned columns, but
    # actively destructive on any real multi-column layout (textbooks, academic
    # frameworks, credits pages): poppler walks the page top-to-bottom and stitches
    # together whatever text sits at the same Y position *regardless of which
    # column it's in*, interleaving unrelated columns word-by-word into nonsense.
    #
    # Confirmed empirically (2026-07-07, see docs/roadmap.md #7): on the AP CSP CED
    # framework PDF, `-layout` mode produced "Learning objectives definewhatastudent
    # shouldbeableto do..." — a sidebar column's words merged mid-sentence into the
    # main column's text, with spaces even dropped between words. Without `-layout`,
    # poppler instead uses its own reading-order heuristics (still spatial, not raw
    # PDF-stream order) and reconstructs the same passage as clean, correctly
    # separated prose. Verified this isn't a one-off: same interleaving pattern
    # reproduced independently on an OpenSciEd teacher's-edition PDF's credits page
    # (three name columns merged into one garbled line under `-layout`, one clean
    # name per line by default). Verified no regression either: single-column
    # tables of contents and pacing tables extract equally cleanly both ways — the
    # only difference there is `-layout` keeps a table row on one line while default
    # mode adds extra line breaks, which is a cosmetic difference a model reading
    # full text handles fine, not an information loss.
    #
    # Best-practice takeaway for future readers: don't reach for a "preserve
    # layout" flag by default just because it sounds safer — test it against your
    # actual documents. For genuinely multi-column source material, format-aware
    # extraction (e.g. PyMuPDF block/column detection, or OCR) still beats plain
    # `pdftotext` in principle, but the free win here (removing a flag that was
    # actively making things worse) was worth taking immediately; a heavier
    # extraction pipeline remains a future option if this default mode still
    # proves insufficient on some other document.
    try:
        result = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        return result.stdout
    except FileNotFoundError:
        # Poppler is a system package, not a Python one: it needs a package
        # manager and, on Windows, usually admin rights. Districts hand this
        # program to curriculum staff on locked-down machines, so requiring it
        # meant the program could not read a PDF on the very computers it is
        # meant for. Fall back to PDFium, which ships as an ordinary wheel on
        # every platform and installs with the rest of the dependencies.
        #
        # Fallback rather than replacement on purpose: the no-`-layout` poppler
        # behaviour above was tuned against real multi-column curriculum PDFs,
        # and the existing intake goldens were recorded from it. Preferring
        # poppler when it is present keeps those outputs byte-identical.
        return _extract_pdf_pdfium(path)


def _extract_pdf_pdfium(path: Path) -> str:
    """Extract PDF text with PDFium, the engine Chrome uses to display PDFs.

    Its text layer walks the page in reading order rather than raw PDF-stream
    order, which is the same property that made plain `pdftotext` beat
    `pdftotext -layout` on multi-column material (see the note above).
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError(
            "Cannot read PDF files: neither pdftotext nor pypdfium2 is "
            "available. Install the Python dependencies "
            "(pip install -r requirements.txt), or install poppler."
        ) from None

    doc = pdfium.PdfDocument(str(path))
    try:
        pages = []
        for page in doc:
            textpage = page.get_textpage()
            try:
                pages.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
        # Poppler separates pages with a form feed; match it so anything
        # downstream that counts or splits on pages behaves the same either way.
        return "\f".join(pages)
    finally:
        doc.close()


def _extract_legacy_doc(path: Path) -> str:
    try:
        result = subprocess.run(
            ["antiword", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except FileNotFoundError:
        pass
    return ""


# Tags that end one idea and begin the next. Layer 0 asks the model to cite
# evidence by paragraph number and resolves the quote from our own paragraph
# list, so paragraph boundaries ARE the citation granularity: if a document
# arrives as one unbroken run of text, every element can only legally point at
# paragraph 1 and the resolved excerpt becomes the whole document. Marking
# these as blank lines is what gives number_paragraphs() something to split on.
_HTML_BLOCK_TAGS = (
    "p|div|br|li|dt|dd|tr|h[1-6]|section|article|header|footer|nav|aside"
    "|blockquote|pre|figure|figcaption|hr|table|thead|tbody|tfoot|ul|ol|dl|form"
)

# Table cells are the exception: breaking every <td> onto its own paragraph
# shreds a row into meaningless fragments, so cells get a plain space and only
# the row (<tr>, above) becomes a boundary.
_HTML_CELL_TAGS = "td|th"


def _strip_html(markup: str) -> str:
    """Flatten HTML to text while preserving paragraph structure.

    Named `markup` rather than `html` so it does not shadow the stdlib `html`
    module we rely on for entity decoding.
    """
    # Script and style bodies are code, not prose - drop them wholesale before
    # any other rule can turn their contents into "text".
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", markup, flags=re.I)

    # Whitespace is insignificant in HTML, so a pretty-printed file wraps
    # sentences mid-phrase. Flatten the source's own newlines FIRST and every
    # newline that remains is one we deliberately inserted below - otherwise
    # the file's line wrapping shows up as breaks inside a quoted excerpt
    # ("B\nCells"). Trade-off: <pre> whitespace is not preserved, which these
    # curriculum exports do not rely on.
    text = re.sub(r"\s+", " ", text)

    # Order matters: convert boundaries to blank lines BEFORE stripping tags,
    # because once every tag is a space the structure is unrecoverable.
    text = re.sub(rf"<\s*/?\s*(?:{_HTML_CELL_TAGS})\b[^>]*>", " ", text, flags=re.I)
    text = re.sub(rf"<\s*/?\s*(?:{_HTML_BLOCK_TAGS})\b[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode entities only now that markup is gone, so a literal "&lt;p&gt;" in
    # the source is never mistaken for a real tag. Without this, "&nbsp;" and
    # "&amp;" reach the model's prompt and any excerpt quoted in a report.
    text = unescape(text)

    # A non-breaking space reads as a space but is not one; normalise it so it
    # collapses with the run below instead of surviving inside excerpts.
    text = text.replace("\u00a0", " ")

    # Collapse only horizontal whitespace. Using \s+ here (as this once did)
    # eats the newlines above and returns every document to a single paragraph.
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(path: Path) -> tuple[str, str]:
    """
    Extract text from path.
    Returns (text, method) where method describes how it was extracted.
    Raises ValueError if unsupported or empty.
    """
    ext = path.suffix.lower()

    if ext in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="replace"), "text"

    if ext in HTML_EXTENSIONS:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _strip_html(raw), "html"

    if ext == ".docx":
        return _extract_docx(path), "docx"

    if ext == ".pptx":
        return _extract_pptx(path), "pptx"

    if ext == ".odt":
        return _extract_odt(path), "odt"

    if ext == ".xlsx":
        return _extract_xlsx(path), "xlsx"

    if ext in PDF_EXTENSIONS:
        return _extract_pdf(path), "pdf"

    if ext == ".doc":
        text = _extract_legacy_doc(path)
        if text.strip():
            return text, "antiword"
        raise ValueError(
            ".doc requires antiword (apt install antiword) or convert to .docx"
        )

    if ext == ".rtf":
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Minimal RTF strip — good enough for audit, not a full parser
        text = re.sub(r"\\[a-z]+\d* ?", " ", raw)
        text = re.sub(r"[{}]", "", text)
        return text, "rtf-basic"

    # Unknown: try plain text, then PDF magic
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
        if raw.strip():
            return raw, "text-fallback"
    except (UnicodeDecodeError, OSError):
        pass

    with open(path, "rb") as f:
        if f.read(5) == b"%PDF-":
            return _extract_pdf(path), "pdf-magic"

    raise ValueError(f"unsupported or binary file type: {ext or '(no extension)'}")


def extract_with_meta(path: Path) -> dict:
    """Extract text and return metadata for evidence scrubbing."""
    ext = path.suffix.lower()
    try:
        text, method = extract_text(path)
    except ValueError as e:
        return {
            "source_file": path.name,
            "source_format": ext or "unknown",
            "extraction_method": "failed",
            "extraction_error": str(e),
            "content_clean": "",
        }
    if not text.strip():
        return {
            "source_file": path.name,
            "source_format": ext or "unknown",
            "extraction_method": method,
            "extraction_error": "no text extracted",
            "content_clean": "",
        }
    return {
        "source_file": path.name,
        "source_format": ext or "unknown",
        "extraction_method": method,
        "raw_text": text,
    }
