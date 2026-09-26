import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import admin_only, current_user
from app.db.session import get_db
from app.models import (
    Lead, LeadActivity, LeadAssignment, LeadDocument, LeadReassignmentRequest,
    LeadSource, LeadStatus, LeadStatusHistory, Notification, Product, Quotation, SiteVisit, User,
)
from app.schemas import (
    ActivityIn, AssignIn, ContactIn, LeadCreate, LeadUpdate, LeadValueCalcIn,
    QuoteFormIn, QuoteIn, ReassignDecisionIn, ReassignRequestIn, StatusChange, VisitIn,
)
from app.services import live
from app.services.lead_service import (
    assign, change_status, notify_admins, open_reassignment_request,
    record_first_contact, validate_assignee,
)
from app.services.normalize import parse_quantity
from app.services.pricing import apply_pricing_to_lead, calc_lead_value, round_money
from app.utils.storage import get_storage


def _money_str(v) -> str | None:
    if v is None:
        return None
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return None

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])

TRACKER_COLS = ["enq", "date", "name", "company", "phone", "city", "cars", "inputs",
                "note", "remarks1", "nsm", "remarks2", "remarks22", "status", "quot",
                "value", "source", "last", "priority", "product", "owner", "tat",
                "tech", "secondary", "docs", "svc", "conv", "lost", "tatd", "email", "addl"]


