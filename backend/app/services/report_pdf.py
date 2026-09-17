"""Branded, paginated lead report downloads."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


LOGO = Path(__file__).resolve().parents[1] / "assets" / "company-logo.jpg"
NAVY = colors.HexColor("#1e3a5f")
KEYS = ("total", "in_followup", "meeting", "site_visit", "quote_sent", "not_interested")


def build_report_pdf(payload: dict, report_type: str) -> bytes:
    if report_type not in ("source", "product"):
        raise ValueError("Invalid report type")
    title, label = ("Product-wise Report", "Product") if report_type == "product" else ("Lead Source Report", "Lead Source")
    field = report_type
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(width, height), leftMargin=36,
                            rightMargin=36, topMargin=122, bottomMargin=42,
                            title=title, author="ESTAR Engineers Pvt Ltd")
    generated = datetime.now().strftime("%d %b %Y")
    # Clip only the whitespace around the supplied artwork; retain the original asset.
    logo = ImageReader(str(LOGO))

    def page_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, height - 85, width, 85, fill=1, stroke=0)
        canvas.saveState()
        clip = canvas.beginPath()
        clip.rect(36, height - 79, 300, 58)
        canvas.clipPath(clip, stroke=0)
        canvas.drawImage(logo, 26, height - 155, width=320, height=213.2)
        canvas.restoreState()
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawRightString(width - 36, height - 42, title.upper())
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - 36, height - 64, f"Generated: {generated}")
        canvas.setStrokeColor(NAVY)
        canvas.line(36, height - 94, width - 36, height - 94)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(36, 24, title)
        canvas.drawRightString(width - 36, 24, f"Page {doc.page}")
        canvas.restoreState()

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=13,
                             textColor=NAVY, spaceAfter=10, keepWithNext=True)
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    story = []
    story.append(Paragraph(title, heading))
    headers = [label, "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Not Interested"]
    rows = [[Paragraph(value, header) for value in headers]]
    for row in payload["rows"]:
        rows.append([Paragraph(escape(str(row[field])), cell), *[row[key] for key in KEYS]])
    if not payload["rows"]:
        rows.append([Paragraph("No leads found", cell), *[0 for _ in KEYS]])
    rows.append(["TOTAL", *[payload["totals"][key] for key in KEYS]])
    table = Table(rows, colWidths=[205, *[(width - 72 - 205) / 6] * 6], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#edf4fa")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dce6ef")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, NAVY),
    ]))
    story.extend([table, Spacer(1, 22)])
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
