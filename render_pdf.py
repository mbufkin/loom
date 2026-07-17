#!/usr/bin/env python3
"""
render_pdf.py — Crystallize packet PDFs (HTML/CSS → WeasyPrint).

Live products (WeasyPrint + Crystallize brand theme):
  GLOBAL-AUDIT-REPORT.pdf, TEACHER-PACKET.pdf, UNIT-PLAN.pdf, LESSON-PLAN.pdf

Archived unit calendar-grid AUDIT-REPORT.pdf still uses ReportLab
(`render_unit_pdf`) until a later pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from audit_lib import load_yaml, log, project_dir, resolve_unit_paths
from pdf_theme import extract_h1, render_packet_pdf, year_at_a_glance_html
from report_lib import build_coverage_matrix

BASE = Path(__file__).resolve().parent

# --- Archived ReportLab path (unit AUDIT-REPORT only) -----------------------

STATUS_STYLE = {
    "present": ("Present", colors.HexColor("#2d6a4f"), colors.HexColor("#d8f3dc")),
    "missing": ("Missing", colors.HexColor("#9b2226"), colors.HexColor("#ffccd5")),
    "misplaced": ("Misplaced", colors.HexColor("#ca6702"), colors.HexColor("#ffedd8")),
    "absent": ("—", colors.HexColor("#6c757d"), colors.HexColor("#f8f9fa")),
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Heading1"],
            fontSize=18,
            spaceAfter=12,
            textColor=colors.HexColor("#1b4332"),
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=13,
            spaceBefore=14,
            spaceAfter=8,
            textColor=colors.HexColor("#1b4332"),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=10, leading=14, spaceAfter=4
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.grey,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["Normal"], fontSize=8, leading=10, alignment=TA_CENTER
        ),
    }


def _cell_paragraph(status: str, doc_id: str | None, styles: dict) -> Paragraph:
    label, _fg, _bg = STATUS_STYLE.get(status, ("?", colors.black, colors.white))
    if status == "present" and doc_id:
        text = f"<b>{label}</b><br/><font size='6'>{doc_id[:12]}</font>"
    elif status == "misplaced" and doc_id:
        text = f"<b>{label}</b><br/><font size='6'>{doc_id[:12]}*</font>"
    elif status == "missing":
        text = f"<b>{label}</b>"
    else:
        text = label
    return Paragraph(text, styles["cell"])


def coverage_table(matrix: dict, styles: dict) -> Table:
    """Calendar-first grid: rows = artifact types, columns = days."""
    day_cols = matrix["day_columns"]
    if not day_cols:
        return Table([["No calendar days defined"]])

    artifact_order: list[str] = []
    seen = set()
    for col in day_cols:
        for c in col["cells"]:
            if c["artifact"] not in seen:
                seen.add(c["artifact"])
                artifact_order.append(c["artifact"])

    header = ["Artifact"] + [f"{c['label']}\n({c['coverage_pct']}%)" for c in day_cols]
    data = [header]

    for art in artifact_order:
        row = [art.replace("_", " ").title()]
        for col in day_cols:
            cell = next((c for c in col["cells"] if c["artifact"] == art), None)
            if cell:
                doc_id = (cell.get("placement") or {}).get("doc_id")
                row.append(_cell_paragraph(cell["status"], doc_id, styles))
            else:
                row.append(_cell_paragraph("absent", None, styles))
        data.append(row)

    summary_row = [Paragraph("<b>Coverage</b>", styles["cell"])]
    for col in day_cols:
        summary_row.append(
            Paragraph(f"<b>{col['present']}/{col['expected']}</b>", styles["cell"])
        )
    data.append(summary_row)

    col_widths = [1.4 * inch] + [1.35 * inch] * len(day_cols)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4332")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9ecef")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for ri, art in enumerate(artifact_order, start=1):
        for ci, col in enumerate(day_cols, start=1):
            cell = next((c for c in col["cells"] if c["artifact"] == art), None)
            if cell:
                _label, _fg, bg = STATUS_STYLE.get(
                    cell["status"], ("", colors.black, colors.white)
                )
                style_cmds.append(("BACKGROUND", (ci, ri), (ci, ri), bg))
    t.setStyle(TableStyle(style_cmds))
    return t


def supporting_table(matrix: dict, styles: dict) -> Table | None:
    rows = matrix.get("supporting_rows", [])
    if not rows:
        return None
    data = [["Supporting artifact", "Status", "Document"]]
    for r in rows:
        if r["status"] == "present":
            docs = ", ".join(p.get("doc_id", "?")[:12] for p in r["placements"])
            data.append([r["artifact"].replace("_", " "), "Present", docs])
        else:
            data.append([r["artifact"].replace("_", " "), "Not in corpus", "—"])
    t = Table(data, colWidths=[2 * inch, 1.2 * inch, 3.3 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#495057")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def render_unit_pdf(
    project_id: str, unit_id: str, output_path: Path | None = None
) -> Path:
    """ARCHIVED: calendar coverage AUDIT-REPORT.pdf (ReportLab)."""
    root, manifest, unit, out_dir = resolve_unit_paths(project_id, unit_id)
    calendar = load_yaml(root / unit["calendar"])
    gap_path = out_dir / "02-gap-report.json"
    map_path = out_dir / "01-calendar-map.json"
    if not gap_path.is_file():
        raise FileNotFoundError(f"Run audit first: missing {gap_path}")

    gap = json.loads(gap_path.read_text())
    placements = (
        json.loads(map_path.read_text()) if map_path.is_file() else {"placements": []}
    )
    matrix = build_coverage_matrix(calendar, gap)

    pdf_path = output_path or (out_dir / "AUDIT-REPORT.pdf")
    styles = _styles()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    story = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story.append(Paragraph("Curriculum Audit Report", styles["title"]))
    story.append(Paragraph(f"<b>{matrix['title']}</b>", styles["h2"]))
    story.append(
        Paragraph(
            f"Project: {project_id} &nbsp;|&nbsp; Unit: {unit_id} &nbsp;|&nbsp; "
            f"Generated: {ts}<br/>"
            f"<i>Read-only auditor — findings only, no curriculum content generated.</i>",
            styles["small"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("1. Calendar Coverage", styles["h2"]))
    story.append(
        Paragraph(
            f"Unit coverage: <b>{matrix['unit_coverage_pct']}%</b> of expected day-slot artifacts are "
            f"placed on the correct calendar day. "
            f"<font color='#9b2226'>Red</font> = missing, "
            f"<font color='#2d6a4f'>green</font> = present, "
            f"<font color='#ca6702'>orange</font> = misplaced (exists but not on this day).",
            styles["body"],
        )
    )
    story.append(Spacer(1, 0.1 * inch))
    story.append(coverage_table(matrix, styles))
    story.append(Spacer(1, 0.15 * inch))

    sup = supporting_table(matrix, styles)
    if sup:
        story.append(Paragraph("Unit-level supporting materials", styles["body"]))
        story.append(sup)
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("2. Gap Findings", styles["h2"]))
    missing = matrix["missing_slots"]
    if missing:
        gap_data = [["Day", "Expected artifact", "Status"]]
        for m in missing:
            gap_data.append(
                [m.get("day_label", m.get("day_id")), m.get("expected", ""), "MISSING"]
            )
        gt = Table(gap_data, colWidths=[2 * inch, 2.2 * inch, 1.3 * inch])
        gt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9b2226")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(gt)
    else:
        story.append(
            Paragraph("No missing expected artifacts on calendar days.", styles["body"])
        )

    unplaced = matrix.get("unplaced_documents", [])
    if unplaced:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(f"Unplaced documents: {', '.join(unplaced)}", styles["body"])
        )

    story.append(Paragraph("3. Document Placements", styles["h2"]))
    detail_data = [["Slot", "Role", "doc_id", "Confidence"]]
    for p in placements.get("placements", []):
        detail_data.append(
            [
                p.get("slot", ""),
                p.get("role", ""),
                p.get("doc_id", ""),
                p.get("confidence", ""),
            ]
        )
    dt = Table(detail_data, colWidths=[1.3 * inch, 1.5 * inch, 1.5 * inch, 1.2 * inch])
    dt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#495057")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(dt)

    notes = placements.get("notes", [])
    if notes:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("4. Auditor Notes", styles["h2"]))
        for n in notes:
            story.append(Paragraph(f"• {n}", styles["body"]))

    doc.build(story)
    log(f"PDF → {pdf_path}")
    return pdf_path


# --- Live WeasyPrint products -----------------------------------------------


def render_project_pdf(project_id: str, output_path: Path | None = None) -> Path:
    """Project PDF from Layer 1 FIRST-PASS / GLOBAL-AUDIT.md."""
    root = project_dir(project_id)
    out_dir = root / "output"
    pdf_path = output_path or (out_dir / "GLOBAL-AUDIT-REPORT.pdf")

    title = "Curriculum Review Work Packet (first-pass)"
    global_md = out_dir / "GLOBAL-AUDIT.md"
    first_pass = out_dir / "FIRST-PASS.md"
    md_path = first_pass if first_pass.is_file() else global_md
    if md_path.is_file():
        md = md_path.read_text(encoding="utf-8")
        title = extract_h1(md, title)
    else:
        md = (
            "No Layer 1 conformance findings found. Run `layer1.py` then "
            "`synthesize.py` for this project.\n"
        )

    appendix = ""
    pacing_path = root / "pacing-plan.yaml"
    if pacing_path.is_file():
        appendix = year_at_a_glance_html(load_yaml(pacing_path))

    render_packet_pdf(
        pdf_path=pdf_path,
        project_id=project_id,
        title=title,
        doc_kind="Course review",
        md_text=md,
        appendix_html=appendix,
    )
    log(f"Project PDF → {pdf_path}")
    return pdf_path


def render_teacher_pdf(
    project_id: str, unit_id: str, output_path: Path | None = None
) -> Path:
    """Render output/teachers/<unit>/TEACHER-PACKET.md → TEACHER-PACKET.pdf."""
    root = project_dir(project_id)
    md_path = root / "output" / "teachers" / unit_id / "TEACHER-PACKET.md"
    if not md_path.is_file():
        raise FileNotFoundError(f"missing teacher packet markdown: {md_path}")
    pdf_path = output_path or (md_path.parent / "TEACHER-PACKET.pdf")
    md = md_path.read_text(encoding="utf-8")
    title = extract_h1(md, f"Teacher packet — {unit_id}")
    render_packet_pdf(
        pdf_path=pdf_path,
        project_id=project_id,
        unit_id=unit_id,
        title=title,
        doc_kind="Teacher packet",
        md_text=md,
    )
    log(f"Teacher PDF → {pdf_path}")
    return pdf_path


def render_unit_plan_pdf(
    project_id: str, unit_id: str, output_path: Path | None = None
) -> Path:
    """Render output/teachers/<unit>/UNIT-PLAN.md → UNIT-PLAN.pdf."""
    root = project_dir(project_id)
    md_path = root / "output" / "teachers" / unit_id / "UNIT-PLAN.md"
    if not md_path.is_file():
        raise FileNotFoundError(f"missing unit plan markdown: {md_path}")
    pdf_path = output_path or (md_path.parent / "UNIT-PLAN.pdf")
    md = md_path.read_text(encoding="utf-8")
    title = extract_h1(md, f"Unit Plan — {unit_id}")
    render_packet_pdf(
        pdf_path=pdf_path,
        project_id=project_id,
        unit_id=unit_id,
        title=title,
        doc_kind="Unit plan inventory",
        md_text=md,
    )
    log(f"Unit Plan PDF → {pdf_path}")
    return pdf_path


def render_lesson_plan_pdf(
    project_id: str, unit_id: str, output_path: Path | None = None
) -> Path:
    """Render output/teachers/<unit>/LESSON-PLAN.md → LESSON-PLAN.pdf."""
    root = project_dir(project_id)
    md_path = root / "output" / "teachers" / unit_id / "LESSON-PLAN.md"
    if not md_path.is_file():
        raise FileNotFoundError(f"missing lesson plan markdown: {md_path}")
    pdf_path = output_path or (md_path.parent / "LESSON-PLAN.pdf")
    md = md_path.read_text(encoding="utf-8")
    title = extract_h1(md, f"Lesson Plan — {unit_id}")
    render_packet_pdf(
        pdf_path=pdf_path,
        project_id=project_id,
        unit_id=unit_id,
        title=title,
        doc_kind="Lesson structure inventory · test draft",
        md_text=md,
    )
    log(f"Lesson Plan PDF → {pdf_path}")
    return pdf_path


def render_all_teacher_pdfs(project_id: str) -> list[Path]:
    """Render PDFs for every teacher unit folder under output/teachers/."""
    teachers = project_dir(project_id) / "output" / "teachers"
    if not teachers.is_dir():
        return []
    written: list[Path] = []
    for unit_dir in sorted(p for p in teachers.iterdir() if p.is_dir()):
        md = unit_dir / "TEACHER-PACKET.md"
        if md.is_file():
            written.append(render_teacher_pdf(project_id, unit_dir.name))
        up = unit_dir / "UNIT-PLAN.md"
        if up.is_file():
            try:
                written.append(render_unit_plan_pdf(project_id, unit_dir.name))
            except Exception as e:
                log(f"WARN: unit plan PDF skipped for {unit_dir.name}: {e}")
        lp = unit_dir / "LESSON-PLAN.md"
        if lp.is_file():
            try:
                written.append(render_lesson_plan_pdf(project_id, unit_dir.name))
            except Exception as e:
                log(f"WARN: lesson plan PDF skipped for {unit_dir.name}: {e}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render Crystallize packet PDFs (WeasyPrint) — global, teachers, "
            "unit/lesson plans; archived unit gap PDFs optional"
        )
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--unit",
        help="ARCHIVED path: unit PDF from existing 02-gap-report.json (not produced by ./run-audit)",
    )
    parser.add_argument(
        "--all-units",
        action="store_true",
        help="ARCHIVED path: unit PDFs for every unit that still has a gap report on disk",
    )
    parser.add_argument(
        "--global",
        dest="global_report",
        action="store_true",
        help="Project first-pass / global PDF",
    )
    parser.add_argument(
        "--teachers",
        action="store_true",
        help="Render PDF for every output/teachers/<unit>/TEACHER-PACKET.md (+ unit/lesson)",
    )
    parser.add_argument(
        "--teacher-unit",
        metavar="UNIT",
        help="Render PDF for one teacher packet unit id",
    )
    args = parser.parse_args()

    try:
        if args.global_report:
            render_project_pdf(args.project)
        if args.teachers:
            paths = render_all_teacher_pdfs(args.project)
            if not paths:
                log(
                    f"WARN: no teacher packets under output/teachers/ for {args.project}"
                )
        if args.teacher_unit:
            uid = args.teacher_unit
            render_teacher_pdf(args.project, uid)
            teachers = project_dir(args.project) / "output" / "teachers" / uid
            if (teachers / "UNIT-PLAN.md").is_file():
                render_unit_plan_pdf(args.project, uid)
            if (teachers / "LESSON-PLAN.md").is_file():
                render_lesson_plan_pdf(args.project, uid)
        if args.all_units:
            manifest = load_yaml(project_dir(args.project) / "manifest.yaml")
            for uid in manifest["units"]:
                gap = project_dir(args.project) / "output" / uid / "02-gap-report.json"
                if gap.is_file():
                    render_unit_pdf(args.project, uid)
        elif args.unit:
            render_unit_pdf(args.project, args.unit)
        elif not (args.global_report or args.teachers or args.teacher_unit):
            print(
                "Specify --global, --teachers, --teacher-unit, --unit, or --all-units",
                file=sys.stderr,
            )
            return 2
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
