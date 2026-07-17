"""WeasyPrint orchestrator for Crystallize packet PDFs."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML

from pdf_theme.md_to_html import md_to_html

THEME_ROOT = Path(__file__).resolve().parents[1] / "assets" / "pdf"
TEMPLATES = THEME_ROOT / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
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
    """Wrap markdown body in the Crystallize print shell and write a Letter PDF."""
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
