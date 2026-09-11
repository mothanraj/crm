from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.deps import admin_only, current_user
from app.db.session import get_db

log = logging.getLogger(__name__)
from app.models import (
    ImportBatch, ImportError, Lead, LeadActivity, LeadAssignment, LeadDocument,
    LeadSource, LeadStatus, LeadStatusHistory, Notification, Product, Quotation, SiteVisit, User,
)
from app.schemas import ActivityIn, AssignIn, ContactIn, LeadCreate, LeadUpdate, QuoteIn, StatusChange, VisitIn
from app.services.lead_service import assign, auto_assign, change_status, next_enquiry_number, record_first_contact
from app.services.normalize import (
    EMPLOYEE_ALIASES, PRODUCT_ALIASES, SOURCE_ALIASES, STATUS_ALIASES,
    norm_key, norm_phone, parse_excel_date, parse_quantity,
)
from app.utils.storage import get_storage

router = APIRouter(prefix="/api/leads", tags=["leads"])

TRACKER_COLS = ["enq", "date", "name", "company", "phone", "city", "cars", "inputs",
                "note", "remarks1", "nsm", "remarks2", "remarks22", "status", "quot",
                "value", "source", "last", "priority", "product", "owner", "tat",
                "tech", "secondary", "docs", "svc", "conv", "lost", "tatd", "email", "addl"]


def _serialize(l: Lead, db: Session) -> dict:
    return {
        "id": str(l.id), "enquiry_number": l.enquiry_number,
        "legacy_enquiry_no": l.legacy_enquiry_no,
        "enquiry_date": str(l.enquiry_date) if l.enquiry_date else None,
        "customer_name": l.customer_name, "contact_number": l.contact_number, "email": l.email,
        "company_name": l.company_name, "city": l.city, "quantity_raw": l.quantity_raw,
        "source_id": str(l.source_id) if l.source_id else None,
        "product_id": str(l.product_id) if l.product_id else None,
        "product_raw": l.product_raw or "",
        "product_name": db.get(Product, l.product_id).name if l.product_id and db.get(Product, l.product_id) else "",
        "source_name": db.get(LeadSource, l.source_id).name if l.source_id and db.get(LeadSource, l.source_id) else "",
        "status_id": str(l.status_id),
        "primary_employee_id": str(l.primary_employee_id) if l.primary_employee_id else None,
        "sla_state": l.sla_state,
        "sla_deadline": l.sla_deadline.isoformat() if l.sla_deadline else None,
        "first_contact_at": l.first_contact_at.isoformat() if l.first_contact_at else None,
        "first_contact_method": l.first_contact_method or "",
        "first_contact_result": l.first_contact_result or "",
        "first_contact_notes": l.first_contact_notes or "",
        "employee_remarks": l.employee_remarks or "",
        "customer_review": l.customer_review or "",
        "next_followup_at": l.next_followup_at.isoformat() if l.next_followup_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "pending_assignment": l.primary_employee_id is None,
        "work_history": [
            {"remarks": a.notes or "", "category": a.customer_review or "", "work_action": a.outcome or "", "at": a.activity_at.isoformat() if a.activity_at else None}
            for a in db.query(LeadActivity).filter_by(lead_id=l.id).order_by(LeadActivity.activity_at.asc()).all()
            if a.activity_type == "Work Progress"
        ],
    }


def _lookup(db, model, name: str):
    if not name:
        return None
    return db.query(model).filter(func.lower(model.name) == name.strip().lower()).first()


def _owned_lead(db: Session, lid: UUID, u: User) -> Lead:
    """404 if missing; EMPLOYEEs may only touch their own assigned leads."""
    lead = db.get(Lead, lid)
    if not lead:
        raise HTTPException(404, "Not found")
    if u.role and u.role.name == "EMPLOYEE" and lead.primary_employee_id != u.id:
        raise HTTPException(403, "Not assigned to you")
    return lead


