"""Lead analytics: filtered KPIs, comparisons, rows, and exports.

Aggregations run in PostgreSQL. Each lead is joined only to its current
status, source, product, and employee, so counts are not multiplied by
history or quotation rows.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import User
from app.services.analytics import (
    COMPARE_OPTIONS,
    LeadFilters,
    available_years,
    build_comparison,
    build_period_comparison,
    year_month_matrix,
    build_summary,
    iter_export_rows,
    meta_payload,
    query_rows,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

EXPORT_LIMIT = 20000


def _require(u: User) -> None:
    if not u.role or u.role.name not in {"ADMIN", "MANAGER"}:
        raise HTTPException(403, "Analytics is available to admins and managers")


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field}") from exc


def _ints(values: list[str] | None, field: str) -> list[int]:
    out = []
    for raw in values or []:
        if raw is None or str(raw).strip() == "":
            continue
        try:
            out.append(int(raw))
        except ValueError as exc:
            raise HTTPException(400, f"Invalid {field}") from exc
    return out


def _opt_int(value: str | None, field: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field}") from exc


def _ids(values: list[str], sentinel: str) -> tuple[list[UUID], bool]:
    ids: list[UUID] = []
    flag = False
    for raw in values:
        token = (raw or "").strip()
        if not token:
            continue
        if token == sentinel:
            flag = True
            continue
        try:
            ids.append(UUID(token))
        except ValueError as exc:
            raise HTTPException(400, "Invalid filter id") from exc
    return ids, flag


def _filters(
    year: list[str] | None,
    month: list[str] | None,
    from_date: str | None,
    to_date: str | None,
    lead_min: str | None,
    lead_max: str | None,
    quote_min: str | None,
    quote_max: str | None,
    category: list[str] | None,
    progress: list[str] | None,
    status: list[str] | None,
    source: list[str] | None,
    product: list[str] | None,
    employee: list[str] | None,
    city: list[str] | None,
    cars: list[str] | None,
    cars_min: str | None,
    cars_max: str | None,
    customer: str | None,
    enquiry: str | None,
    view: str | None,
) -> LeadFilters:
    start = _parse_date(from_date, "from date")
    end = _parse_date(to_date, "to date")
    if start and end and start > end:
        raise HTTPException(400, "From date is after to date")
    months = _ints(month, "month")
    if any(m < 1 or m > 12 for m in months):
        raise HTTPException(400, "Invalid month")
    source_ids, source_unspecified = _ids(source or [], "unspecified")
    product_ids, product_unmapped = _ids(product or [], "unmapped")
    employee_ids, employee_unassigned = _ids(employee or [], "unassigned")
    chosen_view = "historical" if (view or "").lower() == "historical" else "current"
    return LeadFilters(
        years=_ints(year, "year"),
        months=months,
        from_date=start,
        to_date=end,
        lead_min=_opt_int(lead_min, "minimum lead value"),
        lead_max=_opt_int(lead_max, "maximum lead value"),
        quote_min=_opt_int(quote_min, "minimum quotation value"),
        quote_max=_opt_int(quote_max, "maximum quotation value"),
        categories=[c for c in (category or []) if c],
        progress=[c for c in (progress or []) if c],
        statuses=[c for c in (status or []) if c],
        source_ids=source_ids,
        source_unspecified=source_unspecified,
        product_ids=product_ids,
        product_unmapped=product_unmapped,
        employee_ids=employee_ids,
        employee_unassigned=employee_unassigned,
        cities=[c for c in (city or []) if c],
        cars=[c for c in (cars or []) if c],
        cars_min=_opt_int(cars_min, "minimum cars"),
        cars_max=_opt_int(cars_max, "maximum cars"),
        customer=customer or "",
        enquiry=enquiry or "",
        view=chosen_view,
    )


def _common(
    year: list[str] = Query(default=[]),
    month: list[str] = Query(default=[]),
    from_date: str | None = None,
    to_date: str | None = None,
    lead_min: str | None = None,
    lead_max: str | None = None,
    quote_min: str | None = None,
    quote_max: str | None = None,
    category: list[str] = Query(default=[]),
    progress: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    product: list[str] = Query(default=[]),
    employee: list[str] = Query(default=[]),
    city: list[str] = Query(default=[]),
    cars: list[str] = Query(default=[]),
    cars_min: str | None = None,
    cars_max: str | None = None,
    customer: str | None = None,
    enquiry: str | None = None,
    view: str | None = None,
) -> LeadFilters:
    return _filters(
        year, month, from_date, to_date, lead_min, lead_max, quote_min, quote_max,
        category, progress, status, source, product, employee, city, cars, cars_min, cars_max,
        customer, enquiry, view,
    )


@router.get("/meta")
def analytics_meta(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require(u)
    return meta_payload(db)


@router.get("/summary")
def analytics_summary(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filters: LeadFilters = Depends(_common),
    ya: int | None = None,
    yb: int | None = None,
    a_from: str | None = None,
    a_to: str | None = None,
    b_from: str | None = None,
    b_to: str | None = None,
):
    _require(u)
    years = None
    if ya is not None or yb is not None:
        if ya is None or yb is None:
            raise HTTPException(400, "Choose both comparison years")
        years = (ya, yb)
    else:
        options = available_years(db)
        if len(options) >= 2:
            right = options[0]
            left = next((year for year in options if year < right), options[0] - 1)
            years = (left, right)
        elif options:
            years = (options[0] - 1, options[0])
    period_a = period_b = None
    if any([a_from, a_to, b_from, b_to]):
        start_a = _parse_date(a_from, "period A from")
        end_a = _parse_date(a_to, "period A to")
        start_b = _parse_date(b_from, "period B from")
        end_b = _parse_date(b_to, "period B to")
        if not all([start_a, end_a, start_b, end_b]):
            raise HTTPException(400, "Period comparison needs a from and to date on both sides")
        if start_a > end_a or start_b > end_b:
            raise HTTPException(400, "A comparison period starts after it ends")
        period_a = (start_a, end_a)
        period_b = (start_b, end_b)
    return build_summary(db, filters, years, period_a, period_b)


@router.get("/comparison")
def analytics_comparison(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filters: LeadFilters = Depends(_common),
    compare_by: str = "lead",
    measure: str | None = None,
    current_from: str | None = None,
    current_to: str | None = None,
    previous_from: str | None = None,
    previous_to: str | None = None,
):
    _require(u)
    kind = {"lead": "lead", "quotation": "quotation", "lead_value": "lead", "quotation_value": "quotation"}.get(compare_by)
    if kind and any([current_from, current_to, previous_from, previous_to, compare_by in {"lead", "quotation"}]):
        today = date.today()
        if not all([current_from, current_to, previous_from, previous_to]):
            current_end = today
            current_start = today - timedelta(days=27)
            previous_end = current_start - timedelta(days=1)
            previous_start = previous_end - timedelta(days=27)
        else:
            current_start = _parse_date(current_from, "current start")
            current_end = _parse_date(current_to, "current end")
            previous_start = _parse_date(previous_from, "previous start")
            previous_end = _parse_date(previous_to, "previous end")
            if not all([current_start, current_end, previous_start, previous_end]):
                raise HTTPException(400, "Comparison needs a start and end date on both periods")
        if current_start > current_end or previous_start > previous_end:
            raise HTTPException(400, "A comparison period starts after it ends")
        if (current_end - current_start).days > 1100 or (previous_end - previous_start).days > 1100:
            raise HTTPException(400, "Choose a range of 3 years or less")
        chosen_years = list(filters.years)
        # The period chart uses its own dates. Year comparison is separate.
        filters.years = []
        filters.months = []
        filters.from_date = None
        filters.to_date = None
        payload = build_period_comparison(
            db, filters, kind, current_start, current_end, previous_start, previous_end,
        )
        payload["year_comparison"] = year_month_matrix(db, filters, chosen_years, kind)
        return payload
    if compare_by not in COMPARE_OPTIONS:
        raise HTTPException(400, "Invalid compare by")
    try:
        return build_comparison(db, filters, compare_by, measure)
    except ValueError as exc:
        raise HTTPException(400, "Invalid compare by") from exc


@router.get("/rows")
def analytics_rows(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filters: LeadFilters = Depends(_common),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    sort: str = "date",
    dir: str = "desc",
):
    _require(u)
    direction = "asc" if dir == "asc" else "desc"
    return query_rows(db, filters, page=page, page_size=page_size, sort=sort, direction=direction)


def _export_table(db: Session, filters: LeadFilters) -> tuple[list[str], list[list], int]:
    headers = [
        "Enquiry", "Enquiry Date", "Customer", "City", "Contact", "Cars", "Product", "Source",
        "Status", "Progress", "Category", "Remarks", "Employee", "Lead Value", "Quotation Value",
    ]
    body = []
    total = 0
    for row in iter_export_rows(db, filters, EXPORT_LIMIT):
        total += 1
        contact = row["contact"]
        if row.get("email"):
            contact = f"{contact} | {row['email']}"
        body.append([
            row["enquiry_number"], row["enquiry_date"] or "—", row["customer_name"], row["city"],
            contact, row["cars"], row["product"], row["source"], row["status"], row["progress"],
            row["category"], row["remarks"], row["employee"],
            "" if row["lead_value"] is None else row["lead_value"],
            "" if row["quotation_value"] is None else row["quotation_value"],
        ])
    return headers, body, total


@router.get("/export")
def analytics_export(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filters: LeadFilters = Depends(_common),
    format: str = Query("xlsx", pattern="^(xlsx|csv|pdf)$"),
):
    _require(u)
    headers, body, total = _export_table(db, filters)
    stamp = datetime.now().strftime("%Y%m%d")
    if format == "csv":
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(body)
        payload = buffer.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            BytesIO(payload),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="lead-analytics-{stamp}.csv"'},
        )
    if format == "pdf":
        content = _pdf(headers, body, total)
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="lead-analytics-{stamp}.pdf"'},
        )
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(headers)
    for row in body:
        ws.append(row)
    if total >= EXPORT_LIMIT:
        ws.append([])
        ws.append([f"Export stopped at {EXPORT_LIMIT} rows. Narrow the filters to download the rest."])
    raw = BytesIO()
    wb.save(raw)
    raw.seek(0)
    return StreamingResponse(
        raw,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="lead-analytics-{stamp}.xlsx"'},
    )


def _pdf(headers: list[str], body: list[list], total: int) -> bytes:
    shown = body[:400]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=18)
    style = ParagraphStyle("cell", fontName="Helvetica", fontSize=7, leading=9)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.white)

    def cell(value, header=False):
        text = "" if value is None else str(value)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        return Paragraph(text or "—", head if header else style)

    data = [[cell(h, True) for h in headers]]
    for row in shown:
        data.append([cell(value) for value in row])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3F6212")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#E3E6DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    note = f"{total} lead(s) match the current filters."
    if total > len(shown):
        note += f" This PDF shows the first {len(shown)}. Download Excel for the full filtered list."
    story = [
        Paragraph("Lead analytics", ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14, textColor=colors.HexColor("#1C1E1A"))),
        Spacer(1, 6),
        Paragraph(note, ParagraphStyle("note", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#3F443B"))),
        Spacer(1, 8),
        table,
    ]
    doc.build(story)
    return buffer.getvalue()
