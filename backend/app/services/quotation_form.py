"""Editable EEPL-style quotation form PDF (REF EEPLCP…QnR0 template).

REF format: EEPLCP{DDMM}Q{n}R{rev}
  EEPLCP = Estar Engineers Pvt Ltd Car Parking
  DDMM   = enquiry date day+month (e.g. 1009 for 10 Sep)
  Qn     = quotation sequence reserved on form Save (open only previews the next count)
  Rn     = revision (R0 on first save, then R1, R2, … on later edits)
"""
from __future__ import annotations

import json
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
_DELIVERY_BODY = (
    "2 - 3 Months from the date of receipt of Advance payment along with PO or on-site readiness condition."
)
DEFAULT_DELIVERY_PERIOD = f"1. {_DELIVERY_BODY}"
DEFAULT_POST_WARRANTY = (
    "1. After the warranty period AMC is applicable.\n"
    "2. 3 - 4% of the Total cost per unit/year will be approximately charged for AMC."
)
DEFAULT_INTRODUCTION = (
    "E STAR Engineers Private Limited is a high-end Automated Multilevel Car/Auto/Bike "
    "Parking System, Design & Manufacturing Company in Association with International Tycoons "
    "from Japan, Germany & Korea, also a Group Company of MECHCI since 1995."
)


def normalize_delivery_period(text: str | None) -> str:
    """Keep the standard delivery line numbered as 1."""
    value = (text or "").strip()
    if not value or value == _DELIVERY_BODY:
        return DEFAULT_DELIVERY_PERIOD
    return value


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


def _quotation_row_is_issued(notes: str | None, amount_excl) -> bool:
    """Q count is reserved only after a real form save (issued), not on open/preview."""
    if amount_excl is not None:
        try:
            if float(amount_excl) > 0:
                return True
        except (TypeError, ValueError):
            pass
    raw = (notes or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except Exception:
        return False
    return bool(isinstance(data, dict) and data.get("issued"))


def next_quote_seq(db: Session) -> int:
    """Next global Q number = max issued Q in REF + 1 (open/preview does not count)."""
    rows = db.query(Quotation.quotation_number, Quotation.notes, Quotation.amount_excl).all()
    mx = 0
    for num, notes, amount in rows:
        if not _quotation_row_is_issued(notes, amount):
            continue
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
    on_date=None,
) -> str:
    """Build EEPLCP{DDMM}Q{n}R{rev}. DDMM follows on_date when the form date changes."""
    ddmm = enquiry_ddmm(lead, on_date)
    reuse = parse_quote_seq(existing_number) if existing_number else None
    if reuse is not None:
        q = reuse
    elif seq is not None:
        q = int(seq)
    else:
        q = next_quote_seq(db)
    return build_quotation_ref(ddmm, q, revision)


def ensure_quotation_on_assign(db: Session, lead: Lead) -> Quotation:
    """Create Draft quotation with next Qn when the employee first opens the form."""
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


def clean_extra_lines(lines) -> list[dict]:
    """Drop blank added rows. A typed amount with no units counts as 1 unit."""
    out = []
    for line in lines or []:
        if isinstance(line, dict):
            desc = str(line.get("description") or "").strip()
            cost = float(line.get("unit_cost") or 0)
            qty = float(line.get("units") or 0)
        else:
            desc = str(getattr(line, "description", "") or "").strip()
            cost = float(getattr(line, "unit_cost", 0) or 0)
            qty = float(getattr(line, "units", 0) or 0)
        if not desc and cost <= 0:
            continue
        if qty <= 0:
            qty = 1
        out.append({"description": desc, "unit_cost": int(round(cost)), "units": qty})
    return out


def calc_form_totals(unit_cost: float, units: float, extra_lines: list | None = None) -> dict:
    """GST is 18% of the sum of every row (first line plus added rows such as Transport)."""
    total = round(float(unit_cost or 0) * float(units or 0))
    for line in extra_lines or []:
        cost = float(line.get("unit_cost") or 0) if isinstance(line, dict) else float(getattr(line, "unit_cost", 0) or 0)
        qty = float(line.get("units") or 0) if isinstance(line, dict) else float(getattr(line, "units", 0) or 0)
        if qty <= 0 and cost:
            qty = 1
        total += round(cost * qty)
    gst = round(total * GST_RATE)
    return {"amount_excl": total, "gst": gst, "grand_total": total + gst}


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


def _twip(n: float) -> float:
    """Word spacing uses twips. 20 twips = 1 point."""
    return float(n) / 20.0