def _serialize(
    l: Lead,
    db: Session,
    *,
    product_name: str | None = None,
    source_name: str | None = None,
    work_history: list | None = None,
) -> dict:
    if product_name is None:
        product_name = db.get(Product, l.product_id).name if l.product_id and db.get(Product, l.product_id) else ""
    if source_name is None:
        source_name = db.get(LeadSource, l.source_id).name if l.source_id and db.get(LeadSource, l.source_id) else ""
    if work_history is None:
        work_history = [
            {
                "quotation_value": _money_str(a.quotation_value),
                "remarks": a.notes or "",
                "category": (
                    "C (Planning Stage)"
                    if (a.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
                    else (a.customer_review or "")
                ),
                "work_action": a.outcome or "",
                "at": a.activity_at.isoformat() if a.activity_at else None,
            }
            for a in db.query(LeadActivity).filter_by(lead_id=l.id).order_by(LeadActivity.activity_at.asc()).all()
            if a.activity_type == "Work Progress"
        ]
    return {
        "id": str(l.id), "enquiry_number": l.enquiry_number,
        "legacy_enquiry_no": l.legacy_enquiry_no,
        "enquiry_date": str(l.enquiry_date) if l.enquiry_date else None,
        "customer_name": l.customer_name, "contact_number": l.contact_number,
        "alternate_contact": l.alternate_contact or "", "email": l.email,
        "company_name": l.company_name, "city": l.city, "quantity_raw": l.quantity_raw,
        "quantity_num": float(l.quantity_num) if l.quantity_num is not None else None,
        "price_per_car": _money_str(l.price_per_car),
        "gst_percent": 18,
        "gst_amount": _money_str(l.gst_amount),
        "lead_value": _money_str(l.lead_value),
        "source_id": str(l.source_id) if l.source_id else None,
        "product_id": str(l.product_id) if l.product_id else None,
        "product_raw": l.product_raw or "",
        "product_name": product_name or "",
        "source_name": source_name or "",
        "status_id": str(l.status_id),
        "primary_employee_id": str(l.primary_employee_id) if l.primary_employee_id else None,
        "sla_state": l.sla_state,
        "sla_deadline": l.sla_deadline.isoformat() if l.sla_deadline else None,
        "first_contact_at": l.first_contact_at.isoformat() if l.first_contact_at else None,
        "first_contact_method": l.first_contact_method or "",
        "first_contact_result": l.first_contact_result or "",
        "first_contact_notes": l.first_contact_notes or "",
        "employee_remarks": l.employee_remarks or "",
        "customer_review": (
            "C (Planning Stage)"
            if (l.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
            else (l.customer_review or "")
        ),
        "quotation_value": _money_str(l.quotation_value),
        "next_followup_at": l.next_followup_at.isoformat() if l.next_followup_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "pending_assignment": l.primary_employee_id is None,
        "work_history": work_history,
        "reassignment_request": _serialize_reassignment(db, l.id),
    }


def _serialize_reassignment(db: Session, lead_id) -> dict | None:
    req = open_reassignment_request(db, lead_id)
    if not req:
        return None
    requester = db.get(User, req.requested_by)
    return {
        "id": str(req.id),
        "status": req.status,
        "reason": req.reason or "",
        "requested_by": str(req.requested_by),
        "requested_by_name": requester.name if requester else "—",
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "review_note": req.review_note or "",
    }


def _require_lead_write(u: User) -> None:
    """Managers are read-only per business rules; admins/employees may mutate."""
    role = getattr(getattr(u, "role", None), "name", None)
    if role == "MANAGER":
        raise HTTPException(403, "Managers have read-only access")


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
    if u.role and u.role.name == "EMPLOYEE" and lead.sla_state == "COMPLETED":
        status = db.get(LeadStatus, lead.status_id)
        if status and status.name == "Converted":
            raise HTTPException(403, "Converted leads cannot be edited or reopened.")
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
               sort: str = "", page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    q = db.query(Lead).filter(Lead.is_active.is_(True))
    if u.role and u.role.name == "EMPLOYEE":
        q = q.filter(Lead.primary_employee_id == u.id)
    if search:
        like = f"%{_escape_like(search)}%"
        q = q.filter(or_(Lead.customer_name.ilike(like, escape="\\"), Lead.company_name.ilike(like, escape="\\"),
                         Lead.contact_number.ilike(like, escape="\\"), Lead.enquiry_number.ilike(like, escape="\\"),
                         Lead.email.ilike(like, escape="\\")))
    if status:
        q = q.filter(Lead.status_id == _parse_uuid(status, "status"))
    if source:
        q = q.filter(Lead.source_id == _parse_uuid(source, "source"))
    if product:
        q = q.filter(Lead.product_id == _parse_uuid(product, "product"))
    if employee:
        q = q.filter(Lead.primary_employee_id == _parse_uuid(employee, "employee"))
    if sla == "NOT_INTERESTED":
        q = q.filter(Lead.status_id.in_(
            db.query(LeadStatus.id).filter(LeadStatus.name.in_(("Not Interested", "Not Interested/Spam")))
        ))
    elif sla:
        if sla not in ("PENDING", "OVERDUE", "COMPLETED"):
            raise HTTPException(400, "Invalid sla filter")
        q = q.filter(Lead.sla_state == sla)
    if unassigned in ("1", "true", "yes"):
        q = q.filter(Lead.primary_employee_id.is_(None))
    if customer_review:
        q = q.filter(Lead.customer_review == customer_review)
    total = q.count()
    sort_key = (sort or "").strip().lower()
    if sort_key in ("lead_value", "lead_value_asc"):
        q = q.order_by(Lead.lead_value.asc().nullslast(), Lead.updated_at.desc())
    elif sort_key in ("lead_value_desc", "-lead_value"):
        q = q.order_by(Lead.lead_value.desc().nullslast(), Lead.updated_at.desc())
    else:
        q = q.order_by(Lead.updated_at.desc())
    rows = q.offset((page - 1) * size).limit(size).all()
    # Batch lookup names + work history to avoid N+1 on list pages.
    prod_ids = {r.product_id for r in rows if r.product_id}
    src_ids = {r.source_id for r in rows if r.source_id}
    products = {p.id: p.name for p in db.query(Product).filter(Product.id.in_(prod_ids)).all()} if prod_ids else {}
    sources = {s.id: s.name for s in db.query(LeadSource).filter(LeadSource.id.in_(src_ids)).all()} if src_ids else {}
    lead_ids = [r.id for r in rows]
    hist_by_lead: dict = {lid: [] for lid in lead_ids}
    if lead_ids:
        acts = (
            db.query(LeadActivity)
            .filter(LeadActivity.lead_id.in_(lead_ids), LeadActivity.activity_type == "Work Progress")
            .order_by(LeadActivity.activity_at.asc())
            .all()
        )
        for a in acts:
            hist_by_lead.setdefault(a.lead_id, []).append({
                "quotation_value": _money_str(a.quotation_value),
                "remarks": a.notes or "",
                "category": (
                    "C (Planning Stage)"
                    if (a.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
                    else (a.customer_review or "")
                ),
                "work_action": a.outcome or "",
                "at": a.activity_at.isoformat() if a.activity_at else None,
            })
    quote_by_lead: dict = {}
    if lead_ids:
        for qrow in db.query(Quotation).filter(Quotation.lead_id.in_(lead_ids)).all():
            prev = quote_by_lead.get(qrow.lead_id)
            if not prev or (qrow.revision or "") >= (prev.revision or ""):
                quote_by_lead[qrow.lead_id] = qrow
    items = [
        {
            **_serialize(
                r, db,
                product_name=products.get(r.product_id, ""),
                source_name=sources.get(r.source_id, ""),
                work_history=hist_by_lead.get(r.id, []),
            ),
            "quotation_form": (
                {
                    "quotation_number": quote_by_lead[r.id].quotation_number,
                    "revision": quote_by_lead[r.id].revision,
                    "grand_total": _money_str(quote_by_lead[r.id].grand_total),
                }
                if r.id in quote_by_lead else None
            ),
        }
        for r in rows
    ]
    return {"total": total, "items": items}


@router.post("")
def create_lead(body: LeadCreate, db: Session = Depends(get_db), u: User = Depends(current_user)):
    raise HTTPException(
        403,
        "Leads can only be created by importing the Excel tracker. Use Import in the admin portal.",
    )


@router.get("/reassignment-requests")
def list_reassignment_requests(
    status: str | None = Query(default="PENDING"),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    q = db.query(LeadReassignmentRequest).order_by(LeadReassignmentRequest.created_at.desc())
    if status:
        q = q.filter(LeadReassignmentRequest.status == status.upper())
    rows = q.limit(100).all()
    out = []
    for req in rows:
        lead = db.get(Lead, req.lead_id)
        requester = db.get(User, req.requested_by)
        out.append({
            "id": str(req.id),
            "status": req.status,
            "reason": req.reason or "",
            "review_note": req.review_note or "",
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
            "requested_by": str(req.requested_by),
            "requested_by_name": requester.name if requester else "—",
            "lead_id": str(req.lead_id),
            "enquiry_number": lead.enquiry_number if lead else "—",
            "customer_name": lead.customer_name if lead else "—",
            "contact_number": lead.contact_number if lead else "",
            "current_employee_id": str(lead.primary_employee_id) if lead and lead.primary_employee_id else None,
        })
    return out


@router.post("/reassignment-requests/{rid}/accept")
def accept_reassignment(
    rid: UUID,
    body: ReassignDecisionIn | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    """Admin accepts — lead stays with current owner until admin manually assigns."""
    req = db.get(LeadReassignmentRequest, rid)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "PENDING":
        raise HTTPException(400, f"Request is already {req.status.lower()}")
    lead = db.get(Lead, req.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    now = datetime.now(timezone.utc)
    req.status = "ACCEPTED"
    req.reviewed_by = admin.id
    req.reviewed_at = now
    req.review_note = ((body.note if body else "") or "").strip()
    db.add(Notification(
        user_id=req.requested_by, lead_id=lead.id, kind="REASSIGN_ACCEPTED",
        title="Reassignment accepted",
        body=f"Admin accepted your request for {lead.enquiry_number}. They will assign another employee manually.",
    ))
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=admin.id, activity_type="Reassignment Decision",
        notes=req.review_note or "Accepted", outcome="ACCEPTED",
    ))
    db.commit()
    return {
        "ok": True,
        "status": "ACCEPTED",
        "lead_id": str(lead.id),
        "message": "Accepted. Manually assign this lead to another employee — ownership is unchanged until then.",
    }


@router.post("/reassignment-requests/{rid}/decline")
def decline_reassignment(
    rid: UUID,
    body: ReassignDecisionIn | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    """Admin declines — no change to lead ownership."""
    req = db.get(LeadReassignmentRequest, rid)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "PENDING":
        raise HTTPException(400, f"Request is already {req.status.lower()}")
    lead = db.get(Lead, req.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    now = datetime.now(timezone.utc)
    note = ((body.note if body else "") or "").strip()
    req.status = "DECLINED"
    req.reviewed_by = admin.id
    req.reviewed_at = now
    req.review_note = note
    db.add(Notification(
        user_id=req.requested_by, lead_id=lead.id, kind="REASSIGN_DECLINED",
        title="Reassignment declined",
        body=f"Admin declined your reassignment request for {lead.enquiry_number}."
             + (f" Note: {note}" if note else " Lead remains assigned to you."),
    ))
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=admin.id, activity_type="Reassignment Decision",
        notes=note or "Declined", outcome="DECLINED",
    ))
    db.commit()
    return {"ok": True, "status": "DECLINED", "lead_id": str(lead.id)}


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


@router.post("/calculate-value")
def calculate_lead_value(body: LeadValueCalcIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Preview Lead Value (backend-authoritative). Does not persist."""
    prod = None
    if body.product_id:
        prod = db.get(Product, body.product_id)
        if not prod or not prod.is_active:
            raise HTTPException(400, "Select a valid product from the product list")
    cars = body.number_of_cars
    if cars is None and body.quantity_raw is not None:
        cars = parse_quantity(body.quantity_raw)
    price = prod.price_per_car if prod else None
    result = calc_lead_value(cars, price, product_name=prod.name if prod else None)
    return {
        "product_id": str(prod.id) if prod else None,
        "product": prod.name if prod else None,
        **result,
    }


@router.put("/{lid}")
def update_lead(lid: UUID, body: LeadUpdate, db: Session = Depends(get_db), u: User = Depends(current_user)):
    from app.services.normalize import is_valid_email, norm_phone
    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    data = body.model_dump(exclude_unset=True)
    # Never trust client-sent pricing fields
    data.pop("lead_value", None)
    data.pop("price_per_car", None)
    data.pop("gst_amount", None)
    role = getattr(getattr(u, "role", None), "name", None)
    admin_fields = {
        "enquiry_number", "enquiry_date", "customer_name", "company_name",
        "contact_number", "city", "email", "source_id",
    }
    if role != "ADMIN" and any(key in data for key in admin_fields):
        raise HTTPException(403, "Only an admin can edit these lead details")
    if "enquiry_number" in data:
        number = str(data.pop("enquiry_number") or "").strip()
        if not number:
            raise HTTPException(400, "Enquiry number is required")
        taken = db.query(Lead).filter(Lead.enquiry_number == number, Lead.id != lead.id).first()
        if taken:
            raise HTTPException(409, "That enquiry number is already used")
        lead.enquiry_number = number
        suffix = number.upper().removeprefix("ENQ-")
        if number.upper().startswith("ENQ-") and suffix.isdigit():
            lead.legacy_enquiry_no = int(suffix)
    if "enquiry_date" in data:
        lead.enquiry_date = data.pop("enquiry_date")
    if "source_id" in data:
        sid = data.pop("source_id")
        if sid is None:
            lead.source_id = None
        else:
            src = db.get(LeadSource, sid)
            if not src:
                raise HTTPException(400, "Select a valid lead source")
            lead.source_id = src.id
    for key in ("customer_name", "company_name", "contact_number", "city", "email"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()

    pricing_changed = False
    if "product_id" in data:
        pid = data.pop("product_id")
        if pid is None:
            lead.product_id = None
            lead.product_raw = ""
            pricing_changed = True
        else:
            prod = db.get(Product, pid)
            if not prod or not prod.is_active:
                raise HTTPException(400, "Select a valid product from the product list")
            lead.product_id = prod.id
            lead.product_raw = prod.name
            pricing_changed = True

    if "quantity_raw" in data:
        raw = data.pop("quantity_raw") or ""
        lead.quantity_raw = str(raw).strip()
        cars = parse_quantity(lead.quantity_raw)
        if lead.quantity_raw and cars is None:
            raise HTTPException(400, "Number of cars must be a positive number")
        if cars is not None and cars <= 0:
            raise HTTPException(400, "Number of cars must be greater than zero")
        lead.quantity_num = cars
        pricing_changed = True

    for k, v in data.items():
        if v is not None:
            setattr(lead, k, v)
    if body.email is not None and body.email.strip() and not is_valid_email(body.email.strip()):
        raise HTTPException(400, "Enter a valid email address")
    if body.contact_number is not None:
        lead.contact_number_norm = norm_phone(lead.contact_number)

    if pricing_changed or lead.lead_value is None:
        prod = db.get(Product, lead.product_id) if lead.product_id else None
        apply_pricing_to_lead(lead, product=prod)

    db.commit()
    return _serialize(lead, db)


@router.post("/{lid}/status")
def set_status(lid: UUID, body: StatusChange, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    remarks = (body.reason or "").strip()
    if not remarks:
        raise HTTPException(400, "Remarks are required after speaking to the customer")
    status = db.get(LeadStatus, body.new_status_id)
    if not status:
        raise HTTPException(400, "Invalid work progress status")
    customer_review = (body.customer_review or "").strip()
    if customer_review in {"C (plan stage)", "Planning Stage"}:
        customer_review = "C (Planning Stage)"
    if customer_review and customer_review not in {"A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (Planning Stage)"}:
        raise HTTPException(400, "Invalid customer review")
    if body.sla_state is not None and body.sla_state not in {"PENDING", "COMPLETED"}:
        raise HTTPException(400, "Invalid overdue state")
    completion_only = (
        body.sla_state is not None
        and (body.sla_state == "COMPLETED" or lead.sla_state == "COMPLETED")
        and lead.status_id == body.new_status_id
        and (lead.employee_remarks or "").strip() == remarks
        and (lead.customer_review or "").strip() == customer_review
        and (body.quotation_value is None or body.quotation_value == lead.quotation_value)
    )
    if completion_only:
        lead.sla_state = body.sla_state
        db.commit()
        return {"ok": True, "sla_state": lead.sla_state, "status": status.name, "activity_recorded": False}
    # First talk after assignment also completes the 3-day contact SLA
    if not lead.first_contact_at and lead.primary_employee_id == u.id:
        record_first_contact(db, lead, u, body.method or "Call", status.name, remarks)
    change_status(db, lead, body.new_status_id, u, remarks)
    lead.employee_remarks = remarks
    lead.customer_review = customer_review
    if status.name == "Quotation sent" and body.quotation_value is not None:
        rounded = round_money(body.quotation_value)
        if rounded is None:
            raise HTTPException(400, "Quotation value must be a whole number (no decimals)")
        lead.quotation_value = rounded
    if body.sla_state is not None:
        lead.sla_state = body.sla_state
    q_for_activity = round_money(body.quotation_value) if status.name == "Quotation sent" and body.quotation_value is not None else None
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Work Progress",
        notes=remarks, outcome=status.name, customer_review=customer_review,
        quotation_value=q_for_activity,
    ))
    db.commit()
    return {"ok": True, "sla_state": lead.sla_state, "status": status.name, "activity_recorded": True}


@router.post("/{lid}/assign")
def assign_lead(lid: UUID, body: AssignIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    lead = db.get(Lead, lid)
    if not lead:
        raise HTTPException(404, "Not found")
    emp = db.get(User, body.employee_id)
    try:
        emp = validate_assignee(emp)
    except ValueError as exc:
        code = 404 if str(exc) == "Employee not found" else 400
        raise HTTPException(code, str(exc)) from exc

    # Changing an existing owner requires an accepted reassignment request,
    # unless admin is assigning manually from the leads list.
    if (
        not getattr(body, "manual", False)
        and body.role == "PRIMARY"
        and lead.primary_employee_id is not None
        and lead.primary_employee_id != emp.id
    ):
        open_req = open_reassignment_request(db, lead.id)
        if not open_req or open_req.status != "ACCEPTED":
            raise HTTPException(
                400,
                "Accept the employee's reassignment request before manually assigning this lead to another employee",
            )

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
    live.bump()
    return {"ok": True}


@router.post("/{lid}/reassign-request")
def request_reassignment(
    lid: UUID,
    body: ReassignRequestIn,
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
):
    """Employee asks admin to reassign a lead they cannot follow."""
    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    role = getattr(getattr(u, "role", None), "name", None)
    if role != "EMPLOYEE":
        raise HTTPException(403, "Only the assigned employee can request reassignment")
    if lead.primary_employee_id != u.id:
        raise HTTPException(403, "You can only request reassignment for your own leads")
    reason = (body.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(400, "Please explain why this lead should be reassigned")
    existing = open_reassignment_request(db, lead.id)
    if existing:
        raise HTTPException(
            400,
            f"A reassignment request is already {existing.status.lower()} for this lead",
        )
    req = LeadReassignmentRequest(
        lead_id=lead.id,
        requested_by=u.id,
        reason=reason,
        status="PENDING",
    )
    db.add(req)
    db.flush()
    notify_admins(
        db,
        lead_id=lead.id,
        kind="REASSIGN_REQUEST",
        title="Reassignment requested",
        body=f"{u.name} asked to reassign {lead.enquiry_number} ({lead.customer_name or 'customer'}): {reason}",
    )
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Reassignment Request",
        notes=reason, outcome="PENDING",
    ))
    db.commit()
    return {"ok": True, "request": _serialize_reassignment(db, lead.id)}


@router.post("/{lid}/contact")
def first_contact(lid: UUID, body: ContactIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    if not (body.notes or "").strip() and not (body.result or "").strip():
        raise HTTPException(400, "Please enter what you talked about with the customer")
    record_first_contact(db, lead, u, body.method, body.result, body.notes)
    db.commit()
    return {"sla_state": lead.sla_state, "ok": True}


@router.post("/{lid}/activities")
def add_activity(lid: UUID, body: ActivityIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_lead_write(u)
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
    _require_lead_write(u)
    _owned_lead(db, lid, u)
    v = SiteVisit(lead_id=lid, employee_id=u.id, visit_date=body.visit_date, site_location=body.site_location,
                  visit_status=body.visit_status, customer_feedback=body.customer_feedback, notes=body.notes)
    db.add(v)
    db.commit()
    return {"id": str(v.id)}


@router.post("/{lid}/quotations")
def add_quote(lid: UUID, body: QuoteIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_lead_write(u)
    _owned_lead(db, lid, u)
    q = Quotation(lead_id=lid, **body.model_dump())
    db.add(q)
    db.commit()
    return {"id": str(q.id)}


def _quote_notes_payload(quote: Quotation | None) -> dict:
    import json
    if not quote or not (quote.notes or "").strip().startswith("{"):
        return {}
    try:
        data = json.loads(quote.notes)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _next_revision(current: str | None) -> str:
    raw = (current or "R0").strip().upper()
    if raw.startswith("R") and raw[1:].isdigit():
        return f"R{int(raw[1:]) + 1}"
    return "R1"


def _quotation_form_dict(db: Session, lead: Lead, quote: Quotation | None = None) -> dict:
    from app.services.quotation_form import (
        DEFAULT_PAYMENT_TERMS, DEFAULT_POST_WARRANTY,
        normalize_delivery_period,
        build_quotation_number, calc_form_totals, clean_extra_lines,
    )

    product = db.get(Product, lead.product_id) if lead.product_id else None
    product_name = (product.name if product else "") or (lead.product_raw or "Parking System")
    notes = _quote_notes_payload(quote)
    units = float(quote.units) if quote and quote.units is not None else (
        float(lead.quantity_num) if lead.quantity_num is not None else 0
    )
    unit_cost = float(notes["unit_cost"]) if notes.get("unit_cost") is not None else (
        float(lead.price_per_car) if lead.price_per_car is not None else 0
    )
    to_name = (notes.get("to_name") or "").strip() or (lead.company_name or lead.customer_name or "").strip() or "—"
    address_parts = [p for p in [(lead.location or "").strip(), (lead.city or "").strip()] if p]
    to_address = (notes.get("to_address") or "").strip() or ("\n".join(address_parts) if address_parts else "—")
    cars_label = int(units) if units and float(units) == int(float(units)) else (units or "")
    subject = (notes.get("subject") or "").strip() or f"Offer for {product_name}- {cars_label} Cars"
    product_description = (notes.get("product_description") or "").strip() or (
        f"Design, Manufacture, Supply and Erection of {product_name}"
    )
    payment_terms = (notes.get("payment_terms") or "").strip() or DEFAULT_PAYMENT_TERMS
    delivery_period = normalize_delivery_period(notes.get("delivery_period"))
    post_warranty = (notes.get("post_warranty") or "").strip() or DEFAULT_POST_WARRANTY
    extra_lines = clean_extra_lines(notes.get("extra_lines") or [])
    revision = (quote.revision if quote else "R0") or "R0"
    if quote and quote.quotation_number:
        quotation_number = quote.quotation_number
    else:
        quotation_number = build_quotation_number(db, lead, revision)
    qdate = quote.quotation_date if quote and quote.quotation_date else date.today()
    totals = calc_form_totals(unit_cost, units, extra_lines)
    return {
        "id": str(quote.id) if quote else None,
        "quotation_number": quotation_number,
        "revision": revision,
        "quotation_date": qdate.isoformat() if hasattr(qdate, "isoformat") else str(qdate),
        "to_name": to_name,
        "to_address": to_address,
        "subject": subject,
        "product_description": product_description,
        "payment_terms": payment_terms,
        "delivery_period": delivery_period,
        "post_warranty": post_warranty,
        "unit_cost": int(round(unit_cost)) if unit_cost else 0,
        "units": units,
        "extra_lines": extra_lines,
        "amount_excl": totals["amount_excl"],
        "gst": totals["gst"],
        "grand_total": totals["grand_total"],
        "status": quote.status if quote else "Draft",
        "customer_name": lead.customer_name or "",
        "company_name": lead.company_name or "",
        "city": lead.city or "",
        "enquiry_number": lead.enquiry_number or "",
        "product_name": product_name,
    }


@router.get("/{lid}/quotation-form")
def get_quotation_form(lid: UUID, db: Session = Depends(get_db), u: User = Depends(current_user)):
    lead = _owned_lead(db, lid, u)
    quote = (
        db.query(Quotation)
        .filter_by(lead_id=lid)
        .order_by(Quotation.quotation_date.desc().nullslast(), Quotation.revision.desc())
        .first()
    )
    # If assigned but REF missing (legacy), create it now so employee always sees REF.
    if quote is None and lead.primary_employee_id is not None:
        from app.services.quotation_form import ensure_quotation_on_assign
        quote = ensure_quotation_on_assign(db, lead)
        db.commit()
        db.refresh(quote)
    return _quotation_form_dict(db, lead, quote)


@router.put("/{lid}/quotation-form")
def save_quotation_form(lid: UUID, body: QuoteFormIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    import json
    from datetime import date as date_cls

    from app.services.quotation_form import calc_form_totals, build_quotation_number, clean_extra_lines

    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    quote = (
        db.query(Quotation)
        .filter_by(lead_id=lid)
        .order_by(Quotation.quotation_date.desc().nullslast(), Quotation.revision.desc())
        .first()
    )
    extra_lines = clean_extra_lines(body.extra_lines)
    totals = calc_form_totals(body.unit_cost, body.units, extra_lines)
    qdate = body.quotation_date or date_cls.today()
    snap = {
        "unit_cost": int(round(float(body.unit_cost))),
        "to_name": (body.to_name or "").strip(),
        "to_address": (body.to_address or "").strip(),
        "subject": (body.subject or "").strip(),
        "product_description": (body.product_description or "").strip(),
        "payment_terms": (body.payment_terms or "").strip(),
        "delivery_period": (body.delivery_period or "").strip(),
        "post_warranty": (body.post_warranty or "").strip(),
        "units": float(body.units),
        "extra_lines": extra_lines,
        "quotation_date": qdate.isoformat() if hasattr(qdate, "isoformat") else str(qdate),
    }
    # First save+download stays R0. The next edit that is saved becomes R1, then R2…
    # Download itself does not change the revision. Saving the same text again does not bump.
    if quote:
        prev_number = quote.quotation_number
        old = _quote_notes_payload(quote)
        already_issued = bool(old.get("issued")) or bool((old.get("to_name") or "").strip()) or (
            quote.amount_excl is not None and float(quote.amount_excl or 0) > 0
        )
        old_snap = {k: old.get(k) for k in snap}
        if old.get("units") is None and quote.units is not None:
            old_snap["units"] = float(quote.units)
        if not old_snap.get("quotation_date") and quote.quotation_date is not None:
            old_snap["quotation_date"] = quote.quotation_date.isoformat()
        if not old_snap.get("extra_lines"):
            old_snap["extra_lines"] = []
        changed = any(old_snap.get(k) != snap[k] for k in snap)
        if already_issued and changed:
            quote.revision = _next_revision(quote.revision)
        else:
            quote.revision = quote.revision or "R0"
        new_number = build_quotation_number(
            db, lead, quote.revision, existing_number=prev_number, on_date=qdate,
        )
        taken = db.query(Quotation).filter(
            Quotation.quotation_number == new_number,
            Quotation.id != quote.id,
        ).first()
        if taken:
            raise HTTPException(409, "That quotation reference is already used. Choose another date.")
        quote.quotation_number = new_number
        quote.quotation_date = qdate
        quote.units = body.units
        quote.amount_excl = totals["amount_excl"]
        quote.gst = totals["gst"]
        quote.grand_total = totals["grand_total"]
        quote.notes = json.dumps({**snap, "issued": True})
        quote.status = "Draft"
    else:
        revision = "R0"
        notes = json.dumps({**snap, "issued": True})
        quote = Quotation(
            lead_id=lid,
            quotation_number=build_quotation_number(db, lead, revision, on_date=qdate),
            quotation_date=qdate,
            revision=revision,
            units=body.units,
            amount_excl=totals["amount_excl"],
            gst=totals["gst"],
            grand_total=totals["grand_total"],
            status="Draft",
            notes=notes,
        )
        db.add(quote)
    # Keep lead quotation_value in sync (excl GST, whole rupees)
    lead.quotation_value = round_money(totals["amount_excl"])
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Quotation Form",
        notes=f"Saved quotation {quote.quotation_number} (units={body.units}, unit_cost={int(round(float(body.unit_cost)))})",
        outcome=quote.revision,
        quotation_value=round_money(totals["amount_excl"]),
    ))
    db.commit()
    db.refresh(quote)
    return _quotation_form_dict(db, lead, quote)


@router.get("/{lid}/quotation-form/pdf")
def download_quotation_form_pdf(lid: UUID, db: Session = Depends(get_db), u: User = Depends(current_user)):
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from app.services.quotation_form import build_quotation_form_pdf

    lead = _owned_lead(db, lid, u)
    quote = (
        db.query(Quotation)
        .filter_by(lead_id=lid)
        .order_by(Quotation.quotation_date.desc().nullslast(), Quotation.revision.desc())
        .first()
    )
    if not quote:
        raise HTTPException(400, "Save the quotation form before downloading PDF")
    payload = _quotation_form_dict(db, lead, quote)
    content = build_quotation_form_pdf(payload)
    filename = f"{payload['quotation_number']}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{lid}/documents")
async def upload_doc(lid: UUID, file: UploadFile, doc_type: str = "Other",
                     db: Session = Depends(get_db), u: User = Depends(current_user)):
    _require_lead_write(u)
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
