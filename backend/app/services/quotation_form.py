"""Editable EEPL-style quotation form PDF (REF EEPLCP…QnR0 template).

REF format: EEPLCP{DDMM}Q{n}R{rev}
  EEPLCP = Estar Engineers Pvt Ltd Car Parking
  DDMM   = enquiry date day+month (e.g. 1009 for 10 Sep)
  Qn     = global quotation sequence (1st, 22nd, 76th, …)
  Rn     = revision (R0 on assign, then R1, R2, … on edits)
"""
from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models import Lead, Quotation


LOGO = Path(__file__).resolve().parents[1] / "assets" / "company-logo.jpg"
ASSETS = Path(__file__).resolve().parents[1] / "assets"
LETTERHEAD_LOGO = ASSETS / "quote-letterhead-logo.jpg"
FOOTER_BANNER = ASSETS / "quote-footer-banner.jpg"
SIGNATURE_IMG = ASSETS / "quote-signature.jpg"
NAVY = colors.HexColor("#1e3a5f")
GST_RATE = 0.18
_REF_Q_RE = re.compile(r"Q(\d+)R\d+", re.IGNORECASE)

DEFAULT_PAYMENT_TERMS = (
    "1. 60% Advance along with P.O\n"
    "2. 30% Advance for Structural Erection & Procurement\n"
    "3. 10% on successful Testing & Commissioning"
)
DEFAULT_DELIVERY_PERIOD = (
    "2 - 3 Months from the date of receipt of Advance payment along with PO or on-site readiness condition."
)
DEFAULT_POST_WARRANTY = (
    "1. After the warranty period AMC is applicable.\n"
    "2. 3 - 4% of the Total cost per unit/year will be approximately charged for AMC."
)


def enquiry_ddmm(lead: Lead | None = None, enquiry_date=None) -> str:
    """Day+month from enquiry date as DDMM (e.g. 1009)."""
    d = enquiry_date
    if d is None and lead is not None:
        d = lead.enquiry_date
    if d is None:
        d = date.today()
    if hasattr(d, "day") and hasattr(d, "month"):
        return f"{int(d.day):02d}{int(d.month):02d}"
    try:
        parsed = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        return f"{parsed.day:02d}{parsed.month:02d}"
    except ValueError:
        today = date.today()
        return f"{today.day:02d}{today.month:02d}"


def parse_quote_seq(quotation_number: str | None) -> int | None:
    if not quotation_number:
        return None
    m = _REF_Q_RE.search(str(quotation_number))
    return int(m.group(1)) if m else None


def next_quote_seq(db: Session) -> int:
    """Next global Q number = max existing Q in REF + 1 (or 1 if none)."""
    rows = db.query(Quotation.quotation_number).all()
    mx = 0
    for (num,) in rows:
        seq = parse_quote_seq(num)
        if seq is not None and seq > mx:
            mx = seq
    return mx + 1


def build_quotation_ref(ddmm: str, seq: int, revision: str = "R0") -> str:
    rev = (revision or "R0").strip().upper()
    if not rev.startswith("R"):
        rev = f"R{rev}"
    return f"EEPLCP{ddmm}Q{int(seq)}{rev}"


def build_quotation_number(
    db: Session,
    lead: Lead,
    revision: str = "R0",
    *,
    existing_number: str | None = None,
    seq: int | None = None,
) -> str:
    """Build EEPLCP{DDMM}Q{n}R{rev}. Reuses Q seq from existing REF when editing."""
    ddmm = enquiry_ddmm(lead)
    reuse = parse_quote_seq(existing_number) if existing_number else None
    if reuse is not None:
        q = reuse
    elif seq is not None:
        q = int(seq)
    else:
        q = next_quote_seq(db)
    return build_quotation_ref(ddmm, q, revision)


def ensure_quotation_on_assign(db: Session, lead: Lead) -> Quotation:
    """Create Draft quotation with REF …R0 when a lead is assigned (if none yet)."""
    existing = (
        db.query(Quotation)
        .filter_by(lead_id=lead.id)
        .order_by(Quotation.quotation_date.desc().nullslast(), Quotation.revision.desc())
        .first()
    )
    if existing is not None:
        return existing
    revision = "R0"
    ref = build_quotation_number(db, lead, revision)
    # Collision guard (unique quotation_number)
    tries = 0
    while db.query(Quotation).filter_by(quotation_number=ref).first() is not None and tries < 20:
        tries += 1
        ref = build_quotation_ref(enquiry_ddmm(lead), next_quote_seq(db) + tries, revision)
    quote = Quotation(
        lead_id=lead.id,
        quotation_number=ref,
        quotation_date=date.today(),
        revision=revision,
        units=float(lead.quantity_num) if lead.quantity_num is not None else None,
        amount_excl=None,
        gst=None,
        grand_total=None,
        status="Draft",
        notes="",
    )
    db.add(quote)
    db.flush()
    return quote


