"""Generate the binary documents in the welding sample corpus.

The PDF, spreadsheet and JPEG in the sample corpus are committed so the folder
works straight from a clone, but they are built here rather than hand-made: a
binary blob in a diff is something nobody can review, whereas this script keeps
their content as readable code and lets them be regenerated if a library
changes what it emits.

Run from the repository root:

    python sample-documents/make_sample_binaries.py
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

CORPUS = Path(__file__).resolve().parent / "welding-technology-2026"
UNSUPPORTED = CORPUS / "not-supported"


# --------------------------------------------------------------------------
# The PDF: a printable pre-use checklist for Unit 2.
#
# PDF is here on purpose. It is the format teachers actually hand over most
# often, and it is the one extraction path with a real chance of failing
# quietly -- a scanned PDF yields no text layer at all. This one is generated
# rather than scanned, so it does have a text layer and should extract
# cleanly; it exercises the PDFium path without also testing OCR.
# --------------------------------------------------------------------------
def build_pdf() -> Path:
    out = CORPUS / "unit-2-oxyfuel-safety-checklist.pdf"

    styles = getSampleStyleSheet()
    # leading is set well above font size because this is a document people
    # read standing up at a bench, holding a torch in the other hand.
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=15,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    h1 = ParagraphStyle(
        "h1", parent=styles["Heading1"], fontSize=17, leading=21, spaceAfter=4
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=12.5, leading=16, spaceBefore=14
    )
    note = ParagraphStyle(
        "note", parent=body, fontSize=9.5, leading=13, textColor="#444444"
    )

    def checks(items: list[str]) -> ListFlowable:
        # An open square rather than a bullet: the point of the document is
        # that somebody ticks it.
        return ListFlowable(
            [ListItem(Paragraph(text, body), leftIndent=18) for text in items],
            bulletType="bullet",
            start="\u25a1",
            bulletFontSize=11,
            leftIndent=16,
        )

    flow = [
        Paragraph("Unit 2 &mdash; Oxy-Fuel Pre-Use Safety Checklist", h1),
        Paragraph(
            "Introduction to Welding Technology (CTE 1042). "
            "One copy per outfit, per period. "
            "Initial each section. An unticked box means the torch is not lit.",
            note,
        ),
        Spacer(1, 10),
        Paragraph(
            "Student: ______________________________ &nbsp;&nbsp; "
            "Outfit / bay: __________ &nbsp;&nbsp; "
            "Date: ____________ &nbsp;&nbsp; Period: ______",
            body,
        ),
        Paragraph("1. Before you touch anything", h2),
        checks(
            [
                "Bay extraction fan is running.",
                "Bay is clear of combustibles, including scrap paper and rags.",
                "Fire extinguisher located and its position stated aloud.",
                "Cutting goggles (shade 5), safety glasses, gloves, "
                "flame-resistant jacket and leather boots on.",
            ]
        ),
        Paragraph("2. Cylinders", h2),
        checks(
            [
                "Both cylinders chained upright.",
                "Hydrostatic test dates in date on both cylinders.",
                "Acetylene cylinder has stood upright at least 30 minutes "
                "&mdash; it is stored dissolved in acetone and needs to settle.",
                "Caps fitted on any cylinder in the bay without a regulator.",
                "Oxygen and fuel gas in storage are separated by 20 ft, or by "
                "a 5 ft non-combustible barrier rated for half an hour.",
            ]
        ),
        Paragraph("3. Assembly, in this order", h2),
        checks(
            [
                "Each cylinder valve cracked briefly to clear the seat.",
                "Correct regulator on the correct cylinder &mdash; acetylene "
                "is left-hand thread with a notched nut, oxygen is "
                "right-hand.",
                "Hoses attached: green to oxygen, red to fuel.",
                "Torch handle fitted, then the cutting attachment, then the "
                "tip.",
                "Both regulators backed out to zero before the cylinder "
                "valves are opened.",
            ]
        ),
        Paragraph("4. Opening up", h2),
        checks(
            [
                "Oxygen cylinder valve opened fully, against the back seat.",
                "Acetylene cylinder valve opened no more than three quarters "
                "of a turn, so it can be shut fast.",
                "Working pressures set for the tip in use &mdash; size 0 tip: "
                "40 psi oxygen, 7 psi acetylene.",
                "Acetylene is at or below 15 psi. Above 15 psi it becomes "
                "unstable. This is not a guideline.",
            ]
        ),
        Paragraph("5. Leak test &mdash; every joint, every time", h2),
        checks(
            [
                "Soap solution applied to both regulator-to-cylinder joints.",
                "Soap solution applied to both hose-to-regulator and "
                "hose-to-torch joints.",
                "No bubbles anywhere. A bubble means the joint comes apart "
                "and is refitted, then retested.",
            ]
        ),
        Paragraph("6. Lighting and flame", h2),
        checks(
            [
                "Striker in hand. No lighters, no matches, no hot plate.",
                "Striker held to the side of the tip, never in front of it.",
                "Flame adjusted to neutral &mdash; sharply defined inner cone, "
                "no acetylene feather, no harsh hiss.",
            ]
        ),
        Paragraph("7. Shutdown, in this order", h2),
        checks(
            [
                "Cutting oxygen lever released.",
                "Torch oxygen valve closed.",
                "Torch fuel valve closed.",
                "Both cylinder valves closed.",
                "Hoses bled by reopening the torch valves briefly.",
                "Both regulators backed out to zero.",
                "Hoses coiled and hung, plate returned to the rack, bay "
                "swept.",
            ]
        ),
        Spacer(1, 12),
        Paragraph(
            "Student initials: __________ &nbsp;&nbsp;&nbsp; "
            "Instructor verification: __________",
            body,
        ),
        Spacer(1, 6),
        Paragraph(
            "If you notice a backfire (a sharp pop and the flame going out) "
            "or a flashback (a squeal with the flame burning back inside the "
            "torch), shut the fuel valve first, then the oxygen, and tell the "
            "instructor before relighting. Do not relight a torch that has "
            "flashed back until it has been checked.",
            note,
        ),
    ]

    SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Unit 2 Oxy-Fuel Pre-Use Safety Checklist",
        author="Introduction to Welding Technology (CTE 1042)",
    ).build(flow)

    return out


# --------------------------------------------------------------------------
# The spreadsheet: booth-by-booth equipment condition.
#
# Two sheets rather than one, because a workbook with a single sheet does not
# prove the extractor walks all of them -- and a teacher's real inventory
# workbook always has more than one tab.
# --------------------------------------------------------------------------
def build_xlsx() -> Path:
    out = CORPUS / "equipment-inventory.xlsx"

    wb = Workbook()
    bold = Font(bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")

    def write_sheet(ws, title: str, headers: list[str], rows: list[list]) -> None:
        ws.title = title
        ws.append(headers)
        for cell in ws[1]:
            cell.font = bold
        for row in rows:
            ws.append(row)
        # Width from the longest value in each column, capped, so the file is
        # readable if anyone actually opens it rather than only extracts it.
        for i, _ in enumerate(headers, start=1):
            longest = max(
                len(str(ws.cell(row=r, column=i).value or ""))
                for r in range(1, ws.max_row + 1)
            )
            ws.column_dimensions[get_column_letter(i)].width = min(
                max(longest + 2, 10), 46
            )
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap
        ws.freeze_panes = "A2"

    booths = wb.active
    write_sheet(
        booths,
        "Welding booths",
        ["Booth", "Machine", "Output", "Condition", "Action needed", "Last checked"],
        [
            [1, "Lincoln AC/DC 225/125", "AC + DCEP/DCEN", "Serviceable", "", "2026-08-24"],
            [2, "Lincoln AC/DC 225/125", "AC + DCEP/DCEN", "Serviceable", "", "2026-08-24"],
            [3, "Lincoln AC/DC 225/125", "AC + DCEP/DCEN", "Serviceable", "", "2026-08-24"],
            [
                4,
                "Lincoln AC/DC 225/125",
                "AC only - DC selector seized",
                "Limited",
                "DC selector will not move. Usable for the E6011 demonstration "
                "only. Do not assign for the E7018 graded practical.",
                "2026-08-24",
            ],
            [5, "Miller Thunderbolt 210", "AC + DC", "Serviceable", "", "2026-08-24"],
            [6, "Miller Thunderbolt 210", "AC + DC", "Serviceable", "", "2026-08-24"],
            [
                7,
                "Miller Thunderbolt 210",
                "AC + DC",
                "Serviceable",
                "Work clamp spring weak, holds but needs watching. Replacement "
                "ordered.",
                "2026-08-24",
            ],
            [
                8,
                "Miller Thunderbolt 210",
                "AC + DC",
                "Out of service",
                "Primary lead insulation cracked at the strain relief. Locked "
                "out at the disconnect. Electrician scheduled.",
                "2026-08-29",
            ],
        ],
    )

    write_sheet(
        wb.create_sheet(),
        "Cutting bays and consumables",
        ["Item", "Location", "Quantity", "Condition", "Notes"],
        [
            [
                "Oxy-acetylene outfit",
                "Cutting bay 1",
                1,
                "Serviceable",
                "Size 0 and size 1 tips present. Flashback arrestors fitted.",
            ],
            [
                "Oxy-acetylene outfit",
                "Cutting bay 2",
                1,
                "Serviceable",
                "Size 0 tip only. Second tip on order.",
            ],
            [
                "Oxy-acetylene outfit",
                "Cutting bay 3",
                1,
                "Limited",
                "Acetylene regulator gauge glass crazed, reading still legible. "
                "Replace before next semester.",
            ],
            [
                "Oxygen cylinder, full",
                "Cylinder store",
                4,
                "In date",
                "Hydrostatic test dates 2024-2025. Chained upright, caps fitted.",
            ],
            [
                "Acetylene cylinder, full",
                "Cylinder store",
                3,
                "In date",
                "Stored 20 ft from oxygen per MFG.SAF.2.",
            ],
            [
                "Acetylene cylinder, empty",
                "Cylinder store",
                2,
                "Awaiting exchange",
                "Tagged EMPTY. Collection booked.",
            ],
            [
                "E7018 electrode, 1/8 in",
                "Rod oven",
                "3 boxes",
                "Dry",
                "Oven holding 250 F, logged daily on the consumables check.",
            ],
            [
                "E6011 electrode, 1/8 in",
                "Consumables cabinet",
                "1 box",
                "Serviceable",
                "Below the quarter-box reorder point. Flagged on the whiteboard.",
            ],
            [
                "E6013 electrode, 3/32 in",
                "Consumables cabinet",
                "2 boxes",
                "Serviceable",
                "Held for sheet metal work later in the semester.",
            ],
            [
                "Mild steel plate, 1/4 in",
                "Plate rack",
                "~90 coupons",
                "Serviceable",
                "4 in x 6 in. Unit 1 needs 8 per student.",
            ],
            [
                "Mild steel plate, 3/8 in",
                "Plate rack",
                "~40 coupons",
                "Low",
                "6 in x 6 in. Unit 2 needs 4 per student; short for a full "
                "roster of 24.",
            ],
            [
                "Welding helmet, shade 10",
                "Booth hooks",
                8,
                "Mixed",
                "Booths 2 and 6 have pitted cover plates. Replace on the next "
                "housekeeping rotation.",
            ],
            [
                "Cutting goggles, shade 5",
                "Cutting bays",
                6,
                "Serviceable",
                "Worn in addition to safety glasses, not instead of them.",
            ],
            [
                "Striker",
                "Cutting bays",
                4,
                "Serviceable",
                "Spare flints in the consumables cabinet. No lighters or "
                "matches in the bay.",
            ],
            [
                "Fire extinguisher, ABC",
                "Lab, by the bay door",
                2,
                "In date",
                "Inspected 2026-08-01. Position pointed out to each class "
                "rather than assumed known.",
            ],
        ],
    )

    wb.save(out)
    return out


# --------------------------------------------------------------------------
# The image: a file Loom is meant to refuse.
#
# Kept in not-supported/ so it is opt-in. A corpus that only contains files
# that work never tests the refusal message, and a refusal that fails to name
# the formats that do work is the kind of dead end this whole setup flow
# exists to remove.
#
# A JPEG rather than something exotic, because a phone photograph of a paper
# handout is the unsupported file teachers actually send. It carries real
# instructional content and no text layer at all, which is exactly the case
# that must be refused at upload rather than accepted and found empty later.
# --------------------------------------------------------------------------
def build_photo() -> Path:
    UNSUPPORTED.mkdir(parents=True, exist_ok=True)
    out = UNSUPPORTED / "shop-safety-poster-photo.jpg"

    # Rendered with reportlab and rasterised with PyMuPDF, both of which are
    # already dependencies, rather than adding Pillow for one test fixture.
    import pymupdf

    tmp = UNSUPPORTED / "_poster.pdf"
    styles = getSampleStyleSheet()
    SimpleDocTemplate(str(tmp), pagesize=letter).build(
        [
            Paragraph("SHOP SAFETY", styles["Title"]),
            Spacer(1, 24),
            Paragraph(
                "Helmet down before the arc. Goggles and glasses for cutting. "
                "Cylinders chained upright. Clamp to the work, not through a "
                "chain.",
                ParagraphStyle(
                    "poster", parent=styles["BodyText"], fontSize=22, leading=30
                ),
            ),
            Spacer(1, 36),
            Paragraph(
                "This is a stand-in for a photographed wall poster. It is a "
                "JPEG, which Loom's extractor does not read, and it exists so "
                "the refusal path can be tried on purpose.",
                styles["BodyText"],
            ),
        ]
    )

    doc = pymupdf.open(tmp)
    doc.load_page(0).get_pixmap(dpi=110).save(out)
    doc.close()
    tmp.unlink()

    return out


def main() -> None:
    for build in (build_pdf, build_xlsx, build_photo):
        path = build()
        rel = path.relative_to(Path(__file__).resolve().parent)
        print(f"  wrote {rel}  ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
