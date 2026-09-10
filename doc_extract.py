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


def _extract_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        if "xl/sharedStrings.xml" not in zf.namelist():
            return ""
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return "\n".join(_xml_texts(root, "t"))


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