def _inr(n) -> str:
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    s = f"{v:,}"
    # Indian-style grouping approximation via en-IN not available; use western then fine for PDF
    return f"Rs. {s}"


def _inr_indian(n) -> str:
    """Format as Indian lakhs grouping (e.g. 55,00,000)."""
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    neg = v < 0
    v = abs(v)
    s = str(v)
    if len(s) <= 3:
        out = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        out = ",".join(reversed(parts)) + "," + last3
    return f"{'-' if neg else ''}{out}"


def calc_totals(unit_cost: float, units: float) -> dict:
    total = round(float(unit_cost or 0) * float(units or 0))
    gst = round(total * GST_RATE)
    grand = total + gst
    return {
        "amount_excl": total,
        "gst": gst,
        "grand_total": grand,
    }


def _logo_path() -> Path | None:
    if LETTERHEAD_LOGO.exists():
        return LETTERHEAD_LOGO
    return LOGO if LOGO.exists() else None


def _multiline_paras(text: str, style) -> list:
    paras = []
    for line in str(text or "").splitlines():
        line = line.rstrip()
        if line.strip():
            paras.append(Paragraph(escape(line), style))
    return paras or [Paragraph("", style)]


def _draw_letterhead_page(canvas, _doc):
    """Real EEPL letterhead: GURUKRIBA / Sree Laal above logo + footer banner."""
    canvas.saveState()
    page_w, page_h = A4
    logo = _logo_path()
    logo_w = 78 * mm
    logo_h = 18 * mm
    logo_x = (page_w - logo_w) / 2
    logo_y = page_h - 14 * mm - logo_h
    # Blessing lines sit above the logo (same positions as sent Word quotes):
    #   GURUKRIBA ………… centred over the E+star emblem (left half of logo)
    #   Sree Laal SidthBabaji … centred over the ESTAR wordmark (right half)
    canvas.setFillColor(colors.HexColor("#1e293b"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(logo_x + logo_w * 0.22, logo_y + logo_h + 4, "GURUKRIBA")
    canvas.drawCentredString(logo_x + logo_w * 0.72, logo_y + logo_h + 4, "Sree Laal SidthBabaji")
    if logo:
        canvas.drawImage(
            str(logo),
            logo_x,
            logo_y,
            width=logo_w,
            height=logo_h,
            preserveAspectRatio=True,
            mask="auto",
        )
    if FOOTER_BANNER.exists():
        fw = page_w - 20 * mm
        fh = 20 * mm
        canvas.drawImage(
            str(FOOTER_BANNER),
            10 * mm,
            6 * mm,
            width=fw,
            height=fh,
            preserveAspectRatio=True,
            mask="auto",
        )
    canvas.restoreState()


def build_quotation_form_pdf(data: dict) -> bytes:
    """Build quotation PDF matching the actual EEPL Word/PDF letterhead."""
    from reportlab.platypus import Image, PageBreak

    buffer = BytesIO()
    width, _height = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=38 * mm, bottomMargin=32 * mm,
        title=data.get("quotation_number") or "Quotation",
        author="ESTAR Engineers Pvt Ltd",
    )

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#1e293b"), spaceAfter=2)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=9, leading=13, textColor=colors.HexColor("#334155"), spaceAfter=2)
    section = ParagraphStyle("section", parent=bold, spaceBefore=10, spaceAfter=4)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
    cell_left = ParagraphStyle("cell_l", fontName="Helvetica", fontSize=9, leading=12, alignment=0)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)

    quote_date = data.get("quotation_date") or date.today().isoformat()
    if hasattr(quote_date, "isoformat"):
        quote_date = quote_date.isoformat()
    try:
        quote_date_disp = datetime.strptime(str(quote_date)[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        quote_date_disp = str(quote_date)

    ref = escape(str(data.get("quotation_number") or "—"))
    to_name = escape(str(data.get("to_name") or "—"))
    to_address = escape(str(data.get("to_address") or "—").replace("\n", "<br/>"))
    subject = escape(str(data.get("subject") or "Offer for Parking System"))
    desc = escape(str(data.get("product_description") or "Design, Manufacture, Supply and Erection of Parking System"))
    payment_terms = (data.get("payment_terms") or "").strip() or DEFAULT_PAYMENT_TERMS
    delivery_period = (data.get("delivery_period") or "").strip() or DEFAULT_DELIVERY_PERIOD
    post_warranty = (data.get("post_warranty") or "").strip() or DEFAULT_POST_WARRANTY
    unit_cost = float(data.get("unit_cost") or 0)
    units = float(data.get("units") or 0)
    totals = calc_totals(unit_cost, units)
    amount = totals["amount_excl"]
    gst = totals["gst"]
    grand = totals["grand_total"]

    story = []
    # REF left · Date flush right (same as sent quotes)
    ref_date = Table(
        [[
            Paragraph(f"<b>REF:</b> {ref}", body),
            Paragraph(f"<b>Date:</b> {escape(quote_date_disp)}", ParagraphStyle(
                "date_r", parent=body, alignment=2,
            )),
        ]],
        colWidths=[width * 0.55, width * 0.45 - 36 * mm],
    )
    ref_date.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(ref_date)
    story.append(Spacer(1, 14))
    story.append(Paragraph("<b>To</b>", bold))
    story.append(Spacer(1, 4))
    story.append(Paragraph(to_name, bold))
    story.append(Paragraph(to_address, small))
    story.append(Spacer(1, 14))
    story.append(Paragraph("Dear Sir,", body))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Sub: -</b> {subject}", body))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "E STAR Engineers Private Limited is a high-end Automated Multilevel Car/Auto/Bike "
        "Parking System, Design &amp; Manufacturing Company in Association with International Tycoons "
        "from Japan, Germany &amp; Korea, also a Group Company of MECHCI since 1995.",
        small,
    ))
    story.append(Spacer(1, 14))

    rows = [
        [
            Paragraph("S. No", head),
            Paragraph("Description", head),
            Paragraph("Unit Cost (INR)", head),
            Paragraph("No of Units", head),
            Paragraph("Total Cost (INR)", head),
        ],
        [
            Paragraph("1", cell),
            Paragraph(desc, cell_left),
            Paragraph(_inr_indian(unit_cost), cell),
            Paragraph(str(int(units) if units == int(units) else units), cell),
            Paragraph(_inr_indian(amount), cell),
        ],
        [
            Paragraph("", cell),
            Paragraph("GST 18%", cell_left),
            Paragraph("", cell),
            Paragraph("", cell),
            Paragraph(_inr_indian(gst), cell),
        ],
        [
            Paragraph("", cell),
            Paragraph("<b>GRAND TOTAL (INR)</b>", cell_left),
            Paragraph("", cell),
            Paragraph("", cell),
            Paragraph(f"<b>{_inr_indian(grand)}</b>", cell),
        ],
    ]
    usable = width - 36 * mm
    table = Table(rows, colWidths=[usable * 0.08, usable * 0.42, usable * 0.18, usable * 0.14, usable * 0.18])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("<b>General Terms &amp; Conditions:</b>", section))
    for line in [
        "1. GST and Other Taxes as extra applicable.",
        "2. This offer is valid for 15 days only.",
        "3. One-year Warranty and Maintenance on the installed system.",
    ]:
        story.append(Paragraph(escape(line), small))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Customer Scope:</b>", section))
    for line in [
        "1. Approval from the Competent Authority. Site Clearance if required.",
        "2. Civil Foundations, Civil Works and Cladding are Additional",
        "3. 3 Phase Power Supply. Stabilized Power & dedicated Earth for installation and operation to be provided by the Client.",
        "4. The Client must provide an appropriate storage area at the site.",
    ]:
        story.append(Paragraph(escape(line), small))

    # ——— Page 2: Payment / Delivery / Post Warranty / Sign / Banking ———
    story.append(PageBreak())
    story.append(Paragraph("<b>Payment Terms:</b>", section))
    story.extend(_multiline_paras(payment_terms, small))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Delivery Period:</b>", section))
    story.extend(_multiline_paras(delivery_period, small))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Post Warranty:</b>", section))
    story.extend(_multiline_paras(post_warranty, small))

    story.append(Spacer(1, 22))
    story.append(Paragraph("Regards,", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph("For, <b>ESTAR ENGINEERS PRIVATE LIMITED</b>", body))
    story.append(Spacer(1, 8))
    # Original order: signature sits between company line and printed name
    if SIGNATURE_IMG.exists():
        story.append(Image(str(SIGNATURE_IMG), width=22 * mm, height=24 * mm, kind="proportional", hAlign="LEFT"))
        story.append(Spacer(1, 4))
    else:
        story.append(Spacer(1, 16))
    story.append(Paragraph("<b>JAYARAMAN K</b>", bold))
    story.append(Paragraph("<b>Director</b>", small))
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>BANKING DETAILS:</b>", section))
    for line in [
        "Account Name: E STAR ENGINEERS PRIVATE LIMITED",
        "Account Number: 8428210000009812",
        "Bank Name: DBS Bank",
        "Branch Name: Chennai",
        "Any RTGS/NEFT to our IFSC code: DBSS0IN0428",
    ]:
        story.append(Paragraph(escape(line), small))

    doc.build(story, onFirstPage=_draw_letterhead_page, onLaterPages=_draw_letterhead_page)
    return buffer.getvalue()
