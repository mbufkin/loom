#!/usr/bin/env python3
"""Generate presentation SVG flow canvases (no external deps)."""

from pathlib import Path

# Script lives in tools/; SVG assets stay under docs/images/ (product docs zone).
OUT = Path(__file__).resolve().parent.parent / "docs" / "images"


def esc(text: str) -> str:
    """Escape XML special characters in SVG text nodes."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_wrap(
    title: str, body: str, w: int = 1200, h: int = 680, subtitle: str | None = None
) -> str:
    sub = subtitle or "Crystallize Lite · CTAT 2026 · export for Canva / Google Drive"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6 Z" fill="#64748b"/>
    </marker>
    <style>
      .title {{ font: 700 28px 'Segoe UI', Arial, sans-serif; fill: #0f172a; }}
      .subtitle {{ font: 400 16px 'Segoe UI', Arial, sans-serif; fill: #64748b; }}
      .group-title {{ font: 700 13px 'Segoe UI', Arial, sans-serif; fill: #475569; letter-spacing: 0.08em; }}
      .box {{ rx: 12; stroke-width: 2; }}
      .box-text {{ font: 600 15px 'Segoe UI', Arial, sans-serif; fill: #0f172a; }}
      .box-sub {{ font: 400 13px 'Segoe UI', Arial, sans-serif; fill: #475569; }}
      .arrow {{ stroke: #64748b; stroke-width: 2.5; fill: none; marker-end: url(#arrow); }}
    </style>
  </defs>
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <text x="40" y="48" class="title">{esc(title)}</text>
  <text x="40" y="76" class="subtitle">{esc(sub)}</text>
  {body}
</svg>"""


