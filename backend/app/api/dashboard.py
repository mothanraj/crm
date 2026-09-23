from calendar import month_abbr, monthrange
from datetime import date, datetime, timedelta
from io import BytesIO
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import Lead, LeadActivity, LeadAssignment, LeadSource, LeadStatus, Notification, Product, Quotation, SiteVisit, User
from app.services.normalize import CANONICAL_PRODUCTS, CANONICAL_SOURCES, canonical_source
from app.services.pricing import PRODUCT_PRICES

router = APIRouter(prefix="/api", tags=["dashboard"])

# Status buckets used by Excel Details Report / Live Dashboard
STATUS_PROSPECT = "A - Prospect"
STATUS_FOLLOWUP = "In Followup"
STATUS_RNR = "RNR / Not reachable"
STATUS_NOT_INT = ("Not Interested", "Not Interested/Spam")
STATUS_QUOTE = "Quotation sent"
STATUS_CONVERTED = "Converted"
STATUS_PIPELINE = "A+ - Immediate"
STATUS_NEW = "New Lead"
STATUS_ASSIGNED = "Assigned"
STATUS_MEETING = "Meeting"
CUSTOMER_REVIEW_ORDER = ["A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (Planning Stage)"]
CUSTOMER_REVIEW_ALIASES = {
    "C (plan stage)": "C (Planning Stage)",
    "Planning Stage": "C (Planning Stage)",
}
DASHBOARD_MAPPED = {
    STATUS_FOLLOWUP, STATUS_PROSPECT, STATUS_RNR, STATUS_PIPELINE,
    "Not Interested", "Not Interested/Spam", STATUS_CONVERTED, STATUS_NEW,
    STATUS_ASSIGNED, STATUS_MEETING,
}


def _xlsx_download(filename: str, headers: list[str], rows: list[list], title: str = "Report"):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field}. Use YYYY-MM-DD") from exc


def _resolve_range(
    mode: str = "custom",
    month: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    week: str | None = None,
) -> tuple[date | None, date | None, str]:
    mode_l = (mode or "custom").lower().strip()
    if mode_l in ("month", "month-wise", "monthly"):
        if not month:
            today = date.today()
            month = f"{today.year:04d}-{today.month:02d}"
        try:
            y, m = map(int, month.split("-")[:2])
            start = date(y, m, 1)
            end = date(y, m, monthrange(y, m)[1])
        except Exception as exc:
            raise HTTPException(400, "Invalid month. Use YYYY-MM") from exc
        return start, end, "month"
    if mode_l in ("week", "weekly", "week-wise"):
        anchor = _parse_date(week or from_date, "week") or date.today()
        start = anchor - timedelta(days=anchor.weekday())  # Monday
        end = start + timedelta(days=6)
        return start, end, "week"
    start = _parse_date(from_date, "from_date")
    end = _parse_date(to_date, "to_date")
    today = date.today()
    if end and end > today:
        end = today
    if start and start > today:
        start = today
    if start and end and start > end:
        raise HTTPException(400, "from_date must be on or before to_date")
    return start, end, "custom"


def _is_employee(u: User | None) -> bool:
    return bool(u is not None and u.role is not None and u.role.name == "EMPLOYEE")


def _require_reports(u: User) -> None:
    if not u.role or u.role.name not in ("ADMIN", "MANAGER"):
        raise HTTPException(403, "Reports require an admin or manager role")


def _emp_clauses(u: User | None):
    return [Lead.primary_employee_id == u.id] if _is_employee(u) else []


def _date_filter(start: date | None, end: date | None, u: User | None = None):
    clauses = [Lead.is_active.is_(True), *_emp_clauses(u)]
    if start:
        clauses.append(Lead.enquiry_date >= start)
    if end:
        clauses.append(Lead.enquiry_date <= end)
    return and_(*clauses)


def _kpis(db: Session, u: User | None = None):
    emp = _emp_clauses(u)
    is_emp = _is_employee(u)
    total = db.query(Lead).filter(Lead.is_active.is_(True), *emp).count()
    by_status = dict(db.query(LeadStatus.name, func.count(Lead.id)).join(
        Lead, Lead.status_id == LeadStatus.id).filter(Lead.is_active.is_(True), *emp).group_by(LeadStatus.name).all())
    new_lead = by_status.get(STATUS_NEW, 0)
    overdue = db.query(Lead).filter(Lead.sla_state == "OVERDUE", Lead.is_active.is_(True), *emp).count()
    needs_first_contact = db.query(Lead).filter(
        Lead.is_active.is_(True),
        Lead.first_contact_at.is_(None),
        Lead.primary_employee_id.isnot(None),
        *emp,
    ).count()
    contacted = db.query(Lead).filter(
        Lead.is_active.is_(True), Lead.first_contact_at.isnot(None), *emp
    ).count()
    unassigned = 0 if is_emp else db.query(Lead).filter(Lead.primary_employee_id.is_(None), Lead.is_active.is_(True)).count()
    mapped = sum(by_status.get(s, 0) for s in DASHBOARD_MAPPED)
    latest_assignments = (
        db.query(LeadAssignment)
        .join(Lead, Lead.id == LeadAssignment.lead_id)
        .filter(LeadAssignment.is_current.is_(True), Lead.is_active.is_(True), *emp)
        .order_by(LeadAssignment.assigned_at.desc())
        .limit(5)
        .all()
    )
    latest_ids = [a.lead_id for a in latest_assignments]
    latest_leads = {x.id: x for x in db.query(Lead).filter(Lead.id.in_(latest_ids)).all()} if latest_ids else {}
    emp_ids = {x.primary_employee_id for x in latest_leads.values() if x.primary_employee_id}
    emp_map = {u.id: u.name for u in db.query(User).filter(User.id.in_(emp_ids)).all()} if emp_ids else {}
    latest_assigned = []
    for a in latest_assignments:
        lead = latest_leads.get(a.lead_id)
        if not lead:
            continue
        latest_assigned.append({
            "lead_id": str(lead.id),
            "enquiry_number": lead.enquiry_number,
            "customer_name": lead.customer_name or "—",
            "contact_number": lead.contact_number or "—",
            "email": lead.email or "",
            "quantity_raw": lead.quantity_raw or "",
            "employee": emp_map.get(lead.primary_employee_id, "—") if lead.primary_employee_id else "—",
            "assigned_date": a.assigned_at.strftime("%d-%b-%Y") if a.assigned_at else "—",
        })
    quoted_customers = []
    if not is_emp:
        for lead, employee_name in (
            db.query(Lead, User.name)
            .outerjoin(User, User.id == Lead.primary_employee_id)
            .filter(Lead.is_active.is_(True), Lead.quotation_value.isnot(None))
            .order_by(Lead.updated_at.desc()).all()
        ):
            quoted_customers.append({
                "lead_id": str(lead.id), "enquiry_number": lead.enquiry_number,
                "customer_name": lead.customer_name or "—", "employee": employee_name,
                "quotation_value": str(int(round(float(lead.quotation_value)))),
            })
    lead_value = _lead_value_analytics(db, u)
    return {
        "quoted_customers": quoted_customers,
        "total": total,
        "lead_value": lead_value,
        "total_lead_value": lead_value["total_lead_value"],
        "by_status": by_status,
        "funnel": {
            "total": total,
            "in_followup": by_status.get(STATUS_FOLLOWUP, 0),
            "prospect": by_status.get(STATUS_PROSPECT, 0),
            "rnr": by_status.get(STATUS_RNR, 0),
            "pipeline": by_status.get(STATUS_PIPELINE, 0),
            "site_visit": by_status.get("Site Visit", 0),
            "meeting": by_status.get(STATUS_MEETING, 0),
            "quotation_sent": by_status.get("Quotation sent", 0),
            "not_interested": by_status.get("Not Interested", 0) + by_status.get("Not Interested/Spam", 0),
            "converted": by_status.get(STATUS_CONVERTED, 0),
            "new_lead": new_lead,
            "assigned": by_status.get(STATUS_ASSIGNED, 0),
            "other": max(0, total - mapped),
        },
        "new_lead_actual": new_lead,
        # Business rule: the New Lead tile always reads 5 (last assigned customers).
        "new_lead_display": 5,
        "latest_assigned": latest_assigned,
        "new_lead_capped": new_lead > 5,
        "sla_overdue": overdue,
        "needs_first_contact": needs_first_contact,
        "contacted": contacted,
        "unassigned": unassigned,
        "quotations": (
            db.query(Quotation).join(Lead, Quotation.lead_id == Lead.id)
            .filter(Lead.is_active.is_(True), *emp).count()
            if is_emp else db.query(Quotation).count()
        ),
        "visits": (
            db.query(SiteVisit).join(Lead, SiteVisit.lead_id == Lead.id)
            .filter(Lead.is_active.is_(True), *emp).count()
            if is_emp else db.query(SiteVisit).count()
        ),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), u: User = Depends(current_user)):
    d = _kpis(db, u)
    if d["new_lead_capped"]:
        d["warning"] = "New leads exceeded the threshold."
    return d


