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
GREEN = colors.HexColor("#3F6212")
KEYS = ("total", "in_followup", "meeting", "site_visit", "quote_sent", "not_interested")


def _brand_logo() -> ImageReader:
    """Load the E-Star logo, trimming white margins so it fits the PDF header."""
    if not LOGO.exists():
        raise FileNotFoundError(f"Company logo missing: {LOGO}")
    try:
        from PIL import Image

        im = Image.open(LOGO).convert("RGB")
        pixels = im.load()
        w, h = im.size
        minx, miny, maxx, maxy = w, h, 0, 0
        found = False
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                if r < 245 or g < 245 or b < 245:
                    found = True
                    if x < minx:
                        minx = x
                    if y < miny:
                        miny = y
                    if x > maxx:
                        maxx = x
                    if y > maxy:
                        maxy = y
        if found:
            pad = 8
            im = im.crop((
                max(0, minx - pad),
                max(0, miny - pad),
                min(w, maxx + 1 + pad),
                min(h, maxy + 1 + pad),
            ))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return ImageReader(str(LOGO))


def _inr(n) -> str:
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    # Whole rupees only — no paise / .00
    s = f"{v:,}"
    return f"Rs. {s}"


def _centered_table_style(header_color=NAVY) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#edf4fa")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dce6ef")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, header_color),
    ])


def _page_header_fn(logo, logo_iw, logo_ih, title: str, generated: str, width, height, doc):
    def page_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, height - 85, width, 85, fill=1, stroke=0)
        max_w, max_h = 300, 58
        scale = min(max_w / float(logo_iw), max_h / float(logo_ih))
        draw_w, draw_h = logo_iw * scale, logo_ih * scale
        canvas.drawImage(
            logo, 36, height - 14 - draw_h, width=draw_w, height=draw_h,
            mask="auto", preserveAspectRatio=True, anchor="c",
        )
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
    return page_header


