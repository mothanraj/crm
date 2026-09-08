from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import admin_only, current_user
from app.db.session import get_db
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
        "id": str(l.id), "enquiry_number": l.enquiry_number, "enquiry_date": str(l.enquiry_date) if l.enquiry_date else None,
        "customer_name": l.customer_name, "contact_number": l.contact_number, "email": l.email,
        "company_name": l.company_name, "city": l.city, "quantity_raw": l.quantity_raw,
        "source_id": str(l.source_id) if l.source_id else None,
        "product_id": str(l.product_id) if l.product_id else None,
        "status_id": str(l.status_id), "primary_employee_id": str(l.primary_employee_id) if l.primary_employee_id else None,
        "sla_state": l.sla_state, "sla_deadline": l.sla_deadline.isoformat() if l.sla_deadline else None,
        "next_followup_at": l.next_followup_at.isoformat() if l.next_followup_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }


def _lookup(db, model, name: str):
    if not name:
        return None
    return db.query(model).filter(func.lower(model.name) == name.strip().lower()).first()


@router.get("")
def list_leads(db: Session = Depends(get_db), u: User = Depends(current_user),
               search: str = "", status: str = "", source: str = "", product: str = "",
               employee: str = "", sla: str = "", page: int = 1, size: int = 20):
    q = db.query(Lead).filter(Lead.is_active.is_(True))
    if u.role and u.role.name == "EMPLOYEE":
        q = q.filter(Lead.primary_employee_id == u.id)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Lead.customer_name.ilike(like), Lead.company_name.ilike(like),
                         Lead.contact_number.ilike(like), Lead.enquiry_number.ilike(like)))
    if status:
        q = q.filter(Lead.status_id == status)
    if source:
        q = q.filter(Lead.source_id == source)
    if product:
        q = q.filter(Lead.product_id == product)
    if employee:
        q = q.filter(Lead.primary_employee_id == employee)
    if sla:
        q = q.filter(Lead.sla_state == sla)
    total = q.count()
    rows = q.order_by(Lead.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [_serialize(r, db) for r in rows]}


@router.post("")
def create_lead(body: LeadCreate, db: Session = Depends(get_db), u: User = Depends(current_user)):
    src = db.get(LeadSource, body.source_id) if body.source_id else (_lookup(db, LeadSource, body.source_name) if body.source_name else None)
    prod = None
    if body.product_id:
        prod = db.get(Product, body.product_id)
    elif body.product_name:
        from app.models import ProductAlias
        prod = _lookup(db, Product, body.product_name)
        if not prod:
            al = db.query(ProductAlias).filter(func.lower(ProductAlias.alias) == norm_key(body.product_name)).first()
            prod = db.get(Product, al.product_id) if al else None
    st = _lookup(db, LeadStatus, STATUS_ALIASES.get(norm_key(body.status_name), body.status_name)) or _lookup(db, LeadStatus, "New Lead")
    lead = Lead(enquiry_number=next_enquiry_number(db), enquiry_date=body.enquiry_date,
                customer_name=body.customer_name, contact_number=body.contact_number,
                contact_number_norm=norm_phone(body.contact_number), alternate_contact=body.alternate_contact,
                email=body.email, company_name=body.company_name, location=body.location, city=body.city,
                source_id=src.id if src else None, product_id=prod.id if prod else None,
                requirement=body.requirement, quantity_raw=body.quantity_raw,
                quantity_num=parse_quantity(body.quantity_raw), priority=body.priority,
                status_id=st.id, created_by=u.id)
    db.add(lead)
    db.flush()
    db.add(LeadStatusHistory(lead_id=lead.id, old_status_id=None, new_status_id=st.id, changed_by=u.id, reason="created"))
    if body.primary_employee_id:
        emp = db.get(User, body.primary_employee_id)
        if emp:
            assign(db, lead, emp, "PRIMARY", u)
    else:
        auto_assign(db, lead, u)
    db.commit()
    db.refresh(lead)
    return _serialize(lead, db)


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
    lead = db.get(Lead, lid)
    if not lead:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(lead, k, v)
    db.commit()
    return _serialize(lead, db)


@router.post("/{lid}/status")
def set_status(lid: UUID, body: StatusChange, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = db.get(Lead, lid)
    change_status(db, lead, body.new_status_id, u, body.reason)
    db.commit()
    return {"ok": True}


@router.post("/{lid}/assign")
def assign_lead(lid: UUID, body: AssignIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    lead = db.get(Lead, lid)
    emp = db.get(User, body.employee_id)
    if not lead or not emp:
        raise HTTPException(404, "Not found")
    assign(db, lead, emp, body.role, admin)
    db.commit()
    return {"ok": True}


@router.post("/{lid}/contact")
def first_contact(lid: UUID, body: ContactIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = db.get(Lead, lid)
    record_first_contact(db, lead, u, body.method, body.result, body.notes)
    db.commit()
    return {"sla_state": lead.sla_state}


@router.post("/{lid}/activities")
def add_activity(lid: UUID, body: ActivityIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    a = LeadActivity(lead_id=lid, employee_id=u.id, activity_type=body.activity_type,
                     notes=body.notes, outcome=body.outcome, next_followup_at=body.next_followup_at)
    db.add(a)
    if body.next_followup_at:
        db.get(Lead, lid).next_followup_at = body.next_followup_at
    db.commit()
    return {"id": str(a.id)}


@router.post("/{lid}/site-visits")
def add_visit(lid: UUID, body: VisitIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    v = SiteVisit(lead_id=lid, employee_id=u.id, visit_date=body.visit_date, site_location=body.site_location,
                  visit_status=body.visit_status, customer_feedback=body.customer_feedback, notes=body.notes)
    db.add(v)
    db.commit()
    return {"id": str(v.id)}


@router.post("/{lid}/quotations")
def add_quote(lid: UUID, body: QuoteIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = Quotation(lead_id=lid, **body.model_dump())
    db.add(q)
    db.commit()
    return {"id": str(q.id)}


@router.post("/{lid}/documents")
async def upload_doc(lid: UUID, file: UploadFile, doc_type: str = "Other",
                     db: Session = Depends(get_db), u: User = Depends(current_user)):
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, "File too large")
    path = get_storage().save(str(lid), file.filename, data)
    d = LeadDocument(lead_id=lid, file_name=file.filename, stored_path=path,
                     content_type=file.content_type or "", size_bytes=len(data),
                     document_type=doc_type, uploaded_by=u.id)
    db.add(d)
    db.commit()
    return {"id": str(d.id)}
