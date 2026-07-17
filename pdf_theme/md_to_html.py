"""Markdown-lite → semantic HTML for Crystallize print PDFs.

Mirrors the heading / list / table / bold / code rules previously used by
render_pdf.md_to_flowables so existing MD plates render without content changes.
"""

from __future__ import annotations

import html
import re


def _inline(text: str) -> str:
    """Escape, then apply **bold** and `code` — same contract as table cells."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _is_table_sep(line: str) -> bool:
    return bool(line) and set(line) <= set("|-: ") and "-" in line


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def _status_chip(cell: str) -> str | None:
    """Optional chip wrapping for common status tokens in inventory tables."""
    raw = cell.strip()
    key = re.sub(r"[^A-Za-z]", "", raw).upper()
    mapping = {
        "PRESENT": "present",
        "MISSING": "missing",
        "MISPLACED": "misplaced",
        "ABSENT": "absent",
        "NOTFOUND": "missing",
        "BLANK": "absent",
    }
    kind = mapping.get(key)
    if not kind:
        return None
    return f'<span class="chip chip-{kind}">{_inline(raw)}</span>'


def _table_html(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header, body = rows[0], rows[1:]
    parts = ['<table><thead><tr>']
    for c in header:
        parts.append(f"<th>{_inline(c)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        for i in range(len(header)):
            cell = row[i] if i < len(row) else ""
            chip = _status_chip(cell)
            parts.append(f"<td>{chip if chip else _inline(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def md_to_html(md_text: str, *, skip_h1: bool = True) -> str:
    """Convert GLOBAL-AUDIT / teacher / unit / lesson markdown into HTML fragments."""
    out: list[str] = []
    lines = md_text.splitlines()
    i = 0
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("|"):
            close_lists()
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = [_split_table_row(b) for b in block if not _is_table_sep(b)]
            if rows:
                out.append(_table_html(rows))
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        # Horizontal rule used as section breaks in plates (---)
        if stripped in ("---", "***", "___") or re.fullmatch(r"-{3,}", stripped):
            close_lists()
            out.append("<hr/>")
            i += 1
            continue

        if stripped.startswith("# "):
            close_lists()
            if not skip_h1:
                out.append(f"<h1>{_inline(stripped[2:])}</h1>")
            i += 1
            continue

        if stripped.startswith("## "):
            close_lists()
            out.append(f"<h2>{_inline(stripped[3:])}</h2>")
            i += 1
            continue

        if stripped.startswith("### "):
            close_lists()
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
            i += 1
            continue

        if stripped.startswith("- "):
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        close_lists()
        # Soft italic for whole-line emphasis used in plates (*note*)
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            out.append(f"<p><em>{_inline(stripped.strip('*'))}</em></p>")
        else:
            out.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    close_lists()
    return "\n".join(out)


def extract_h1(md_text: str, default: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return default