def _as_rupee(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _lead_value_analytics(db: Session, u: User | None = None) -> dict:
    emp = _emp_clauses(u)
    total_leads = db.query(Lead).filter(Lead.is_active.is_(True), *emp).count()
    total_value = _as_rupee(
        db.query(func.coalesce(func.sum(Lead.lead_value), 0))
        .filter(Lead.is_active.is_(True), *emp).scalar() or 0
    )
    total_cars = int(round(float(
        db.query(func.coalesce(func.sum(Lead.quantity_num), 0))
        .filter(Lead.is_active.is_(True), *emp).scalar() or 0
    )))
    valued = db.query(Lead).filter(
        Lead.is_active.is_(True), Lead.lead_value.isnot(None), *emp,
    ).count()
    avg_value = _as_rupee(total_value / valued) if valued else 0

    rows = (
        db.query(Product.name, func.coalesce(func.sum(Lead.lead_value), 0), func.count(Lead.id))
        .select_from(Lead)
        .join(Product, Lead.product_id == Product.id)
        .filter(Lead.is_active.is_(True), *emp)
        .group_by(Product.name)
        .all()
    )
    by_name = {name: {"product": name, "lead_value": _as_rupee(val), "leads": int(cnt or 0)} for name, val, cnt in rows}
    by_product = [
        by_name.get(name) or {"product": name, "lead_value": 0, "leads": 0}
        for name in CANONICAL_PRODUCTS
    ]

    status_rows = (
        db.query(LeadStatus.name, func.coalesce(func.sum(Lead.lead_value), 0), func.count(Lead.id))
        .join(Lead, Lead.status_id == LeadStatus.id)
        .filter(Lead.is_active.is_(True), *emp)
        .group_by(LeadStatus.name)
        .all()
    )
    by_status = [
        {"status": st, "lead_value": _as_rupee(val), "leads": int(cnt or 0)}
        for st, val, cnt in status_rows
    ]
    return {
        "total_lead_value": total_value,
        "total_leads": total_leads,
        "total_cars": total_cars,
        "average_lead_value": avg_value,
        "by_product": by_product,
        "by_status": by_status,
    }


@router.get("/dashboard/lead-value")
def dashboard_lead_value(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _lead_value_analytics(db, u)


def _lead_value_for_range(db: Session, start: date | None, end: date | None, mode: str, u: User | None = None) -> dict:
    filters = _date_filter(start, end, u)
    total_leads = db.query(Lead).filter(filters).count()
    total_value = _as_rupee(
        db.query(func.coalesce(func.sum(Lead.lead_value), 0)).filter(filters).scalar() or 0
    )
    total_cars = int(round(float(
        db.query(func.coalesce(func.sum(Lead.quantity_num), 0)).filter(filters).scalar() or 0
    )))
    valued = db.query(Lead).filter(filters, Lead.lead_value.isnot(None)).count()
    avg_value = _as_rupee(total_value / valued) if valued else 0

    rows = (
        db.query(Product.name, func.coalesce(func.sum(Lead.lead_value), 0), func.count(Lead.id))
        .select_from(Lead)
        .join(Product, Lead.product_id == Product.id)
        .filter(filters)
        .group_by(Product.name)
        .all()
    )
    by_name = {
        name: {"product": name, "lead_value": _as_rupee(val), "leads": int(cnt or 0), "sources": "—"}
        for name, val, cnt in rows
    }

    # Distinct sources that contributed lead value for each product
    product_source_rows = (
        db.query(Product.name, LeadSource.name)
        .select_from(Lead)
        .join(Product, Lead.product_id == Product.id)
        .join(LeadSource, Lead.source_id == LeadSource.id)
        .filter(filters)
        .distinct()
        .all()
    )
    sources_by_product: dict[str, set[str]] = {}
    for product_name, source_name in product_source_rows:
        if not product_name or not source_name:
            continue
        sources_by_product.setdefault(product_name, set()).add(source_name)
    for product_name, sources in sources_by_product.items():
        if product_name in by_name:
            by_name[product_name]["sources"] = ", ".join(sorted(sources)) or "—"

    by_product = [
        by_name.get(name) or {"product": name, "lead_value": 0, "leads": 0, "sources": "—"}
        for name in CANONICAL_PRODUCTS
    ]

    source_rows = (
        db.query(LeadSource.name, func.coalesce(func.sum(Lead.lead_value), 0), func.count(Lead.id))
        .select_from(Lead)
        .join(LeadSource, Lead.source_id == LeadSource.id)
        .filter(filters)
        .group_by(LeadSource.name)
        .all()
    )
    by_source_name = {
        name: {"source": name, "lead_value": _as_rupee(val), "leads": int(cnt or 0)}
        for name, val, cnt in source_rows
    }
    by_source = [
        by_source_name.get(name) or {"source": name, "lead_value": 0, "leads": 0}
        for name in CANONICAL_SOURCES
    ]
    # Include any non-canonical sources that still have leads
    for name, row in sorted(by_source_name.items()):
        if name not in CANONICAL_SOURCES:
            by_source.append(row)

    # Period series: daily for week mode, weekly buckets otherwise
    period_rows = (
        db.query(Lead.enquiry_date, Lead.lead_value)
        .filter(filters, Lead.enquiry_date.isnot(None))
        .all()
    )
    buckets: dict[str, dict] = {}
    use_daily = mode == "week"

    def week_key(d: date) -> tuple[str, str]:
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        key = monday.isoformat()
        label = f"{monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')}"
        return key, label

    for enq_date, val in period_rows:
        if not enq_date:
            continue
        d = enq_date if isinstance(enq_date, date) else enq_date.date()
        if use_daily:
            key = d.isoformat()
            label = d.strftime("%d %b %Y")
        else:
            key, label = week_key(d)
        b = buckets.setdefault(key, {"period": key, "label": label, "lead_value": 0, "leads": 0})
        b["lead_value"] += _as_rupee(val)
        b["leads"] += 1

    by_period = [
        {**buckets[k], "lead_value": _as_rupee(buckets[k]["lead_value"])}
        for k in sorted(buckets.keys())
    ]
    return {
        "mode": mode,
        "from_date": start.isoformat() if start else None,
        "to_date": end.isoformat() if end else None,
        "total_lead_value": total_value,
        "total_leads": total_leads,
        "total_cars": total_cars,
        "average_lead_value": avg_value,
        "by_product": by_product,
        "by_source": by_source,
        "by_period": by_period,
    }


@router.get("/reports/lead-value")
def reports_lead_value(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    return _lead_value_for_range(db, start, end, resolved, u)


@router.get("/reports/lead-value/export")
def reports_lead_value_export(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    payload = _lead_value_for_range(db, start, end, resolved, u)
    headers = ["Product", "Sources", "Leads", "Lead Value"]
    body = [[r["product"], r.get("sources") or "—", r["leads"], r["lead_value"]] for r in payload["by_product"]]
    body.append(["TOTAL", "", payload["total_leads"], payload["total_lead_value"]])
    body.append(["", "", "", ""])
    body.append(["Source", "", "Leads", "Lead Value"])
    for r in payload.get("by_source") or []:
        body.append([r["source"], "", r["leads"], r["lead_value"]])
    body.append([
        "TOTAL",
        "",
        sum(int(r["leads"]) for r in (payload.get("by_source") or [])),
        sum(int(r["lead_value"]) for r in (payload.get("by_source") or [])),
    ])
    body.append(["", "", "", ""])
    body.append(["Period", "", "Leads", "Lead Value"])
    for r in payload["by_period"]:
        body.append([r.get("label") or r.get("period"), "", r["leads"], r["lead_value"]])
    return _xlsx_download(
        f"lead-value-{start or 'all'}-to-{end or 'all'}.xlsx",
        headers,
        body,
        title="Lead Value Report",
    )


def _as_rupee_int(v) -> int:
    try:
        return int(round(float(v or 0)))
    except Exception:
        return 0


def _quotation_report_payload(db: Session, start: date | None, end: date | None, mode: str) -> dict:
    """Quotation report (no Quotation Ref / Revision). Prefer quotations table; fall back to quoted leads."""
    from app.services.pricing import GST_RATE

    rows: list[dict] = []
    q = (
        db.query(Quotation, Lead, Product)
        .join(Lead, Quotation.lead_id == Lead.id)
        .outerjoin(Product, Lead.product_id == Product.id)
        .filter(Lead.is_active.is_(True))
    )
    if start:
        q = q.filter(func.coalesce(Quotation.quotation_date, Lead.enquiry_date) >= start)
    if end:
        q = q.filter(func.coalesce(Quotation.quotation_date, Lead.enquiry_date) <= end)
    quote_rows = q.order_by(func.coalesce(Quotation.quotation_date, Lead.enquiry_date).desc()).all()

    seen_leads: set = set()
    for quote, lead, product in quote_rows:
        seen_leads.add(lead.id)
        excl = quote.amount_excl
        gst = quote.gst
        grand = quote.grand_total
        if excl is None and grand is not None:
            excl = float(grand) / float(1 + GST_RATE)
            gst = float(grand) - float(excl)
        elif excl is not None and gst is None:
            gst = float(excl) * float(GST_RATE)
            if grand is None:
                grand = float(excl) + float(gst)
        units = quote.units if quote.units is not None else lead.quantity_num
        dt = quote.quotation_date or lead.enquiry_date
        rows.append({
            "date": dt.isoformat() if dt else None,
            "enquiry_number": lead.enquiry_number or "",
            "customer_name": lead.customer_name or "",
            "state": lead.city or "",
            "parking_type": (product.name if product else None) or lead.product_raw or "",
            "units": float(units) if units is not None else None,
            "order_value_excl_gst": _as_rupee_int(excl),
            "gst": _as_rupee_int(gst),
            "grand_total": _as_rupee_int(grand if grand is not None else (
                (float(excl or 0) + float(gst or 0)) if excl is not None else 0
            )),
        })

    lead_q = (
        db.query(Lead, Product, LeadStatus)
        .outerjoin(Product, Lead.product_id == Product.id)
        .join(LeadStatus, Lead.status_id == LeadStatus.id)
        .filter(
            Lead.is_active.is_(True),
            Lead.quotation_value.isnot(None),
            LeadStatus.name == STATUS_QUOTE,
        )
    )
    if start:
        lead_q = lead_q.filter(Lead.enquiry_date >= start)
    if end:
        lead_q = lead_q.filter(Lead.enquiry_date <= end)
    for lead, product, _st in lead_q.order_by(Lead.enquiry_date.desc()).all():
        if lead.id in seen_leads:
            continue
        excl = float(lead.quotation_value or 0)
        gst = excl * float(GST_RATE)
        rows.append({
            "date": lead.enquiry_date.isoformat() if lead.enquiry_date else None,
            "enquiry_number": lead.enquiry_number or "",
            "customer_name": lead.customer_name or "",
            "state": lead.city or "",
            "parking_type": (product.name if product else None) or lead.product_raw or "",
            "units": float(lead.quantity_num) if lead.quantity_num is not None else None,
            "order_value_excl_gst": _as_rupee_int(excl),
            "gst": _as_rupee_int(gst),
            "grand_total": _as_rupee_int(excl + gst),
        })

    totals = {
        "order_value_excl_gst": sum(r["order_value_excl_gst"] for r in rows),
        "gst": sum(r["gst"] for r in rows),
        "grand_total": sum(r["grand_total"] for r in rows),
        "count": len(rows),
    }
    return {
        "mode": mode,
        "effective_from": start.isoformat() if start else None,
        "effective_to": end.isoformat() if end else None,
        "rows": rows,
        "totals": totals,
    }


@router.get("/reports/quotations")
def reports_quotations(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    return _quotation_report_payload(db, start, end, resolved)


@router.get("/reports/quotations/export")
def reports_quotations_export(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    payload = _quotation_report_payload(db, start, end, resolved)
    headers = [
        "S.No", "Date", "Enquiry No", "Customer Name", "State", "Parking Type",
        "No. of Units/Cars", "Order Value (Excl GST)", "GST", "Grand Total",
    ]
    body = []
    for i, r in enumerate(payload["rows"], start=1):
        body.append([
            i, r["date"] or "", r["enquiry_number"], r["customer_name"], r["state"],
            r["parking_type"], r["units"] if r["units"] is not None else "",
            r["order_value_excl_gst"], r["gst"], r["grand_total"],
        ])
    t = payload["totals"]
    body.append([
        "", "", "", "", "", "TOTAL", "",
        t["order_value_excl_gst"], t["gst"], t["grand_total"],
    ])
    label = f"{payload['effective_from'] or 'all'}_to_{payload['effective_to'] or 'all'}"
    return _xlsx_download(f"quotation-report-{label}.xlsx", headers, body, title="Quotation Report")


def _by_source_matrix(db: Session, start: date | None = None, end: date | None = None, u: User | None = None) -> dict:
    # Single query from Lead: blank sources fold into "Others" via coalesce,
    # so each lead is counted exactly once.
    src_name = func.coalesce(LeadSource.name, "Others")
    rows = db.query(src_name, LeadStatus.name, func.count(Lead.id)).outerjoin(
        LeadSource, Lead.source_id == LeadSource.id
    ).outerjoin(LeadStatus, Lead.status_id == LeadStatus.id).filter(
        _date_filter(start, end, u)
    ).group_by(src_name, LeadStatus.name).all()
    out: dict = {name: {"total": 0} for name in CANONICAL_SOURCES}
    for src, st, c in rows:
        name = canonical_source(src)
        out.setdefault(name, {"total": 0})
        if st:
            out[name][st] = out[name].get(st, 0) + c
            out[name]["total"] += c
        elif c:
            out[name]["total"] += c
    return out


@router.get("/dashboard/by-source")
def by_source(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _by_source_matrix(db, u=u)


def _quote_sums_by_source(db: Session, start: date | None, end: date | None) -> dict[str, dict[str, float]]:
    """project_value = all quote totals; sales_amount = quotes on Converted leads."""
    q = (
        db.query(
            LeadSource.name,
            LeadStatus.name,
            func.coalesce(func.sum(Quotation.grand_total), 0),
        )
        .join(Lead, Quotation.lead_id == Lead.id)
        .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
        .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
        .filter(_date_filter(start, end))
        .group_by(LeadSource.name, LeadStatus.name)
        .all()
    )
    out: dict[str, dict[str, float]] = {}
    for src, st, amt in q:
        name = src or "Others"
        bucket = out.setdefault(name, {"project_value": 0.0, "sales_amount": 0.0})
        val = float(amt or 0)
        bucket["project_value"] += val
        if st == STATUS_CONVERTED:
            bucket["sales_amount"] += val
    return out


def _ordered_sources(matrix: dict) -> list[str]:
    seen = set()
    ordered = []
    for s in CANONICAL_SOURCES:
        if s in matrix:
            ordered.append(s)
            seen.add(s)
    for s in sorted(matrix.keys()):
        if s not in seen:
            ordered.append(s)
    return ordered


def _source_details_payload(db: Session, start: date | None, end: date | None, mode: str) -> dict:
    matrix = _by_source_matrix(db, start, end)
    rows = []
    totals = {
        "total": 0, "in_followup": 0, "meeting": 0, "site_visit": 0, "quote_sent": 0, "not_interested": 0,
    }
    for src in _ordered_sources(matrix):
        m = matrix[src]
        row = {
            "source": src,
            "total": int(m.get("total", 0)),
            "in_followup": int(m.get(STATUS_FOLLOWUP, 0)),
            "meeting": int(m.get("Meeting", 0)),
            "site_visit": int(m.get("Site Visit", 0)),
            "not_interested": int(sum(m.get(s, 0) for s in STATUS_NOT_INT)),
            "quote_sent": int(m.get(STATUS_QUOTE, 0)),
        }
        rows.append(row)
        for k in totals:
            totals[k] += row[k]
    return {
        "mode": mode,
        "effective_from": start.isoformat() if start else None,
        "effective_to": end.isoformat() if end else None,
        "rows": rows,
        "totals": totals,
    }


def _product_details_payload(db: Session, start: date | None, end: date | None, mode: str, u: User | None = None) -> dict:
    # Always list every canonical product (incl. zero-lead ones like Pit Stack Parking).
    rows_by_product: dict[str, dict] = {name: {"total": 0} for name in CANONICAL_PRODUCTS}
    query = (db.query(Product.name, LeadStatus.name, func.count(Lead.id))
             .select_from(Lead)
             .outerjoin(Product, Lead.product_id == Product.id)
             .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
             .filter(_date_filter(start, end, u))
             .group_by(Product.name, LeadStatus.name).all())
    for product, status, count in query:
        name = product or "Unmapped"
        row = rows_by_product.setdefault(name, {"total": 0})
        if status:
            row[status] = int(count)
        row["total"] += int(count)
    ordered = list(CANONICAL_PRODUCTS) + sorted(p for p in rows_by_product if p not in CANONICAL_PRODUCTS)
    rows = []
    totals = {"total": 0, "in_followup": 0, "meeting": 0, "site_visit": 0, "not_interested": 0, "quote_sent": 0}
    for product in ordered:
        data = rows_by_product[product]
        row = {"product": product, "total": data.get("total", 0),
               "in_followup": data.get(STATUS_FOLLOWUP, 0), "meeting": data.get("Meeting", 0),
               "site_visit": data.get("Site Visit", 0), "not_interested": sum(data.get(s, 0) for s in STATUS_NOT_INT),
               "quote_sent": data.get(STATUS_QUOTE, 0)}
        rows.append(row)
        for key in totals: totals[key] += row[key]
    return {"mode": mode, "effective_from": start.isoformat() if start else None,
            "effective_to": end.isoformat() if end else None, "rows": rows, "totals": totals}


@router.get("/dashboard/by-product")
def by_product(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _product_details_payload(db, None, None, "custom", u)


@router.get("/reports/product-details")
def product_details(db: Session = Depends(get_db), u: User = Depends(current_user), mode: str = Query("custom"), month: str | None = None, week: str | None = None, from_date: str | None = None, to_date: str | None = None):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    return _product_details_payload(db, start, end, resolved)


@router.get("/reports/product-details/export")
def product_details_export(db: Session = Depends(get_db), u: User = Depends(current_user), mode: str = Query("custom"), month: str | None = None, week: str | None = None, from_date: str | None = None, to_date: str | None = None):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    payload = _product_details_payload(db, start, end, resolved)
    headers = ["Product", "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Not Interested"]
    body = [[r["product"], r["total"], r["in_followup"], r["meeting"], r["site_visit"], r["quote_sent"], r["not_interested"]] for r in payload["rows"]]
    t = payload["totals"]
    body.append(["TOTAL", t["total"], t["in_followup"], t["meeting"], t["site_visit"], t["quote_sent"], t["not_interested"]])
    return _xlsx_download("product-wise-details.xlsx", headers, body, title="Product-wise Leads")


@router.get("/reports/source-details")
def source_details(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    return _source_details_payload(db, start, end, resolved)


@router.get("/reports/source-details/export")
def source_details_export(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require_reports(u)
    start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
    payload = _source_details_payload(db, start, end, resolved)
    headers = ["Lead Source", "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Not Interested"]
    body = []
    for r in payload["rows"]:
        body.append([
            r["source"], r["total"], r["in_followup"], r["meeting"], r["site_visit"], r["quote_sent"], r["not_interested"],
        ])
    t = payload["totals"]
    body.append([
        "TOTAL", t["total"], t["in_followup"], t["meeting"], t["site_visit"], t["quote_sent"], t["not_interested"],
    ])
    # Meta sheet row for range
    label = f"{payload['effective_from'] or 'all'}_to_{payload['effective_to'] or 'all'}"
    return _xlsx_download(
        f"leads-by-source-{label}.xlsx",
        headers,
        body,
        title="Leads by Source",
    )


@router.get("/reports/pdf")
def report_pdf(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    report_type: str = Query(..., pattern="^(source|product|lead_value|quotation|monthly|detailed)$"),
    mode: str = Query("custom"), month: str | None = None,
    week: str | None = None,
    from_date: str | None = None, to_date: str | None = None,
    from_month: str | None = None, to_month: str | None = None,
):
    _require_reports(u)
    from app.services.report_pdf import build_report_pdf

    if report_type == "monthly":
        start, end = _resolve_month_span(from_month, to_month)
        rows = _monthly_rows(db, u, start, end)
        content = build_report_pdf(
            {
                "rows": rows,
                "from_month": from_month,
                "to_month": to_month,
            },
            "monthly",
        )
        filename = "monthly-lead-volume.pdf"
    elif report_type == "detailed":
        start, end = _resolve_month_span(from_month, to_month)
        payload = _detailed_leads_payload(db, start, end, from_month, to_month)
        content = build_report_pdf(payload, "detailed")
        filename = "detailed-lead-report.pdf"
    else:
        start, end, resolved = _resolve_range(mode, month, from_date, to_date, week)
        if report_type == "lead_value":
            payload = _lead_value_for_range(db, start, end, resolved, u)
            content = build_report_pdf(payload, "lead_value")
            filename = "lead-value-report.pdf"
        elif report_type == "quotation":
            payload = _quotation_report_payload(db, start, end, resolved)
            content = build_report_pdf(payload, "quotation")
            filename = "quotation-report.pdf"
        else:
            payload_builder = _product_details_payload if report_type == "product" else _source_details_payload
            content = build_report_pdf(payload_builder(db, start, end, resolved), report_type)
            filename = f"{report_type}-report.pdf"
    return StreamingResponse(BytesIO(content), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _product_wise_rows(db: Session, start: date | None = None, end: date | None = None):
    filters = [Lead.is_active.is_(True)]
    if start:
        filters.append(Lead.enquiry_date >= start)
    if end:
        filters.append(Lead.enquiry_date <= end)
    counts = dict(
        db.query(Product.name, func.count(Lead.id))
        .outerjoin(Lead, and_(Lead.product_id == Product.id, *filters))
        .group_by(Product.name)
        .all()
    )
    # Always include every canonical product (zeros for unused ones like Pit Stack).
    rows = [{"product": name, "leads": int(counts.get(name, 0) or 0)} for name in CANONICAL_PRODUCTS]
    unmapped = db.query(func.count(Lead.id)).filter(
        Lead.product_id.is_(None), *filters).scalar() or 0
    extras = [
        {"product": name, "leads": int(c or 0)}
        for name, c in counts.items()
        if name and name not in CANONICAL_PRODUCTS and int(c or 0) > 0
    ]
    if unmapped:
        extras.append({"product": "Unmapped", "leads": int(unmapped)})
    extras.sort(key=lambda r: r["leads"], reverse=True)
    return rows + extras


def _source_wise_rows(db: Session):
    matrix = _by_source_matrix(db)
    return [{"source": name, "leads": matrix[name]["total"]} for name in _ordered_sources(matrix)]


def _customer_review_rows(db: Session):
    rows = dict(
        db.query(Lead.customer_review, func.count(Lead.id))
        .filter(Lead.is_active.is_(True))
        .group_by(Lead.customer_review)
        .all()
    )
    # Fold legacy labels into "C (Planning Stage)"
    for old, new in CUSTOMER_REVIEW_ALIASES.items():
        if old in rows:
            rows[new] = int(rows.get(new, 0) or 0) + int(rows.pop(old) or 0)
    allowed = set(CUSTOMER_REVIEW_ORDER)
    out = [{"customer_review": label, "leads": int(rows.get(label, 0) or 0)} for label in CUSTOMER_REVIEW_ORDER]
    other = sum(int(c or 0) for label, c in rows.items() if label and label not in allowed)
    blank = int(rows.get("", 0) or 0)
    if other:
        out.append({"customer_review": "Other", "leads": other})
    if blank:
        out.append({"customer_review": "Unreviewed", "leads": blank})
    return out


@router.get("/reports/product-wise")
def product_wise(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    mode: str = Query("custom"), month: str | None = None,
    week: str | None = None,
    from_date: str | None = None, to_date: str | None = None,
):
    _require_reports(u)
    start, end, _ = _resolve_range(mode, month, from_date, to_date, week)
    return _product_wise_rows(db, start, end)


@router.get("/reports/product-wise/export")
def product_wise_export(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    mode: str = Query("custom"), month: str | None = None,
    week: str | None = None,
    from_date: str | None = None, to_date: str | None = None,
):
    _require_reports(u)
    start, end, _ = _resolve_range(mode, month, from_date, to_date, week)
    rows = _product_wise_rows(db, start, end)
    return _xlsx_download(
        f"product-wise-report-{start or 'all'}-to-{end or 'all'}.xlsx",
        ["Product", "Leads"],
        [[r["product"], r["leads"]] for r in rows],
        title="Product-wise Leads",
    )


@router.get("/reports/source-wise")
def source_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_reports(u)
    return _source_wise_rows(db)


@router.get("/reports/source-wise/export")
def source_wise_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_reports(u)
    rows = _source_wise_rows(db)
    return _xlsx_download(
        "source-wise-report.xlsx",
        ["Lead Source", "Leads"],
        [[r["source"], r["leads"]] for r in rows],
    )


@router.get("/reports/customer-review")
def customer_review_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_reports(u)
    return _customer_review_rows(db)


@router.get("/reports/customer-review/export")
def customer_review_wise_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_reports(u)
    rows = _customer_review_rows(db)
    return _xlsx_download(
        "customer-review-report.xlsx",
        ["Customer Review", "Leads"],
        [[r["customer_review"], r["leads"]] for r in rows],
        title="Customer Review",
    )


@router.get("/reports/employee-wise")
def employee_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_reports(u)
    rows = db.query(User.name, func.count(Lead.id)).join(
        Lead, Lead.primary_employee_id == User.id, isouter=True).group_by(User.name).all()
    return [{"employee": n, "assigned": c} for n, c in rows]


def _parse_year_month(value: str | None, field: str) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        y, m = map(int, value.split("-")[:2])
        if m < 1 or m > 12:
            raise ValueError
        return y, m
    except Exception as exc:
        raise HTTPException(400, f"Invalid {field}. Use YYYY-MM") from exc


def _resolve_month_span(from_month: str | None, to_month: str | None) -> tuple[date | None, date | None]:
    """Optional inclusive month range (YYYY-MM → YYYY-MM)."""
    start_ym = _parse_year_month(from_month, "from_month")
    end_ym = _parse_year_month(to_month, "to_month")
    if not start_ym and not end_ym:
        return None, None
    if start_ym and not end_ym:
        end_ym = start_ym
    if end_ym and not start_ym:
        start_ym = end_ym
    assert start_ym and end_ym
    if start_ym > end_ym:
        raise HTTPException(400, "from_month must be on or before to_month")
    start = date(start_ym[0], start_ym[1], 1)
    end = date(end_ym[0], end_ym[1], monthrange(end_ym[0], end_ym[1])[1])
    return start, end


def _monthly_rows(db: Session, u: User | None = None, start: date | None = None, end: date | None = None):
    filters = [Lead.is_active.is_(True), Lead.enquiry_date.isnot(None), *_emp_clauses(u)]
    if start:
        filters.append(Lead.enquiry_date >= start)
    if end:
        filters.append(Lead.enquiry_date <= end)
    rows = (db.query(Lead, LeadStatus.name, LeadSource.name, Product.name)
            .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
            .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
            .outerjoin(Product, Lead.product_id == Product.id)
            .filter(*filters)
            .order_by(Lead.enquiry_date)
            .all())
    grouped = {}
    for lead, status_name, source_name, product_name in rows:
        dt = lead.enquiry_date
        # strftime('%b-%y') raises on Windows for years < 1900 (bad Excel dates
        # like 1899-12-30), so build the label without strftime.
        key = f"{dt.year:04d}-{dt.month:02d}"
        label = f"{month_abbr[dt.month]}-{dt.year % 100:02d}"
        item = grouped.setdefault(key, {
            "month_key": key, "month": label, "leads": 0,
            "in_followup": 0, "meeting": 0, "site_visit": 0,
            "quotation_sent": 0, "not_interested": 0,
            "sources": set(), "products": set(),
        })
        item["leads"] += 1
        if source_name: item["sources"].add(source_name)
        if product_name: item["products"].add(product_name)
        if status_name == STATUS_FOLLOWUP: item["in_followup"] += 1
        elif status_name == "Meeting": item["meeting"] += 1
        elif status_name == "Site Visit": item["site_visit"] += 1
        elif status_name == STATUS_QUOTE: item["quotation_sent"] += 1
        elif status_name in STATUS_NOT_INT: item["not_interested"] += 1
    result = []
    for key in sorted(grouped):
        item = grouped[key]
        item["sources"] = ", ".join(sorted(item["sources"])) or "—"
        item["products"] = ", ".join(sorted(item["products"])) or "—"
        result.append(item)
    return result


@router.get("/reports/monthly")
def monthly(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    from_month: str | None = None, to_month: str | None = None,
):
    _require_reports(u)
    start, end = _resolve_month_span(from_month, to_month)
    return _monthly_rows(db, u, start, end)


@router.get("/reports/monthly/export")
def monthly_export(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    from_month: str | None = None, to_month: str | None = None,
):
    _require_reports(u)
    start, end = _resolve_month_span(from_month, to_month)
    rows = _monthly_rows(db, u, start, end)
    return _xlsx_download(
        "monthly-lead-volume.xlsx",
        ["Month", "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Not Interested", "Lead Sources", "Products"],
        [[r["month"], r["leads"], r["in_followup"], r["meeting"], r["site_visit"], r["quotation_sent"], r["not_interested"], r["sources"], r["products"]] for r in rows],
        title="Monthly Volume",
    )


def _money_cell(n) -> str | None:
    if n is None or n == "":
        return None
    try:
        return str(int(round(float(n))))
    except (TypeError, ValueError):
        return None


def _numbered_lines(values: list[str]) -> str:
    cleaned = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not cleaned:
        return "—"
    if len(cleaned) == 1:
        return cleaned[0]
    return "\n".join(f"{i}. {v}" for i, v in enumerate(cleaned, 1))


def _detailed_leads_payload(
    db: Session,
    start: date | None,
    end: date | None,
    from_month: str | None = None,
    to_month: str | None = None,
) -> dict:
    """Row-level lead details (same fields as the Leads page) for a month span."""
    filters = [Lead.is_active.is_(True)]
    if start:
        filters.append(Lead.enquiry_date >= start)
    if end:
        filters.append(Lead.enquiry_date <= end)
    q = (
        db.query(
            Lead,
            LeadStatus.name,
            LeadSource.name,
            Product.name,
            User.name,
        )
        .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
        .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
        .outerjoin(Product, Lead.product_id == Product.id)
        .outerjoin(User, Lead.primary_employee_id == User.id)
        .filter(*filters)
        .order_by(Lead.enquiry_date.desc(), Lead.enquiry_number)
    )
    leads = q.all()
    lead_ids = [lead.id for lead, *_ in leads]
    history_by_lead: dict = defaultdict(list)
    if lead_ids:
        activities = (
            db.query(LeadActivity)
            .filter(
                LeadActivity.lead_id.in_(lead_ids),
                LeadActivity.activity_type == "Work Progress",
            )
            .order_by(LeadActivity.activity_at.asc())
            .all()
        )
        for a in activities:
            history_by_lead[a.lead_id].append({
                "remarks": (a.notes or "").strip(),
                "category": (a.customer_review or "").strip(),
                "progress": (a.outcome or "").strip(),
                "quotation_value": _money_cell(a.quotation_value),
                "at": a.activity_at.isoformat() if a.activity_at else None,
            })

    rows = []
    for lead, status_name, source_name, product_name, employee_name in leads:
        status = status_name or "—"
        if status == STATUS_NEW and lead.primary_employee_id:
            status = STATUS_ASSIGNED
        history = history_by_lead.get(lead.id) or []
        if history:
            categories = [h["category"] for h in history]
            remarks = [h["remarks"] for h in history]
            progress = [h["progress"] for h in history]
            # Prefer latest quotation from history when present
            quote_vals = [h["quotation_value"] for h in history if h.get("quotation_value")]
            quotation_value = quote_vals[-1] if quote_vals else _money_cell(lead.quotation_value)
        else:
            categories = [lead.customer_review or ""]
            remarks = [(lead.employee_remarks or "").strip()]
            progress = [status if status != "—" else ""]
            quotation_value = _money_cell(lead.quotation_value)
        rows.append({
            "enquiry_number": lead.enquiry_number or "—",
            "enquiry_date": lead.enquiry_date.isoformat() if lead.enquiry_date else "—",
            "customer_name": lead.customer_name or "—",
            "company_name": lead.company_name or "—",
            "city": lead.city or "—",
            "contact_number": lead.contact_number or "—",
            "email": lead.email or "—",
            "cars": lead.quantity_raw or ("—" if lead.quantity_num is None else str(int(lead.quantity_num))),
            "product": product_name or lead.product_raw or "—",
            "source": source_name or "—",
            "status": status,
            "category": _numbered_lines(categories),
            "remarks": _numbered_lines(remarks),
            "progress": _numbered_lines(progress),
            "work_history": history,
            "employee": employee_name or "Unassigned",
            "lead_value": _money_cell(lead.lead_value),
            "quotation_value": quotation_value,
        })
    return {
        "from_month": from_month,
        "to_month": to_month,
        "effective_from": start.isoformat() if start else None,
        "effective_to": end.isoformat() if end else None,
        "count": len(rows),
        "rows": rows,
    }


@router.get("/reports/detailed-leads")
def detailed_leads(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    from_month: str | None = None, to_month: str | None = None,
):
    _require_reports(u)
    start, end = _resolve_month_span(from_month, to_month)
    return _detailed_leads_payload(db, start, end, from_month, to_month)


@router.get("/reports/detailed-leads/export")
def detailed_leads_export(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    from_month: str | None = None, to_month: str | None = None,
):
    _require_reports(u)
    start, end = _resolve_month_span(from_month, to_month)
    payload = _detailed_leads_payload(db, start, end, from_month, to_month)
    headers = [
        "Enquiry No", "Enquiry Date", "Customer", "Company", "City", "Contact", "Email",
        "Cars", "Product", "Source", "Current Status", "Progress", "Category", "Employee",
        "Lead Value", "Quotation Value", "Remarks",
    ]
    body = [[
        r["enquiry_number"], r["enquiry_date"], r["customer_name"], r["company_name"], r["city"],
        r["contact_number"], r["email"], r["cars"], r["product"], r["source"], r["status"],
        r["progress"], r["category"], r["employee"], r["lead_value"] or "—", r["quotation_value"] or "—",
        r["remarks"],
    ] for r in payload["rows"]]
    return _xlsx_download("detailed-lead-report.xlsx", headers, body, title="Detailed Lead Report")


COMPARISON_CATEGORIES = ["A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (plan stage)"]
COMPARISON_ACTIONS = [
    "New Lead", "Assigned", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Converted", "Not Interested",
]
_SLICE_STATUSES = (
    "New Lead", "Assigned", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Converted", "Not Interested",
)


def _shift_months(d: date, months: int) -> date:
    month = d.month - months
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    last = monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def _comparison_windows(year: int | None, months: int | None) -> tuple[date, date, date, date, str, str]:
    today = date.today()
    if months:
        months = max(1, min(int(months), 24))
        current_end = today
        anchor = _shift_months(today, months - 1)
        current_start = date(anchor.year, anchor.month, 1)
        previous_end = current_start - timedelta(days=1)
        prev_anchor = _shift_months(previous_end, months - 1)
        previous_start = date(prev_anchor.year, prev_anchor.month, 1)
        return current_start, current_end, previous_start, previous_end, f"Last {months} months", f"Previous {months} months"
    chosen = year or today.year
    current_start, current_end = date(chosen, 1, 1), date(chosen, 12, 31)
    if chosen == today.year:
        current_end = today
    previous_start, previous_end = date(chosen - 1, 1, 1), date(chosen - 1, 12, 31)
    return current_start, current_end, previous_start, previous_end, str(chosen), str(chosen - 1)


def _lead_status_label(status_name: str | None, employee_id) -> str:
    status = status_name or ""
    if status == STATUS_NEW and employee_id:
        return STATUS_ASSIGNED
    if status in STATUS_NOT_INT:
        return "Not Interested"
    return status or "—"


def _status_bucket() -> dict:
    return {"total": 0, **{name: 0 for name in _SLICE_STATUSES}}


def _comparison_slice(db: Session, start: date, end: date, category: str | None, work_action: str | None) -> dict:
    rows = (
        db.query(Lead, LeadStatus.name, LeadSource.name, Product.name)
        .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
        .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
        .outerjoin(Product, Lead.product_id == Product.id)
        .filter(Lead.is_active.is_(True), Lead.enquiry_date >= start, Lead.enquiry_date <= end)
        .all()
    )
    by_category = {name: {"leads": 0, "lead_value": 0, "quotation_sent": 0, "quotation_value": 0} for name in COMPARISON_CATEGORIES}
    by_action = {name: {"leads": 0, "lead_value": 0, "quotation_sent": 0, "quotation_value": 0} for name in COMPARISON_ACTIONS}
    by_source = {name: _status_bucket() for name in CANONICAL_SOURCES}
    by_product = {name: _status_bucket() for name in CANONICAL_PRODUCTS}
    leads = lead_value = quotation_value = quotation_sent = 0
    for lead, status_name, source_name, product_name in rows:
        status = _lead_status_label(status_name, lead.primary_employee_id)
        cat = (lead.customer_review or "").strip()
        if category and cat != category:
            continue
        if work_action and status != work_action:
            continue
        value = int(round(float(lead.lead_value or 0)))
        quote = int(round(float(lead.quotation_value or 0)))
        sent = 1 if status == STATUS_QUOTE else 0
        leads += 1
        lead_value += value
        quotation_value += quote
        quotation_sent += sent
        if cat in by_category:
            by_category[cat]["leads"] += 1
            by_category[cat]["lead_value"] += value
            by_category[cat]["quotation_sent"] += sent
            by_category[cat]["quotation_value"] += quote
        if status in by_action:
            by_action[status]["leads"] += 1
            by_action[status]["lead_value"] += value
            by_action[status]["quotation_sent"] += sent
            by_action[status]["quotation_value"] += quote
        source = canonical_source(source_name or "")
        product = product_name or "Unmapped"
        by_source.setdefault(source, _status_bucket())
        by_product.setdefault(product, _status_bucket())
        for bucket in (by_source[source], by_product[product]):
            bucket["total"] += 1
            if status in _SLICE_STATUSES:
                bucket[status] += 1
    source_order = list(CANONICAL_SOURCES) + sorted(name for name in by_source if name not in CANONICAL_SOURCES)
    product_order = list(CANONICAL_PRODUCTS) + sorted(name for name in by_product if name not in CANONICAL_PRODUCTS)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "leads": leads,
        "lead_value": lead_value,
        "quotation_sent": quotation_sent,
        "quotation_value": quotation_value,
        "by_category": [{"name": name, **stats} for name, stats in by_category.items()],
        "by_action": [{"name": name, **stats} for name, stats in by_action.items()],
        "by_source": [{"name": name, **by_source[name]} for name in source_order],
        "by_product": [{"name": name, **by_product[name]} for name in product_order],
    }


@router.get("/dashboard/comparison")
def dashboard_comparison(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    year: int | None = None,
    months: int | None = Query(None, ge=1, le=24),
    category: str | None = None,
    work_action: str | None = None,
):
    if not u.role or u.role.name != "ADMIN":
        raise HTTPException(403, "Comparison is available to admins")
    if category and category not in COMPARISON_CATEGORIES:
        raise HTTPException(400, "Unknown category")
    if work_action and work_action not in COMPARISON_ACTIONS:
        raise HTTPException(400, "Unknown work action")
    cur_start, cur_end, prev_start, prev_end, cur_label, prev_label = _comparison_windows(year, months)
    years = [
        int(y) for (y,) in db.query(func.extract("year", Lead.enquiry_date))
        .filter(Lead.enquiry_date.isnot(None))
        .distinct()
        .all()
        if y is not None
    ]
    this_year = date.today().year
    if this_year not in years:
        years.append(this_year)
    return {
        "current_label": cur_label,
        "previous_label": prev_label,
        "years": sorted(set(years), reverse=True),
        "categories": COMPARISON_CATEGORIES,
        "work_actions": COMPARISON_ACTIONS,
        "current": _comparison_slice(db, cur_start, cur_end, category, work_action),
        "previous": _comparison_slice(db, prev_start, prev_end, category, work_action),
    }


@router.get("/masters")
def masters(db: Session = Depends(get_db), u: User = Depends(current_user)):
    from sqlalchemy.orm import joinedload
    from app.models import Role
    staff = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name.in_(("EMPLOYEE", "MANAGER")))
        .options(joinedload(User.role))
        .order_by(User.name)
        .all()
    )
    products = (
        db.query(Product)
        .filter_by(is_active=True)
        .order_by(Product.name)
        .all()
    )
    # Keep canonical order for the 7 parking products
    order = {n: i for i, n in enumerate(CANONICAL_PRODUCTS)}
    products.sort(key=lambda p: order.get(p.name, 100 + hash(p.name) % 50))
    return {
        "sources": [{"id": str(s.id), "name": s.name} for s in db.query(LeadSource).filter_by(is_active=True).all()],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "price_per_car": int(round(float(p.price_per_car or PRODUCT_PRICES.get(p.name, 0) or 0))),
                "gst_percent": 18,
            }
            for p in products
            if p.name in PRODUCT_PRICES
        ],
        "statuses": [{"id": str(s.id), "name": s.name} for s in db.query(LeadStatus).order_by(LeadStatus.sort_order).all()],
        "customer_reviews": CUSTOMER_REVIEW_ORDER,
        "employees": [{"id": str(e.id), "name": e.name} for e in staff],
    }


@router.get("/notifications")
def notifs(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(Notification).filter(Notification.user_id == u.id).order_by(Notification.created_at.desc()).limit(50).all()
    return [{"id": str(n.id), "title": n.title, "body": n.body, "is_read": n.is_read,
             "kind": n.kind, "lead_id": str(n.lead_id) if n.lead_id else None,
             "created_at": n.created_at.isoformat() if n.created_at else None} for n in rows]


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), u: User = Depends(current_user)):
    db.query(Notification).filter(
        Notification.user_id == u.id, Notification.is_read.is_(False),
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read")
def mark_read(nid: UUID, db: Session = Depends(get_db), u: User = Depends(current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != u.id:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}
