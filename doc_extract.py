"""
doc_extract.py — Extract plain text from any common curriculum file type.

Used before scrub/ingest. Adds formats without changing the audit pipeline.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
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
        raise RuntimeError("pdftotext not installed (apt: poppler-utils)") from None


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


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