def _parse_uuid(value: str, field: str) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, f"Invalid {field} filter")


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
def list_leads(db: Session = Depends(get_db), u: User = Depends(current_user),
               search: str = "", status: str = "", source: str = "", product: str = "",
               employee: str = "", sla: str = "", unassigned: str = "", customer_review: str = "",
               page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    q = db.query(Lead).filter(Lead.is_active.is_(True))
    if u.role and u.role.name == "EMPLOYEE":
        q = q.filter(Lead.primary_employee_id == u.id)
    if search:
        like = f"%{_escape_like(search)}%"
        q = q.filter(or_(Lead.customer_name.ilike(like, escape="\\"), Lead.company_name.ilike(like, escape="\\"),
                         Lead.contact_number.ilike(like, escape="\\"), Lead.enquiry_number.ilike(like, escape="\\")))
    if status:
        q = q.filter(Lead.status_id == _parse_uuid(status, "status"))
    if source:
        q = q.filter(Lead.source_id == _parse_uuid(source, "source"))
    if product:
        q = q.filter(Lead.product_id == _parse_uuid(product, "product"))
    if employee:
        q = q.filter(Lead.primary_employee_id == _parse_uuid(employee, "employee"))
    if sla:
        if sla not in ("PENDING", "OVERDUE", "COMPLETED"):
            raise HTTPException(400, "Invalid sla filter")
        q = q.filter(Lead.sla_state == sla)
    if unassigned in ("1", "true", "yes"):
        q = q.filter(Lead.primary_employee_id.is_(None))
    if customer_review:
        q = q.filter(Lead.customer_review == customer_review)
    total = q.count()
    rows = q.order_by(Lead.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [_serialize(r, db) for r in rows]}


@router.post("")
def create_lead(body: LeadCreate, db: Session = Depends(get_db), u: User = Depends(current_user)):
    raise HTTPException(
        403,
        "Leads can only be created by importing the Excel tracker. Use Import in the admin portal.",
    )


@router.get("/{lid}")
def get_lead(lid: UUID, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = db.get(Lead, lid)
    if not lead:
        raise HTTPException(404, "Not found")
    if u.role and u.role.name == "EMPLOYEE" and lead.primary_employee_id != u.id:
        raise HTTPException(403, "Not assigned")
    acts = db.query(LeadActivity).filter_by(lead_id=lid).order_by(LeadActivity.activity_at.desc()).all()
    hist = db.query(LeadStatusHistory).filter_by(lead_id=lid).order_by(LeadStatusHistory.changed_at.desc()).all()
    quotes = db.query(Quotation).filter_by(lead_id=lid).all()
    visits = db.query(SiteVisit).filter_by(lead_id=lid).all()
    docs = db.query(LeadDocument).filter_by(lead_id=lid).all()
    d = _serialize(lead, db)
    d["activities"] = [{"id": str(a.id), "type": a.activity_type, "notes": a.notes, "at": a.activity_at.isoformat() if a.activity_at else None} for a in acts]
    d["history"] = [{"id": str(h.id), "old": str(h.old_status_id) if h.old_status_id else None, "new": str(h.new_status_id), "reason": h.reason} for h in hist]
    d["quotations"] = [{"id": str(x.id), "number": x.quotation_number, "total": float(x.grand_total) if x.grand_total else None} for x in quotes]
    d["visits"] = [{"id": str(v.id), "status": v.visit_status, "notes": v.notes} for v in visits]
    d["documents"] = [{"id": str(x.id), "name": x.file_name} for x in docs]
    return d


@router.put("/{lid}")
def update_lead(lid: UUID, body: LeadUpdate, db: Session = Depends(get_db), u: User = Depends(current_user)):
    from app.services.normalize import is_valid_email, norm_phone
    lead = _owned_lead(db, lid, u)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(lead, k, v)
    if body.email is not None and body.email.strip() and not is_valid_email(body.email.strip()):
        raise HTTPException(400, "Enter a valid email address")
    if body.contact_number is not None:
        lead.contact_number_norm = norm_phone(body.contact_number)
    db.commit()
    return _serialize(lead, db)


@router.post("/{lid}/status")
def set_status(lid: UUID, body: StatusChange, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = _owned_lead(db, lid, u)
    remarks = (body.reason or "").strip()
    if not remarks:
        raise HTTPException(400, "Remarks are required after speaking to the customer")
    status = db.get(LeadStatus, body.new_status_id)
    if not status:
        raise HTTPException(400, "Invalid work progress status")
    customer_review = (body.customer_review or "").strip()
    if customer_review and customer_review not in {"A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (plan stage)"}:
        raise HTTPException(400, "Invalid customer review")
    if body.sla_state is not None and body.sla_state not in {"PENDING", "COMPLETED"}:
        raise HTTPException(400, "Invalid SLA state")
    # First talk after assignment also completes the 3-day contact SLA
    if not lead.first_contact_at and lead.primary_employee_id == u.id:
        record_first_contact(db, lead, u, body.method or "Call", status.name, remarks)
    change_status(db, lead, body.new_status_id, u, remarks)
    lead.employee_remarks = remarks
    lead.customer_review = customer_review
    if body.sla_state is not None:
        lead.sla_state = body.sla_state
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Work Progress",
        notes=remarks, outcome=status.name, customer_review=customer_review,
    ))
    db.commit()
    return {"ok": True, "sla_state": lead.sla_state, "status": status.name}


@router.post("/{lid}/assign")
def assign_lead(lid: UUID, body: AssignIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    from app.services.lead_service import open_workload
    lead = db.get(Lead, lid)
    emp = db.get(User, body.employee_id)
    if not lead or not emp:
        raise HTTPException(404, "Not found")
    if body.role == "PRIMARY" and open_workload(db, emp.id) >= max(1, int(settings.OPEN_LEAD_LIMIT)):
        raise HTTPException(400, "Employee already has an open customer. Finish first contact before assigning another.")
    assign(db, lead, emp, body.role, admin)
    db.commit()
    # Immediate assignment email with full customer details (fail-open).
    if body.role == "PRIMARY":
        try:
            from app.services import email_service
            fresh = db.get(Lead, lid)
            src = db.get(LeadSource, fresh.source_id) if fresh.source_id else None
            prod = db.get(Product, fresh.product_id) if fresh.product_id else None
            cur = db.query(LeadAssignment).filter(
                LeadAssignment.lead_id == fresh.id,
                LeadAssignment.is_current.is_(True),
            ).order_by(LeadAssignment.assigned_at.desc()).first()
            at = cur.assigned_at if cur else fresh.created_at
            item = {
                "enquiry_number": fresh.enquiry_number,
                "legacy_enq": fresh.legacy_enquiry_no,
                "enquiry_date": str(fresh.enquiry_date) if fresh.enquiry_date else "—",
                "assigned_date_str": at.strftime("%d-%b-%Y") if at else "—",
                "customer_name": fresh.customer_name or "",
                "contact_number": fresh.contact_number or "",
                "alternate_contact": fresh.alternate_contact or "",
                "email": fresh.email or "",
                "company_name": fresh.company_name or "",
                "city": fresh.city or "",
                "source": src.name if src else "—",
                "product": (fresh.product_raw or (prod.name if prod else "") or "—"),
                "quantity_raw": fresh.quantity_raw or "",
                "deadline_str": fresh.sla_deadline.strftime("%d-%b-%Y %H:%M") if fresh.sla_deadline else "—",
                "lead_url": f"{settings.FRONTEND_URL.rstrip('/')}/leads/{fresh.id}",
            }
            if email_service.send_assignment_email(emp.email, emp.name, [item]):
                fresh.assignment_email_sent_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            log.error("manual assignment email failed for %s: %s", lid, exc)
    return {"ok": True}


@router.post("/{lid}/contact")
def first_contact(lid: UUID, body: ContactIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = _owned_lead(db, lid, u)
    if not (body.notes or "").strip() and not (body.result or "").strip():
        raise HTTPException(400, "Please enter what you talked about with the customer")
    record_first_contact(db, lead, u, body.method, body.result, body.notes)
    db.commit()
    return {"sla_state": lead.sla_state, "ok": True}


@router.post("/{lid}/activities")
def add_activity(lid: UUID, body: ActivityIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = _owned_lead(db, lid, u)
    a = LeadActivity(lead_id=lid, employee_id=u.id, activity_type=body.activity_type,
                     notes=body.notes, outcome=body.outcome, next_followup_at=body.next_followup_at)
    db.add(a)
    if body.next_followup_at:
        lead.next_followup_at = body.next_followup_at
    db.commit()
    return {"id": str(a.id)}


@router.post("/{lid}/site-visits")
def add_visit(lid: UUID, body: VisitIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _owned_lead(db, lid, u)
    v = SiteVisit(lead_id=lid, employee_id=u.id, visit_date=body.visit_date, site_location=body.site_location,
                  visit_status=body.visit_status, customer_feedback=body.customer_feedback, notes=body.notes)
    db.add(v)
    db.commit()
    return {"id": str(v.id)}


@router.post("/{lid}/quotations")
def add_quote(lid: UUID, body: QuoteIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _owned_lead(db, lid, u)
    q = Quotation(lead_id=lid, **body.model_dump())
    db.add(q)
    db.commit()
    return {"id": str(q.id)}


@router.post("/{lid}/documents")
async def upload_doc(lid: UUID, file: UploadFile, doc_type: str = "Other",
                     db: Session = Depends(get_db), u: User = Depends(current_user)):
    _owned_lead(db, lid, u)
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, "File too large")
    try:
        path = get_storage().save(str(lid), file.filename, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    d = LeadDocument(lead_id=lid, file_name=file.filename, stored_path=path,
                     content_type=file.content_type or "", size_bytes=len(data),
                     document_type=doc_type, uploaded_by=u.id)
    db.add(d)
    db.commit()
    return {"id": str(d.id)}
