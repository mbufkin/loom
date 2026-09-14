"""Packet PDF orchestrator: WeasyPrint when it can run, ReportLab when it cannot."""

from __future__ import annotations

import html
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pdf_theme.md_to_html import md_to_html
from pdf_theme.reportlab_render import render_packet_pdf_reportlab


_ENGINE: tuple | None = None
_PROBED = False


@contextmanager
def _quiet_probe():
    """Silence the WeasyPrint import probe at file-descriptor level.

    Both descriptors, because WeasyPrint prints this particular banner to
    STDOUT -- which is why redirect_stderr missed it and why suppressing fd 2
    alone still left it in the run log, where it sat directly above our own
    "using the ReportLab renderer" line telling the reader the opposite.

    Held only for the duration of the import and restored in a finally, so the
    rest of the process keeps its output. Worth the file-descriptor work rather
    than leaving advice to "report an issue" in the log of a run that produced
    every report it promised.
    """
    saved = (os.dup(1), os.dup(2))
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(devnull)
        os.close(saved[0])
        os.close(saved[1])


def _weasyprint():
    """Import WeasyPrint on demand, or return None if it cannot run here.

    Deliberately NOT a module-level import. WeasyPrint's Python package installs
    from pip fine and then raises OSError at import time when its GTK/Pango
    libraries are missing, which is the normal state of a Windows machine. With
    the import at module scope that failure took the whole pdf_theme package
    down, so every caller lost PDFs -- including the ReportLab path, which has
    no native dependencies and would have worked.

    Probed once and remembered: a run renders a PDF per unit plus the global
    report, and on a machine without the libraries each attempt otherwise
    reprints WeasyPrint's multi-line "follow the installation steps before
    reporting an issue" banner. That advice is misleading once a working
    fallback exists, so the banner is swallowed here and the caller says which
    engine it used instead.
    """
    global _ENGINE, _PROBED
    if _PROBED:
        return _ENGINE
    _PROBED = True
    try:
        with _quiet_probe():
            from weasyprint import CSS, HTML
        _ENGINE = (CSS, HTML)
    except Exception:
        _ENGINE = None
    return _ENGINE

THEME_ROOT = Path(__file__).resolve().parents[1] / "assets" / "pdf"
TEMPLATES = THEME_ROOT / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


_ANNOUNCED = False


def _announce_fallback() -> None:
    """Say which engine is rendering, once per run rather than once per packet.

    Silence would be worse than the old banner: the PDFs look different from the
    print theme, and whoever opens them should know why without having to guess
    whether something is broken.
    """
    global _ANNOUNCED
    if _ANNOUNCED:
        return
    _ANNOUNCED = True
    from audit_lib import log

    log(
        "PDF: using the ReportLab renderer (WeasyPrint's GTK/Pango libraries are "
        "not installed). Reports are complete; they do not carry the full print "
        "theme. Install GTK to get it."
    )


def render_packet_pdf(
    *,
    pdf_path: Path,
    project_id: str,
    title: str,
    doc_kind: str,
    md_text: str,
    unit_id: str | None = None,
    appendix_html: str = "",
) -> Path:
    """Wrap markdown body in the Crystallize print shell and write a Letter PDF.

    WeasyPrint stays preferred: it renders the real print theme. ReportLab is
    the fallback rather than the default because it draws flowables instead of
    CSS, so it reproduces the structure and palette but not the full theme.
    Same preferred-if-present arrangement bootstrap.py describes for poppler
    over PDFium.
    """
    engine = _weasyprint()
    if engine is None:
        _announce_fallback()
        return render_packet_pdf_reportlab(
            pdf_path=pdf_path,
            project_id=project_id,
            title=title,
            doc_kind=doc_kind,
            md_text=md_text,
            unit_id=unit_id,
            appendix_html=appendix_html,
        )
    CSS, HTML = engine

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    running_meta = project_id if not unit_id else f"{project_id} · {unit_id}"
    body_html = md_to_html(md_text, skip_h1=True)

    html = _env().get_template("document.html.j2").render(
        title=title,
        doc_kind=doc_kind,
        project_id=project_id,
        unit_id=unit_id or "",
        generated_at=generated_at,
        running_meta=running_meta,
        body_html=body_html,
        appendix_html=appendix_html,
    )

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    # Base URL must be the assets/pdf dir so relative CSS/fonts/SVG resolve.
    HTML(string=html, base_url=str(THEME_ROOT)).write_pdf(
        str(pdf_path),
        stylesheets=[CSS(filename=str(THEME_ROOT / "base.css"))],
    )
    return pdf_path


def year_at_a_glance_html(pacing: dict) -> str:
    """HTML appendix for inferred pacing year map (global report only)."""
    yag = pacing.get("year_at_a_glance") or {}
    cols = yag.get("grading_period_columns") or []
    rows = yag.get("unit_rows") or []
    if not cols or not rows:
        return ""

    summary = pacing.get("summary") or {}
    avail = summary.get("instructional_days_available")
    avail_text = f" / {avail}" if avail is not None else ""
    school_year = html.escape(str(pacing.get("school_year") or "—"))

    parts: list[str] = [
        '<section class="yag-block">',
        "<h2>Year at a Glance (inferred pacing)</h2>",
        '<p class="lede"><em>Structural map from rollup.py — not Layer 1 conformance findings.</em></p>',
        '<p class="yag-summary">',
        f"<strong>School year:</strong> {school_year} &nbsp;·&nbsp; ",
        f"<strong>Units placed:</strong> {html.escape(str(summary.get('units_placed', 0)))} &nbsp;·&nbsp; ",
        f"<strong>Instructional days used:</strong> "
        f"{html.escape(str(summary.get('instructional_days_consumed', '—')))}"
        f"{html.escape(avail_text)}",
        "</p>",
        "<table><thead><tr><th>Unit</th>",
    ]
    for c in cols:
        label = html.escape((c.get("label") or c.get("id") or "")[:18])
        parts.append(f"<th>{label}</th>")
    parts.append("</tr></thead><tbody>")

    col_ids = [c.get("id", "") for c in cols]
    for row in rows:
        title = html.escape((row.get("title") or row["unit_id"])[:28])
        parts.append(f"<tr><td><strong>{title}</strong></td>")
        spans = set(row.get("grading_periods_spanned") or [])
        for cid in col_ids:
            if cid in spans:
                start = row.get("start_date") or ""
                end = row.get("end_date") or ""
                if start and end:
                    cell = html.escape(f"{start[5:]} → {end[5:]}")
                else:
                    cell = "●"
            else:
                cell = "—"
            parts.append(f"<td>{cell}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></section>")
    return "".join(parts)
