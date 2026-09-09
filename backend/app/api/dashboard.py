from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import Lead, LeadSource, LeadStatus, Product, Quotation, SiteVisit, User

router = APIRouter(prefix="/api", tags=["dashboard"])


def _xlsx_download(filename: str, headers: list[str], rows: list[list]):
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
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


def _kpis(db: Session):
    total = db.query(Lead).filter(Lead.is_active.is_(True)).count()
    by_status = dict(db.query(LeadStatus.name, func.count(Lead.id)).join(
        Lead, Lead.status_id == LeadStatus.id).filter(Lead.is_active.is_(True)).group_by(LeadStatus.name).all())
    new_lead = by_status.get("New Lead", 0)
    overdue = db.query(Lead).filter(Lead.sla_state == "OVERDUE", Lead.is_active.is_(True)).count()
    unassigned = db.query(Lead).filter(Lead.primary_employee_id.is_(None), Lead.is_active.is_(True)).count()
    return {"total": total, "by_status": by_status,
            "new_lead_actual": new_lead, "new_lead_display": min(new_lead, 5),
            "new_lead_capped": new_lead > 5, "sla_overdue": overdue,
            "unassigned": unassigned,
            "quotations": db.query(Quotation).count(), "visits": db.query(SiteVisit).count()}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), u: User = Depends(current_user)):
    d = _kpis(db)
    if d["new_lead_capped"]:
        d["warning"] = "New leads exceeded the threshold."
    return d


@router.get("/dashboard/by-source")
def by_source(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(LeadSource.name, LeadStatus.name, func.count(Lead.id)).join(
        Lead, Lead.source_id == LeadSource.id, isouter=True).join(
        LeadStatus, Lead.status_id == LeadStatus.id, isouter=True).filter(
        Lead.is_active.is_(True)).group_by(LeadSource.name, LeadStatus.name).all()
    out: dict = {}
    for src, st, c in rows:
        out.setdefault(src or "Unknown", {"total": 0})
        out[src or "Unknown"][st] = c
        out[src or "Unknown"]["total"] += c
    return out


def _product_wise_rows(db: Session):
    return [{"product": p or "Unmapped", "leads": c} for p, c in
            db.query(Product.name, func.count(Lead.id)).join(
                Lead, Lead.product_id == Product.id, isouter=True)
            .filter(Lead.is_active.is_(True)).group_by(Product.name)
            .order_by(func.count(Lead.id).desc()).all()]


def _source_wise_rows(db: Session):
    return [{"source": s or "Unknown", "leads": c} for s, c in
            db.query(LeadSource.name, func.count(Lead.id)).join(
                Lead, Lead.source_id == LeadSource.id, isouter=True)
            .filter(Lead.is_active.is_(True)).group_by(LeadSource.name)
            .order_by(func.count(Lead.id).desc()).all()]


@router.get("/reports/product-wise")
def product_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _product_wise_rows(db)


@router.get("/reports/product-wise/export")
def product_wise_export(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = _product_wise_rows(db)
    return _xlsx_download(
        "product-wise-report.xlsx",
        ["Product", "Leads"],
        [[r["product"], r["leads"]] for r in rows],
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


@router.get("/reports/employee-wise")
def employee_wise(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(User.name, func.count(Lead.id)).join(
        Lead, Lead.primary_employee_id == User.id, isouter=True).group_by(User.name).all()
    return [{"employee": n, "assigned": c} for n, c in rows]


@router.get("/reports/monthly")
def monthly(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(func.to_char(Lead.enquiry_date, "Mon-YY"), func.count(Lead.id)).filter(
        Lead.is_active.is_(True), Lead.enquiry_date.isnot(None)).group_by(
        func.to_char(Lead.enquiry_date, "Mon-YY")).all()
    return [{"month": m, "leads": c} for m, c in rows]


@router.get("/masters")
def masters(db: Session = Depends(get_db), u: User = Depends(current_user)):
    from app.models import Role
    staff = (
        db.query(User)
        .join(Role)
        .filter(User.is_active.is_(True), Role.name.in_(("EMPLOYEE", "MANAGER")))
        .order_by(User.name)
        .all()
    )
    return {
        "sources": [{"id": str(s.id), "name": s.name} for s in db.query(LeadSource).filter_by(is_active=True).all()],
        "products": [{"id": str(p.id), "name": p.name} for p in db.query(Product).filter_by(is_active=True).all()],
        "statuses": [{"id": str(s.id), "name": s.name} for s in db.query(LeadStatus).order_by(LeadStatus.sort_order).all()],
        "employees": [{"id": str(e.id), "name": e.name} for e in staff],
    }


@router.get("/notifications")
def notifs(db: Session = Depends(get_db), u: User = Depends(current_user)):
    from app.models import Notification
    rows = db.query(Notification).filter(Notification.user_id == u.id).order_by(Notification.created_at.desc()).limit(50).all()
    return [{"id": str(n.id), "title": n.title, "body": n.body, "is_read": n.is_read} for n in rows]