def _address_lines(text, style) -> list:
    """Keep each typed line on its own row. Blank lines stay as a gap."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")
    if not any(line.strip() for line in lines):
        return [Paragraph("—", style)]
    out = []
    for line in lines:
        if line.strip():
            out.append(Paragraph(escape(line.rstrip()), style))
        else:
            out.append(Spacer(1, _twip(80)))
    return out


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
    canvas.setFont("Times-Roman", 8)
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
        # Address banner from the quotation Word file: 171.4 mm wide, 24.8 mm tall.
        fw = 171.4 * mm
        fh = 24.8 * mm
        canvas.drawImage(
            str(FOOTER_BANNER),
            (page_w - fw) / 2,
            4 * mm,
            width=fw,
            height=fh,
            preserveAspectRatio=True,
            mask="auto",
        )
    canvas.restoreState()


def build_quotation_form_pdf(data: dict) -> bytes:
    """Build quotation PDF matching the EEPL Word letterhead and paragraph gaps."""
    from reportlab.platypus import Image, KeepTogether, PageBreak

    buffer = BytesIO()
    width, _height = A4
    # Logo ends near 32 mm; footer banner needs about 29 mm.
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=36 * mm, bottomMargin=30 * mm,
        title=data.get("quotation_number") or "Quotation",
        author="ESTAR Engineers Pvt Ltd",
    )

    # Readable letter spacing (Times New Roman). Only the empty gap after
    # Customer Scope is kept small by letting page-1 content breathe downward.
    body = ParagraphStyle(
        "body", fontName="Times-Roman", fontSize=11, leading=15,
        textColor=colors.HexColor("#1e293b"), spaceAfter=2,
    )
    bold = ParagraphStyle("bold", parent=body, fontName="Times-Bold")
    to_label = ParagraphStyle("to_label", parent=bold, leading=16, spaceAfter=2)
    addr = ParagraphStyle(
        "addr", fontName="Times-Bold", fontSize=10.5, leading=14,
        textColor=colors.HexColor("#1e293b"), spaceAfter=1,
    )
    small = ParagraphStyle(
        "small", fontName="Times-Roman", fontSize=10.5, leading=14,
        textColor=colors.HexColor("#334155"), spaceAfter=2,
    )
    term_item = ParagraphStyle("term_item", parent=small, spaceAfter=3)
    page2_item = ParagraphStyle("page2_item", parent=small, spaceAfter=4)
    section = ParagraphStyle(
        "section", parent=bold, fontSize=11, leading=15,
        spaceBefore=12, spaceAfter=6,
    )
    scope_section = ParagraphStyle(
        "scope_section", parent=section, spaceBefore=12, spaceAfter=6,
    )
    page2_section = ParagraphStyle(
        "page2_section", parent=section, spaceBefore=14, spaceAfter=6,
    )
    first_page2 = ParagraphStyle(
        "first_page2", parent=bold, fontSize=11, leading=15,
        spaceBefore=0, spaceAfter=6,
    )
    cell = ParagraphStyle("cell", fontName="Times-Roman", fontSize=11, leading=14, alignment=1)
    cell_left = ParagraphStyle("cell_l", fontName="Times-Roman", fontSize=11, leading=14, alignment=0)
    head = ParagraphStyle("head", parent=cell, fontName="Times-Bold", textColor=colors.white)
    dear = ParagraphStyle("dear", parent=bold, spaceAfter=8)
    subject_style = ParagraphStyle("subject", parent=bold, spaceBefore=2, spaceAfter=10)
    intro_style = ParagraphStyle("intro", parent=body, alignment=4, leading=15, spaceAfter=2)

    quote_date = data.get("quotation_date") or date.today().isoformat()
    if hasattr(quote_date, "isoformat"):
        quote_date = quote_date.isoformat()
    try:
        quote_date_disp = datetime.strptime(str(quote_date)[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        quote_date_disp = str(quote_date)

    ref = escape(str(data.get("quotation_number") or "—"))
    subject = escape(str(data.get("subject") or "Offer for Parking System"))
    desc = escape(str(data.get("product_description") or "Design, Manufacture, Supply and Erection of Parking System"))
    payment_terms = (data.get("payment_terms") or "").strip() or DEFAULT_PAYMENT_TERMS
    delivery_period = normalize_delivery_period(data.get("delivery_period"))
    post_warranty = (data.get("post_warranty") or "").strip() or DEFAULT_POST_WARRANTY
    unit_cost = float(data.get("unit_cost") or 0)
    units = float(data.get("units") or 0)
    extra_lines = data.get("extra_lines") or []
    totals = calc_form_totals(unit_cost, units, extra_lines)
    gst = totals["gst"]
    grand = totals["grand_total"]

    story = []
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
    story.append(Paragraph("<b>To</b>", to_label))
    story.append(Spacer(1, 4))
    story.extend(_address_lines(data.get("to_name"), addr))
    story.extend(_address_lines(data.get("to_address"), addr))
    story.append(Spacer(1, 14))
    story.append(Paragraph("<b>Dear Sir,</b>", dear))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Sub: - {subject}</b>", subject_style))
    intro = data.get("introduction")
    if intro is None:
        intro = DEFAULT_INTRODUCTION
    intro = str(intro).strip()
    if intro:
        story.extend(_multiline_paras(intro, intro_style))
    story.append(Spacer(1, 14))

    line_rows = [[
        Paragraph("1", cell),
        Paragraph(desc, cell_left),
        Paragraph(_inr_indian(unit_cost), cell),
        Paragraph(str(int(units) if units == int(units) else units), cell),
        Paragraph(_inr_indian(round(unit_cost * units)), cell),
    ]]
    for index, line in enumerate(extra_lines, start=2):
        if isinstance(line, dict):
            line_desc = str(line.get("description") or "")
            line_cost = float(line.get("unit_cost") or 0)
            line_units = float(line.get("units") or 0)
        else:
            line_desc = str(getattr(line, "description", "") or "")
            line_cost = float(getattr(line, "unit_cost", 0) or 0)
            line_units = float(getattr(line, "units", 0) or 0)
        if line_units <= 0 and line_cost:
            line_units = 1
        line_rows.append([
            Paragraph(str(index), cell),
            Paragraph(escape(line_desc), cell_left),
            Paragraph(_inr_indian(line_cost), cell),
            Paragraph(str(int(line_units) if line_units == int(line_units) else line_units), cell),
            Paragraph(_inr_indian(round(line_cost * line_units)), cell),
        ])
    rows = [
        [
            Paragraph("S. No", head),
            Paragraph("Description", head),
            Paragraph("Unit Cost (INR)", head),
            Paragraph("No of Units", head),
            Paragraph("Total Cost (INR)", head),
        ],
        *line_rows,
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
    table = Table(
        rows,
        colWidths=[usable * 0.08, usable * 0.42, usable * 0.18, usable * 0.14, usable * 0.18],
    )
    # Comfortable row height; page-1 Terms + Customer Scope stay together.
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))

    page1_tail = [
        Paragraph("<b>General Terms &amp; Conditions:</b>", section),
        *[Paragraph(escape(line), term_item) for line in [
            "1. GST and Other Taxes as extra applicable.",
            "2. This offer is valid for 15 days only.",
            "3. One-year Warranty and Maintenance on the installed system.",
        ]],
        Paragraph("<b>Customer Scope:</b>", scope_section),
        *[Paragraph(escape(line), term_item) for line in [
            "1. Approval from the Competent Authority. Site Clearance if required.",
            "2. Civil Foundations, Civil Works and Cladding are Additional",
            "3. 3 Phase Power Supply. Stabilized Power & dedicated Earth for installation and operation to be provided by the Client.",
            "4. The Client must provide an appropriate storage area at the site.",
        ]],
        # Small gap only — Payment Terms begin on the next page (same as the Word file).
        Spacer(1, 6),
    ]
    story.append(KeepTogether(page1_tail))

    story.append(PageBreak())
    story.append(Paragraph("<b>Payment Terms:</b>", first_page2))
    story.extend(_multiline_paras(payment_terms, page2_item))
    story.append(Paragraph("<b>Delivery Period:</b>", page2_section))
    story.extend(_multiline_paras(delivery_period, page2_item))
    story.append(Paragraph("<b>Post Warranty:</b>", page2_section))
    story.extend(_multiline_paras(post_warranty, page2_item))

    story.append(Spacer(1, 18))
    story.append(Paragraph("Regards,", ParagraphStyle("regards", parent=body, spaceAfter=6)))
    story.append(Paragraph(
        "For, <b>ESTAR ENGINEERS PRIVATE LIMITED</b>",
        ParagraphStyle("for_co", parent=body, spaceAfter=6),
    ))
    if SIGNATURE_IMG.exists():
        story.append(Image(str(SIGNATURE_IMG), width=22 * mm, height=24 * mm, kind="proportional", hAlign="LEFT"))
        story.append(Spacer(1, 6))
    else:
        story.append(Spacer(1, 16))
    story.append(Paragraph("<b>JAYARAMAN K</b>", ParagraphStyle("sign_name", parent=bold, spaceAfter=2)))
    story.append(Paragraph(
        "<b>Director</b>",
        ParagraphStyle("director", parent=bold, fontSize=9.5, leading=12, spaceAfter=14),
    ))
    story.append(Paragraph("<b>BANKING DETAILS:</b>", ParagraphStyle(
        "bank_head", parent=bold, leading=16, spaceAfter=4,
    )))
    bank_line = ParagraphStyle("bank_line", parent=small, leading=16, spaceAfter=2)
    for line in [
        "Account Name: E STAR ENGINEERS PRIVATE LIMITED",
        "Account Number: 8428210000009812",
        "Bank Name: DBS Bank",
        "Branch Name: Chennai",
        "Any RTGS/NEFT to our IFSC code: DBSS0IN0428",
    ]:
        story.append(Paragraph(escape(line), bank_line))

    doc.build(story, onFirstPage=_draw_letterhead_page, onLaterPages=_draw_letterhead_page)
    return buffer.getvalue()