def build_report_pdf(payload: dict, report_type: str) -> bytes:
    if report_type == "lead_value":
        return build_lead_value_pdf(payload)
    if report_type == "quotation":
        return build_quotation_pdf(payload)
    if report_type == "monthly":
        return build_monthly_pdf(payload)
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
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=13,
                             textColor=NAVY, spaceAfter=10, keepWithNext=True, alignment=1)
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    story = []
    story.append(Paragraph(title, heading))
    headers = [label, "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Not Interested"]
    rows = [[Paragraph(value, header) for value in headers]]
    for row in payload["rows"]:
        rows.append([
            Paragraph(escape(str(row[field])), cell),
            *[Paragraph(str(row[key]), cell) for key in KEYS],
        ])
    if not payload["rows"]:
        rows.append([Paragraph("No leads found", cell), *[Paragraph("0", cell) for _ in KEYS]])
    rows.append([Paragraph("TOTAL", header), *[Paragraph(str(payload["totals"][key]), cell) for key in KEYS]])
    col_w = (width - 72) / 7
    table = Table(rows, colWidths=[col_w] * 7, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style())
    story.extend([table, Spacer(1, 22)])
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_lead_value_pdf(payload: dict) -> bytes:
    title = "Lead Value Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(width, height), leftMargin=36,
                            rightMargin=36, topMargin=122, bottomMargin=42,
                            title=title, author="ESTAR Engineers Pvt Ltd")
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=13,
                             textColor=GREEN, spaceAfter=8, keepWithNext=True, alignment=1)
    subhead = ParagraphStyle("subhead", fontName="Helvetica-Bold", fontSize=11,
                             textColor=NAVY, spaceBefore=12, spaceAfter=8, alignment=1)
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1, textColor=colors.HexColor("#334155"))

    story = []
    story.append(Paragraph(title, heading))
    rng = f"{payload.get('from_date') or 'All'} → {payload.get('to_date') or 'All'}  ·  Mode: {payload.get('mode') or 'custom'}"
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    # KPI strip
    kpi_headers = ["Total Lead Value", "Total Leads", "Total Cars", "Average Lead Value"]
    kpi_vals = [
        _inr(payload.get("total_lead_value")),
        str(payload.get("total_leads") or 0),
        str(int(float(payload.get("total_cars") or 0))),
        _inr(payload.get("average_lead_value")),
    ]
    kpi = Table(
        [[Paragraph(h, header) for h in kpi_headers], [Paragraph(v, cell) for v in kpi_vals]],
        colWidths=[(width - 72) / 4] * 4,
        hAlign="CENTER",
    )
    kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ecfdf3")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(kpi)

    # By product
    story.append(Paragraph("Lead Value by Product", subhead))
    prod_rows = [[Paragraph(h, header) for h in ("Product", "Leads", "Lead Value")]]
    for row in payload.get("by_product") or []:
        prod_rows.append([
            Paragraph(escape(str(row.get("product") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
        ])
    if len(prod_rows) == 1:
        prod_rows.append([Paragraph("No data", cell), Paragraph("0", cell), Paragraph(_inr(0), cell)])
    prod_rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(payload.get("total_leads") or 0), cell),
        Paragraph(_inr(payload.get("total_lead_value")), cell),
    ])
    pw = (width - 72) / 3
    prod_table = Table(prod_rows, colWidths=[pw * 1.4, pw * 0.6, pw], repeatRows=1, hAlign="CENTER")
    prod_table.setStyle(_centered_table_style(GREEN))
    story.append(prod_table)

    # By period
    story.append(Paragraph("Lead Value by Period", subhead))
    per_rows = [[Paragraph(h, header) for h in ("Period", "Leads", "Lead Value")]]
    for row in payload.get("by_period") or []:
        per_rows.append([
            Paragraph(escape(str(row.get("label") or row.get("period") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
        ])
    if len(per_rows) == 1:
        per_rows.append([Paragraph("No dated leads", cell), Paragraph("0", cell), Paragraph(_inr(0), cell)])
    period_total_leads = sum(int(r.get("leads") or 0) for r in (payload.get("by_period") or []))
    period_total_value = sum(float(r.get("lead_value") or 0) for r in (payload.get("by_period") or []))
    per_rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(period_total_leads), cell),
        Paragraph(_inr(period_total_value), cell),
    ])
    per_table = Table(per_rows, colWidths=[pw * 1.4, pw * 0.6, pw], repeatRows=1, hAlign="CENTER")
    per_table.setStyle(_centered_table_style(GREEN))
    story.append(per_table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


AMBER = colors.HexColor("#b45309")
INDIGO = colors.HexColor("#4338ca")


def build_monthly_pdf(payload: dict) -> bytes:
    title = "Monthly Lead Volume"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=28, rightMargin=28,
        topMargin=122, bottomMargin=42, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, alignment=1)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=INDIGO, spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"),
    )

    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('from_month') or 'All'} → {payload.get('to_month') or 'All'}"
        f"  ·  Months: {len(payload.get('rows') or [])}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    headers = [
        "Month", "Total Leads", "In Followup", "Meeting", "Site Visit",
        "Quotation sent", "Not Interested", "Lead Sources", "Products",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    totals = {
        "leads": 0, "in_followup": 0, "meeting": 0, "site_visit": 0,
        "quotation_sent": 0, "not_interested": 0,
    }
    for row in payload.get("rows") or []:
        for key in totals:
            totals[key] += int(row.get(key) or 0)
        rows.append([
            Paragraph(escape(str(row.get("month") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(str(row.get("in_followup") or 0), cell),
            Paragraph(str(row.get("meeting") or 0), cell),
            Paragraph(str(row.get("site_visit") or 0), cell),
            Paragraph(str(row.get("quotation_sent") or 0), cell),
            Paragraph(str(row.get("not_interested") or 0), cell),
            Paragraph(escape(str(row.get("sources") or "—")), cell),
            Paragraph(escape(str(row.get("products") or "—")), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No months found", cell), *[Paragraph("—", cell) for _ in range(8)]])
    rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(totals["leads"]), cell),
        Paragraph(str(totals["in_followup"]), cell),
        Paragraph(str(totals["meeting"]), cell),
        Paragraph(str(totals["site_visit"]), cell),
        Paragraph(str(totals["quotation_sent"]), cell),
        Paragraph(str(totals["not_interested"]), cell),
        Paragraph("", cell),
        Paragraph("", cell),
    ])

    usable = width - 56
    weights = [0.08, 0.08, 0.09, 0.08, 0.08, 0.10, 0.10, 0.20, 0.19]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(INDIGO))
    story.append(table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_quotation_pdf(payload: dict) -> bytes:
    title = "Quotation Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=28, rightMargin=28,
        topMargin=122, bottomMargin=42, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, alignment=1)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=AMBER, spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"),
    )

    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('effective_from') or 'All'} → {payload.get('effective_to') or 'All'}"
        f"  ·  Mode: {payload.get('mode') or 'custom'}"
        f"  ·  Rows: {payload.get('totals', {}).get('count', len(payload.get('rows') or []))}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    headers = [
        "S.No", "Date", "Enquiry No", "Customer Name", "State", "Parking Type",
        "Units/Cars", "Order Value (Excl GST)", "GST", "Grand Total",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    for i, row in enumerate(payload.get("rows") or [], start=1):
        rows.append([
            Paragraph(str(i), cell),
            Paragraph(escape(str(row.get("date") or "—")), cell),
            Paragraph(escape(str(row.get("enquiry_number") or "—")), cell),
            Paragraph(escape(str(row.get("customer_name") or "—")), cell),
            Paragraph(escape(str(row.get("state") or "—")), cell),
            Paragraph(escape(str(row.get("parking_type") or "—")), cell),
            Paragraph("—" if row.get("units") is None else str(row.get("units")), cell),
            Paragraph(_inr(row.get("order_value_excl_gst")), cell),
            Paragraph(_inr(row.get("gst")), cell),
            Paragraph(_inr(row.get("grand_total")), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No quotations found", cell), *[Paragraph("—", cell) for _ in range(9)]])
    totals = payload.get("totals") or {}
    rows.append([
        Paragraph("", cell), Paragraph("", cell), Paragraph("", cell),
        Paragraph("", cell), Paragraph("", cell),
        Paragraph("TOTAL", header),
        Paragraph("", cell),
        Paragraph(_inr(totals.get("order_value_excl_gst")), cell),
        Paragraph(_inr(totals.get("gst")), cell),
        Paragraph(_inr(totals.get("grand_total")), cell),
    ])

    usable = width - 56
    weights = [0.05, 0.09, 0.10, 0.14, 0.09, 0.14, 0.08, 0.12, 0.09, 0.10]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(AMBER))
    story.append(table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