def group(x, y, w, h, label, fill, stroke):
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="2" opacity="0.35"/>
  <text x="{x + 16}" y="{y + 28}" class="group-title">{esc(label)}</text>"""


def box(x, y, w, h, lines, fill="#ffffff", stroke="#334155"):
    line_h = 20
    ty = y + h / 2 - (len(lines) - 1) * line_h / 2 + 6
    texts = []
    for i, (text, cls) in enumerate(lines):
        texts.append(
            f'<text x="{x + w/2}" y="{ty + i * line_h}" text-anchor="middle" class="{cls}">{esc(text)}</text>'
        )
    return f"""
  <rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}"/>
  {''.join(texts)}"""


def arrow(x1, y1, x2, y2):
    return f'<line class="arrow" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'


def data_flow_high_level():
    """Legacy 3-column overview (kept for older slides). Prefer data_flow_layer01()."""
    body = group(40, 110, 250, 420, "INPUT", "#dbeafe", "#1d4ed8")
    body += group(330, 110, 520, 420, "CRYSTALLIZE PIPELINE", "#dcfce7", "#166534")
    body += group(890, 110, 270, 420, "OUTPUT", "#ffedd5", "#c2410c")

    boxes = [
        (
            60,
            160,
            210,
            70,
            [("Curriculum docs", "box-text"), ("pdf · docx · pptx", "box-sub")],
        ),
        (
            60,
            260,
            210,
            70,
            [("District calendar", "box-text"), ("PNG / YAML", "box-sub")],
        ),
        (
            360,
            160,
            180,
            56,
            [("Extract text", "box-text"), ("doc_extract.py", "box-sub")],
        ),
        (560, 160, 180, 56, [("Ingest", "box-text"), ("models", "box-sub")]),
        (360, 250, 180, 56, [("Rollup year", "box-text"), ("code", "box-sub")]),
        (
            560,
            250,
            180,
            56,
            [("Layer 0 extract", "box-text"), ("models · cited", "box-sub")],
            "#dbeafe",
            "#1d4ed8",
        ),
        (
            360,
            340,
            180,
            56,
            [("Layer 1 place", "box-text"), ("MATCH / MISMATCH", "box-sub")],
            "#dbeafe",
            "#1d4ed8",
        ),
        (560, 340, 180, 56, [("Synthesize + PDF", "box-text"), ("code", "box-sub")]),
        (
            910,
            180,
            230,
            80,
            [("GLOBAL PDF", "box-text"), ("DASHBOARD · SUMMARY", "box-sub")],
            "#ecfdf5",
            "#059669",
        ),
        (
            910,
            300,
            230,
            80,
            [("Year map", "box-text"), ("pacing-plan.yaml", "box-sub")],
        ),
    ]
    for b in boxes:
        body += box(*b)

    arrows = [
        (270, 195, 360, 188),
        (270, 295, 360, 278),
        (540, 188, 560, 188),
        (540, 278, 560, 278),
        (540, 368, 560, 368),
        (740, 368, 910, 220),
        (740, 278, 910, 340),
    ]
    for a in arrows:
        body += arrow(*a)

    return svg_wrap("Data Flow — High Level", body)


def data_flow_layer01():
    """Five-column CTAT-style canvas for the Layer 0/1 headline path."""
    w, h = 1400, 720
    # Column bands
    cols = [
        (40, "1  INPUT", "#dbeafe", "#1d4ed8"),
        (300, "2  EXTRACT & ORGANIZE", "#dcfce7", "#166534"),
        (560, "3  STRUCTURAL MAP", "#fef9c3", "#a16207"),
        (820, "4  AUDIT (headline)", "#dbeafe", "#1d4ed8"),
        (1080, "5  OUTPUT", "#ffedd5", "#c2410c"),
    ]
    body = ""
    for x, label, fill, stroke in cols:
        body += group(x, 100, 240, 500, label, fill, stroke)

    # Col 1
    body += box(
        60,
        160,
        200,
        70,
        [("Curriculum documents", "box-text"), ("PDF · DOCX · PPTX · TXT", "box-sub")],
    )
    body += box(
        60,
        260,
        200,
        70,
        [("District calendar", "box-text"), ("optional YAML / image", "box-sub")],
        "#eff6ff",
        "#93c5fd",
    )

    # Col 2
    body += box(
        320,
        150,
        200,
        56,
        [("doc_extract / scrub", "box-text"), ("code · full text", "box-sub")],
    )
    body += box(
        320, 230, 200, 56, [("ingest.py", "box-text"), ("models · organize", "box-sub")]
    )
    body += box(
        320,
        320,
        200,
        56,
        [("manifest.yaml", "box-text"), ("unit ↔ documents", "box-sub")],
        "#ecfdf5",
        "#059669",
    )
    body += box(
        320,
        400,
        200,
        56,
        [("units/*/calendar.yaml", "box-text"), ("provisional day roles", "box-sub")],
        "#ecfdf5",
        "#059669",
    )

    # Col 3
    body += box(580, 180, 200, 56, [("rollup.py", "box-text"), ("code", "box-sub")])
    body += box(
        580,
        280,
        200,
        56,
        [("pacing-plan.yaml", "box-text"), ("inferred year map", "box-sub")],
        "#ecfdf5",
        "#059669",
    )
    body += box(
        580,
        380,
        200,
        56,
        [("Year at a Glance", "box-text"), ("demoted scaffold", "box-sub")],
    )

    # Col 4 — headline
    body += box(
        840,
        150,
        200,
        56,
        [("layer0.py", "box-text"), ("models · cited elements", "box-sub")],
        "#dbeafe",
        "#1d4ed8",
    )
    body += box(
        840,
        230,
        200,
        56,
        [("layer0/ledger.json", "box-text"), ("element ledger", "box-sub")],
        "#ecfdf5",
        "#059669",
    )
    body += box(
        840,
        310,
        200,
        56,
        [("layer1.py", "box-text"), ("placement conformance", "box-sub")],
        "#dbeafe",
        "#1d4ed8",
    )
    body += box(
        840,
        390,
        200,
        56,
        [("MATCH / MISMATCH / …", "box-text"), ("bucket-ledger · findings", "box-sub")],
        "#ffedd5",
        "#c2410c",
    )
    body += box(
        840,
        470,
        200,
        56,
        [("REVIEW-QUEUE.md", "box-text"), ("human calibration", "box-sub")],
        "#fee2e2",
        "#dc2626",
    )

    # Col 5
    body += box(
        1100,
        180,
        200,
        56,
        [("synthesize.py", "box-text"), ("Layer-1 globals", "box-sub")],
    )
    body += box(
        1100, 270, 200, 56, [("render_pdf.py", "box-text"), ("code", "box-sub")]
    )
    body += box(
        1100,
        360,
        200,
        70,
        [("GLOBAL-AUDIT-REPORT.pdf", "box-text"), ("director deliverable", "box-sub")],
        "#ecfdf5",
        "#059669",
    )
    body += box(
        1100,
        460,
        200,
        56,
        [("DASHBOARD.md", "box-text"), ("counts · patterns", "box-sub")],
        "#ecfdf5",
        "#059669",
    )

    # Flow arrows between columns (mid heights)
    for x1, y1, x2, y2 in [
        (260, 195, 320, 178),
        (260, 295, 320, 258),
        (520, 258, 580, 208),
        (520, 348, 580, 308),
        (780, 208, 840, 178),
        (780, 308, 840, 338),
        (1040, 338, 1100, 208),
        (1040, 418, 1100, 298),
        (1040, 498, 1100, 395),
    ]:
        body += arrow(x1, y1, x2, y2)

    # Charter footer
    body += """
  <rect x="40" y="630" width="1320" height="48" rx="10" fill="#fef2f2" stroke="#dc2626" stroke-width="2" stroke-dasharray="6 4"/>
  <text x="700" y="660" text-anchor="middle" class="box-text" fill="#991b1b">Auditor only — never writes lesson content</text>
