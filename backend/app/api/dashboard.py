from calendar import monthrange
from datetime import date, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import Lead, LeadAssignment, LeadSource, LeadStatus, Product, Quotation, SiteVisit, User
from app.services.normalize import CANONICAL_PRODUCTS, CANONICAL_SOURCES

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
CUSTOMER_REVIEW_ORDER = ["A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (plan stage)"]
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
    start = _parse_date(from_date, "from_date")
    end = _parse_date(to_date, "to_date")
    if start and end and start > end:
        raise HTTPException(400, "from_date must be on or before to_date")
    return start, end, "custom"


def _is_employee(u: User | None) -> bool:
    return bool(u is not None and u.role is not None and u.role.name == "EMPLOYEE")


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
            "employee": emp_map.get(lead.primary_employee_id, "—") if lead.primary_employee_id else "—",
            "assigned_date": a.assigned_at.strftime("%d-%b-%Y") if a.assigned_at else "—",
        })
    return {
        "total": total,
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


def _by_source_matrix(db: Session, start: date | None = None, end: date | None = None, u: User | None = None) -> dict:
    # Single query from Lead: blank sources fold into "Others" via coalesce,
    # so each lead is counted exactly once.
    src_name = func.coalesce(LeadSource.name, "Others")
    rows = db.query(src_name, LeadStatus.name, func.count(Lead.id)).outerjoin(
        LeadSource, Lead.source_id == LeadSource.id
    ).outerjoin(LeadStatus, Lead.status_id == LeadStatus.id).filter(
        _date_filter(start, end, u)
    ).group_by(src_name, LeadStatus.name).all()
    out: dict = {}
    for src, st, c in rows:
        name = src or "Others"
        out.setdefault(name, {"total": 0})
        if st:
            out[name][st] = c
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
    money = _quote_sums_by_source(db, start, end)
    rows = []
    totals = {
        "total": 0, "in_followup": 0, "prospect": 0, "rnr": 0, "not_interested": 0,
        "quote_sent": 0, "project_value": 0.0, "converted": 0, "sales_amount": 0.0,
    }
    for src in _ordered_sources(matrix):
        m = matrix[src]
        money_row = money.get(src, {"project_value": 0.0, "sales_amount": 0.0})
        row = {
            "source": src,
            "total": int(m.get("total", 0)),
            "in_followup": int(m.get(STATUS_FOLLOWUP, 0)),
            "prospect": int(m.get(STATUS_PROSPECT, 0)),
            "rnr": int(m.get(STATUS_RNR, 0)),
            "not_interested": int(sum(m.get(s, 0) for s in STATUS_NOT_INT)),
            "quote_sent": int(m.get(STATUS_QUOTE, 0)),
            "project_value": round(float(money_row["project_value"]), 2),
            "converted": int(m.get(STATUS_CONVERTED, 0)),
            "sales_amount": round(float(money_row["sales_amount"]), 2),
        }
        row["conv_pct"] = round((row["converted"] / row["total"] * 100), 1) if row["total"] else 0.0
        rows.append(row)
        for k in totals:
            totals[k] += row[k]
    totals["project_value"] = round(totals["project_value"], 2)
    totals["sales_amount"] = round(totals["sales_amount"], 2)
    totals["conv_pct"] = round((totals["converted"] / totals["total"] * 100), 1) if totals["total"] else 0.0
    return {
        "mode": mode,
        "effective_from": start.isoformat() if start else None,
        "effective_to": end.isoformat() if end else None,
        "rows": rows,
        "totals": totals,
    }


def _product_details_payload(db: Session, start: date | None, end: date | None, mode: str) -> dict:
    rows_by_product: dict[str, dict] = {}
    query = (db.query(Product.name, LeadStatus.name, func.count(Lead.id))
             .join(Lead, Lead.product_id == Product.id)
             .join(LeadStatus, Lead.status_id == LeadStatus.id)
             .filter(_date_filter(start, end))
             .group_by(Product.name, LeadStatus.name).all())
    for product, status, count in query:
        row = rows_by_product.setdefault(product or "Unmapped", {"total": 0})
        row[status] = int(count)
        row["total"] += int(count)
    ordered = [p for p in CANONICAL_PRODUCTS if p in rows_by_product]
    ordered += sorted(p for p in rows_by_product if p not in ordered)
    rows = []
    totals = {"total": 0, "in_followup": 0, "prospect": 0, "rnr": 0, "not_interested": 0, "quote_sent": 0, "converted": 0}
    for product in ordered:
        data = rows_by_product[product]
        row = {"product": product, "total": data.get("total", 0),
               "in_followup": data.get(STATUS_FOLLOWUP, 0), "prospect": data.get(STATUS_PROSPECT, 0),
               "rnr": data.get(STATUS_RNR, 0), "not_interested": sum(data.get(s, 0) for s in STATUS_NOT_INT),
               "quote_sent": data.get(STATUS_QUOTE, 0), "converted": data.get(STATUS_CONVERTED, 0)}
        row["conv_pct"] = round(row["converted"] / row["total"] * 100, 1) if row["total"] else 0.0
        rows.append(row)
        for key in totals: totals[key] += row[key]
    totals["conv_pct"] = round(totals["converted"] / totals["total"] * 100, 1) if totals["total"] else 0.0
    return {"mode": mode, "effective_from": start.isoformat() if start else None,
            "effective_to": end.isoformat() if end else None, "rows": rows, "totals": totals}


@router.get("/reports/product-details")
def product_details(db: Session = Depends(get_db), u: User = Depends(current_user), mode: str = Query("custom"), month: str | None = None, from_date: str | None = None, to_date: str | None = None):
    start, end, resolved = _resolve_range(mode, month, from_date, to_date)
    return _product_details_payload(db, start, end, resolved)


@router.get("/reports/product-details/export")
def product_details_export(db: Session = Depends(get_db), u: User = Depends(current_user), mode: str = Query("custom"), month: str | None = None, from_date: str | None = None, to_date: str | None = None):
    start, end, resolved = _resolve_range(mode, month, from_date, to_date)
    payload = _product_details_payload(db, start, end, resolved)
    headers = ["Product", "Total", "In Followup", "Prospect", "RNR", "Not Int.", "Quote Sent", "Converted", "Conv. %"]
    body = [[r["product"], r["total"], r["in_followup"], r["prospect"], r["rnr"], r["not_interested"], r["quote_sent"], r["converted"], r["conv_pct"]] for r in payload["rows"]]
    t = payload["totals"]
    body.append(["TOTAL", t["total"], t["in_followup"], t["prospect"], t["rnr"], t["not_interested"], t["quote_sent"], t["converted"], t["conv_pct"]])
    return _xlsx_download("product-wise-details.xlsx", headers, body, title="Product-wise Leads")


@router.get("/reports/source-details")
def source_details(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    start, end, resolved = _resolve_range(mode, month, from_date, to_date)
    return _source_details_payload(db, start, end, resolved)


@router.get("/reports/source-details/export")
def source_details_export(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    mode: str = Query("custom"),
    month: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    start, end, resolved = _resolve_range(mode, month, from_date, to_date)
    payload = _source_details_payload(db, start, end, resolved)
    headers = [
        "Lead Source", "Total", "In Followup", "Prospect", "RNR", "Not Int.",
        "Quote Sent", "Project Value (Rs.)", "Converted", "Sales Amount (Rs.)", "Conv. %",
    ]
    body = []
    for r in payload["rows"]:
        body.append([
            r["source"], r["total"], r["in_followup"], r["prospect"], r["rnr"],
            r["not_interested"], r["quote_sent"], r["project_value"], r["converted"],
            r["sales_amount"], r["conv_pct"],
        ])
    t = payload["totals"]
    body.append([
        "TOTAL", t["total"], t["in_followup"], t["prospect"], t["rnr"],
        t["not_interested"], t["quote_sent"], t["project_value"], t["converted"],
        t["sales_amount"], t["conv_pct"],
    ])
    # Meta sheet row for range
    label = f"{payload['effective_from'] or 'all'}_to_{payload['effective_to'] or 'all'}"
    return _xlsx_download(
        f"leads-by-source-{label}.xlsx",
        headers,
        body,
        title="Leads by Source",
    )


def _product_wise_rows(db: Session, start: date | None = None, end: date | None = None):
    filters = [Lead.is_active.is_(True)]
    if start:
        filters.append(Lead.enquiry_date >= start)
    if end:
        filters.append(Lead.enquiry_date <= end)
    rows = [{"product": p or "Unmapped", "leads": c} for p, c in
            db.query(Product.name, func.count(Lead.id)).outerjoin(
                Lead, and_(Lead.product_id == Product.id, *filters))
            .group_by(Product.name)
            .order_by(func.count(Lead.id).desc()).all()]
    unmapped = db.query(func.count(Lead.id)).filter(
        Lead.product_id.is_(None), *filters).scalar() or 0
    if unmapped:
        rows.append({"product": "Unmapped", "leads": unmapped})
        rows.sort(key=lambda r: r["leads"], reverse=True)
    return rows


def _source_wise_rows(db: Session):
    rows = [{"source": s or "Unknown", "leads": c} for s, c in
            db.query(LeadSource.name, func.count(Lead.id)).outerjoin(
                Lead, and_(Lead.source_id == LeadSource.id, Lead.is_active.is_(True)))
            .group_by(LeadSource.name)
            .order_by(func.count(Lead.id).desc()).all()]
    unmapped = db.query(func.count(Lead.id)).filter(
        Lead.is_active.is_(True), Lead.source_id.is_(None)).scalar() or 0
    if unmapped:
        rows.append({"source": "Unknown", "leads": unmapped})
        rows.sort(key=lambda r: r["leads"], reverse=True)
    return rows


def _customer_review_rows(db: Session):
    rows = dict(
        db.query(Lead.customer_review, func.count(Lead.id))
        .filter(Lead.is_active.is_(True))
        .group_by(Lead.customer_review)
        .all()
    )
    out = [{"customer_review": label, "leads": int(rows.get(label, 0) or 0)} for label in CUSTOMER_REVIEW_ORDER]
    other = sum(int(c or 0) for label, c in rows.items() if label and label not in CUSTOMER_REVIEW_ORDER)
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
    from_date: str | None = None, to_date: str | None = None,
):
    start, end, _ = _resolve_range(mode, month, from_date, to_date)
    return _product_wise_rows(db, start, end)


@router.get("/reports/product-wise/export")
def product_wise_export(
    db: Session = Depends(get_db), u: User = Depends(current_user),
    mode: str = Query("custom"), month: str | None = None,
    from_date: str | None = None, to_date: str | None = None,
):
    start, end, _ = _resolve_range(mode, month, from_date, to_date)
    rows = _product_wise_rows(db, start, end)
    return _xlsx_download(
        f"product-wise-report-{start or 'all'}-to-{end or 'all'}.xlsx",
        ["Product", "Leads"],
        [[r["product"], r["leads"]] for r in rows],
        title="Product-wise Leads",
    )


@router.get("/reports/source-wise")
def source_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _source_wise_rows(db)


@router.get("/reports/source-wise/export")
def source_wise_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = _source_wise_rows(db)
    return _xlsx_download(
        "source-wise-report.xlsx",
        ["Lead Source", "Leads"],
        [[r["source"], r["leads"]] for r in rows],
    )


@router.get("/reports/customer-review")
def customer_review_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _customer_review_rows(db)


@router.get("/reports/customer-review/export")
def customer_review_wise_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = _customer_review_rows(db)
    return _xlsx_download(
        "customer-review-report.xlsx",
        ["Customer Review", "Leads"],
        [[r["customer_review"], r["leads"]] for r in rows],
        title="Customer Review",
    )


@router.get("/reports/employee-wise")
def employee_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(User.name, func.count(Lead.id)).join(
        Lead, Lead.primary_employee_id == User.id, isouter=True).group_by(User.name).all()
    return [{"employee": n, "assigned": c} for n, c in rows]


def _monthly_rows(db: Session, u: User | None = None):
    month_key = func.to_char(Lead.enquiry_date, "YYYY-MM")
    month_label = func.to_char(Lead.enquiry_date, "Mon-YY")
    converted = func.sum(case((LeadStatus.name == STATUS_CONVERTED, 1), else_=0))
    rows = (
        db.query(month_key, month_label, func.count(Lead.id), converted)
        .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
        .filter(Lead.is_active.is_(True), Lead.enquiry_date.isnot(None), *_emp_clauses(u))
        .group_by(month_key, month_label)
        .order_by(month_key)
        .all()
    )
    return [{"month_key": k, "month": label, "leads": int(c), "converted": int(conv or 0)} for k, label, c, conv in rows]


@router.get("/reports/monthly")
def monthly(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _monthly_rows(db, u)


@router.get("/reports/monthly/export")
def monthly_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = _monthly_rows(db, u)
    return _xlsx_download(
        "monthly-lead-volume.xlsx",
        ["Month", "Total Leads", "Converted"],
        [[r["month"], r["leads"], r["converted"]] for r in rows],
        title="Monthly Volume",
    )


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
    return {
        "sources": [{"id": str(s.id), "name": s.name} for s in db.query(LeadSource).filter_by(is_active=True).all()],
        "products": [{"id": str(p.id), "name": p.name} for p in db.query(Product).filter_by(is_active=True).all()],
        "statuses": [{"id": str(s.id), "name": s.name} for s in db.query(LeadStatus).order_by(LeadStatus.sort_order).all()],
        "customer_reviews": CUSTOMER_REVIEW_ORDER,
        "employees": [{"id": str(e.id), "name": e.name} for e in staff],
    }


@router.get("/notifications")
def notifs(db: Session = Depends(get_db), u: User = Depends(current_user)):
    from app.models import Notification
    rows = db.query(Notification).filter(Notification.user_id == u.id).order_by(Notification.created_at.desc()).limit(50).all()
    return [{"id": str(n.id), "title": n.title, "body": n.body, "is_read": n.is_read} for n in rows]