"""
    return svg_wrap(
        "Crystallize — Data Flow",
        body,
        w,
        h,
        subtitle="Layer 0/1 headline path · ./run-audit <id> · CTAT 2026",
    )


def file_flow_high_level():
    body = group(40, 110, 280, 420, "INPUT FILES", "#dbeafe", "#1d4ed8")
    body += group(360, 110, 320, 420, "PROJECT SPINE", "#fef9c3", "#a16207")
    body += group(720, 110, 440, 420, "OUTPUT FILES", "#ffedd5", "#c2410c")

    boxes = [
        (
            60,
            170,
            240,
            72,
            [("sources/", "box-text"), ("111 extracted .txt", "box-sub")],
        ),
        (
            60,
            270,
            240,
            72,
            [("reference/", "box-text"), ("district calendar PNG", "box-sub")],
        ),
        (
            60,
            370,
            240,
            72,
            [
                ("units/*/calendar.yaml", "box-text"),
                ("18 provisional grids", "box-sub"),
            ],
        ),
        (
            380,
            170,
            280,
            72,
            [("manifest.yaml", "box-text"), ("unit ↔ doc list", "box-sub")],
        ),
        (
            380,
            270,
            280,
            72,
            [
                ("school-calendar.yaml", "box-text"),
                ("175 instructional days", "box-sub"),
            ],
        ),
        (
            380,
            370,
            280,
            72,
            [("pacing-plan.yaml", "box-text"), ("inferred year map", "box-sub")],
            "#ecfdf5",
            "#059669",
        ),
        (
            740,
            170,
            400,
            72,
            [("output/&lt;unit&gt;/", "box-text"), ("00 · 01 · 02 · PDF", "box-sub")],
        ),
        (
            740,
            270,
            400,
            72,
            [
                ("GLOBAL-AUDIT-REPORT.pdf", "box-text"),
                ("DASHBOARD · SUMMARY", "box-sub"),
            ],
            "#ecfdf5",
            "#059669",
        ),
        (
            740,
            370,
            400,
            72,
            [("runs/run-*.log", "box-text"), ("operator trace", "box-sub")],
        ),
    ]
    for b in boxes:
        body += box(*b)

    for x1, y1, x2, y2 in [
        (300, 206, 380, 206),
        (300, 306, 380, 306),
        (300, 406, 380, 406),
        (660, 206, 740, 206),
        (660, 306, 740, 306),
        (660, 406, 740, 406),
        (880, 242, 880, 270),
    ]:
        body += arrow(x1, y1, x2, y2)

    return svg_wrap("File Flow — High Level", body)


def file_flow_unit_output():
    body = group(
        40,
        110,
        1120,
        420,
        "output/&lt;unit-id&gt;/ — same shape for all 18 units",
        "#f1f5f9",
        "#64748b",
    )
    boxes = [
        (
            80,
            200,
            190,
            80,
            [("00-evidence-index.json", "box-text"), ("all docs + roles", "box-sub")],
        ),
        (
            300,
            200,
            190,
            80,
            [("01-calendar-map.*", "box-text"), ("day placements", "box-sub")],
        ),
        (
            520,
            200,
            190,
            80,
            [("02-gap-report.*", "box-text"), ("missing slots", "box-sub")],
            "#fee2e2",
            "#dc2626",
        ),
        (
            740,
            200,
            190,
            80,
            [("AUDIT-REPORT.pdf", "box-text"), ("director grid", "box-sub")],
            "#ecfdf5",
            "#059669",
        ),
        (
            960,
            200,
            170,
            80,
            [("evidence/*.json", "box-text"), ("scrubbed excerpts", "box-sub")],
        ),
    ]
    for b in boxes:
        body += box(*b)
    body += box(
        520,
        340,
        410,
        70,
        [("Demo read order: 01 → 02 → 00 → PDF", "box-sub")],
        "#eff6ff",
        "#2563eb",
    )
    return svg_wrap("File Flow — Per-Unit Output Folder", body, 1200, 520)


def file_flow_pipeline_writes():
    stages = [
        ("ingest.py", "manifest.yaml · school-calendar.yaml · units/*/calendar.yaml"),
        ("rollup.py", "pacing-plan.yaml · 03-year-calendar-map.*"),
        ("audit.py", "evidence/ · 00- · 01- · 02- per unit"),
        ("synthesize.py", "GLOBAL-AUDIT.md · DASHBOARD.md · aggregate-stats.json"),
        ("render_pdf.py", "AUDIT-REPORT.pdf · GLOBAL-AUDIT-REPORT.pdf"),
    ]
    body = ""
    y = 140
    for script, files in stages:
        body += box(80, y, 220, 64, [(script, "box-text")], "#dcfce7", "#166534")
        body += box(340, y, 780, 64, [(files, "box-sub")])
        body += arrow(300, y + 32, 340, y + 32)
        y += 90
    return svg_wrap("File Flow — Script → Files Written", body, 1200, 700)


def main():
    files = {
        "data-flow-01-high-level.svg": data_flow_high_level(),
        "data-flow-02-layer01.svg": data_flow_layer01(),
        "file-flow-01-high-level.svg": file_flow_high_level(),
        "file-flow-02-unit-output.svg": file_flow_unit_output(),
        "file-flow-03-pipeline-writes.svg": file_flow_pipeline_writes(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
