import logging
from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

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
    QuoteFormIn, QuoteIn, ReassignDecisionIn, ReassignRequestIn, ReminderDoneIn, StatusChange, VisitIn,
)
from app.services import live
from app.services.lead_service import (
    FOLLOWUP_SLA_HOURS, SLA_STOP_STATUSES, assign, auto_assign, change_status,
    employee_by_name, next_enquiry_number, notify_admins,
    open_reassignment_request, record_first_contact, refresh_followup_sla,
    remember_assignment, set_followup_deadline, stop_followup_sla, validate_assignee,
)
from app.services.normalize import (
    allows_odd_cars, canonical_product_name, is_valid_email, is_valid_phone,
    norm_phone, parse_quantity, normalize_car_count,
)
from app.services.pricing import apply_pricing_to_lead, calc_lead_value, round_money
from app.services.ttl_cache import TTLCache
from app.utils.storage import get_storage

_EMPLOYEE_SUMMARY_CACHE = TTLCache(ttl_seconds=60, maxsize=1024)
_LEAD_COUNT_CACHE = TTLCache(ttl_seconds=60, maxsize=2048)


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


_UNSET = object()


def _serialize(
    l: Lead,
    db: Session,
    *,
    product_name: str | None = None,
    source_name: str | None = None,
    work_history: list | None = None,
    reassignment_request=_UNSET,
) -> dict:
    if product_name is None:
        product_name = db.get(Product, l.product_id).name if l.product_id and db.get(Product, l.product_id) else ""
    if source_name is None:
        source_name = db.get(LeadSource, l.source_id).name if l.source_id and db.get(LeadSource, l.source_id) else ""
    if work_history is None:
        work_history = [
            {
                "id": str(a.id),
                "quotation_value": _money_str(a.quotation_value),
                "remarks": a.notes or "",
                "category": (
                    "B (6-9 months)"
                    if (a.customer_review or "").strip() == "B (1 year)"
                    else (
                        "C (Planning Stage)"
                        if (a.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
                        else (a.customer_review or "")
                    )
                ),
                "work_action": a.outcome or "",
                "reminder_date": a.reminder_date.isoformat() if a.reminder_date else None,
                "reminder_done": bool(getattr(a, "reminder_done", False)),
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
            "B (6-9 months)"
            if (l.customer_review or "").strip() == "B (1 year)"
            else (
                "C (Planning Stage)"
                if (l.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
                else (l.customer_review or "")
            )
        ),
        "is_starred": bool(getattr(l, "is_starred", False)),
        "quotation_value": _money_str(l.quotation_value),
        "reminder_date": l.reminder_date.isoformat() if l.reminder_date else None,
        "reminder_done": bool(getattr(l, "reminder_done", False)),
        "next_followup_at": l.next_followup_at.isoformat() if l.next_followup_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "pending_assignment": l.primary_employee_id is None,
        "work_history": work_history,
        "reassignment_request": (
            _serialize_reassignment(db, l.id)
            if reassignment_request is _UNSET
            else reassignment_request
        ),
    }


def _reassignment_dict(req, requester: User | None) -> dict:
    return {
        "id": str(req.id),
        "status": req.status,
        "reason": req.reason or "",
        "requested_by": str(req.requested_by),
        "requested_by_name": requester.name if requester else "—",
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "review_note": req.review_note or "",
    }


def _serialize_reassignment(db: Session, lead_id) -> dict | None:
    req = open_reassignment_request(db, lead_id)
    if not req:
        return None
    return _reassignment_dict(req, db.get(User, req.requested_by))


def _serialize_reassignments(db: Session, lead_ids: list) -> dict:
    """One request + one requester query for a whole page instead of two per lead."""
    if not lead_ids:
        return {}
    reqs = (
        db.query(LeadReassignmentRequest)
        .filter(
            LeadReassignmentRequest.lead_id.in_(lead_ids),
            LeadReassignmentRequest.status.in_(("PENDING", "ACCEPTED")),
        )
        .order_by(LeadReassignmentRequest.created_at.desc())
        .all()
    )
    latest: dict = {}
    for req in reqs:
        latest.setdefault(req.lead_id, req)
    user_ids = {req.requested_by for req in latest.values() if req.requested_by}
    requesters = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )
    return {
        lead_id: _reassignment_dict(req, requesters.get(req.requested_by))
        for lead_id, req in latest.items()
    }


def _require_lead_write(u: User) -> None:
    """Only admin and employee may mutate leads."""
    role = getattr(getattr(u, "role", None), "name", None)
    if role not in ("ADMIN", "EMPLOYEE"):
        raise HTTPException(403, "Not allowed")


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


def _clear_reminder_dues(db: Session, lead: Lead) -> None:
    """Bell hygiene: once the remainder closes (reminder_done=True),
    mark its unread hourly REMINDER_DUE rows read so the badge clears."""
    try:
        if not bool(getattr(lead, "reminder_done", False)):
            return
        db.query(Notification).filter(
            Notification.lead_id == lead.id,
            Notification.kind == "REMINDER_DUE",
            Notification.is_read.is_(False),
        ).update({"is_read": True}, synchronize_session=False)
    except Exception:
        pass


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
               city: str = "", starred: str = "", sort: str = "", light: str = "", page: int = 1, size: int = 20):
    light_mode = light in ("1", "true", "yes")
    page = max(1, page)
    size = min(max(1, size), 100)
    q = db.query(Lead).filter(Lead.is_active.is_(True))
    if u.role and u.role.name == "EMPLOYEE":
        q = q.filter(Lead.primary_employee_id == u.id)
    if search:
        like = f"%{_escape_like(search)}%"
        q = q.filter(or_(Lead.customer_name.ilike(like, escape="\\"), Lead.company_name.ilike(like, escape="\\"),
                         Lead.contact_number.ilike(like, escape="\\"), Lead.enquiry_number.ilike(like, escape="\\"),
                         Lead.email.ilike(like, escape="\\"), Lead.city.ilike(like, escape="\\")))
    if city:
        q = q.filter(Lead.city.ilike(f"%{_escape_like(city.strip())}%", escape="\\"))
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
    if starred in ("1", "true", "yes"):
        q = q.filter(Lead.is_starred.is_(True))
    count_key = (u.id, search, status, source, product, employee, sla, unassigned, customer_review, city)
    total = _LEAD_COUNT_CACHE.get(count_key) if light_mode else None
    if total is None:
        total = q.count()
        if light_mode:
            _LEAD_COUNT_CACHE.set(count_key, total)
    sort_key = (sort or "").strip().lower()
    if sort_key in ("lead_value", "lead_value_asc"):
        q = q.order_by(Lead.lead_value.asc().nullslast(), Lead.updated_at.desc(), Lead.id.desc())
    elif sort_key in ("lead_value_desc", "-lead_value"):
        q = q.order_by(Lead.lead_value.desc().nullslast(), Lead.updated_at.desc(), Lead.id.desc())
    else:
        q = q.order_by(Lead.updated_at.desc(), Lead.id.desc())
    rows = q.offset((page - 1) * size).limit(size).all()
    # Batch lookup names + work history to avoid N+1 on list pages.
    prod_ids = {r.product_id for r in rows if r.product_id}
    src_ids = {r.source_id for r in rows if r.source_id}
    products = {p.id: p.name for p in db.query(Product).filter(Product.id.in_(prod_ids)).all()} if prod_ids else {}
    sources = {s.id: s.name for s in db.query(LeadSource).filter(LeadSource.id.in_(src_ids)).all()} if src_ids else {}
    lead_ids = [r.id for r in rows]
    hist_by_lead: dict = {}
    quote_value_hist_by_lead: dict = {}
    quote_by_lead: dict = {}
    reassignment_by_lead: dict = {}
    if lead_ids and not light_mode:
        hist_by_lead = {lid: [] for lid in lead_ids}
        quote_value_hist_by_lead = {lid: [] for lid in lead_ids}
        acts = (
            db.query(LeadActivity)
            .filter(LeadActivity.lead_id.in_(lead_ids), LeadActivity.activity_type == "Work Progress")
            .order_by(LeadActivity.activity_at.asc())
            .all()
        )
        for a in acts:
            hist_by_lead.setdefault(a.lead_id, []).append({
                "id": str(a.id),
                "quotation_value": _money_str(a.quotation_value),
                "remarks": a.notes or "",
                "category": (
                    "B (6-9 months)"
                    if (a.customer_review or "").strip() == "B (1 year)"
                    else (
                        "C (Planning Stage)"
                        if (a.customer_review or "").strip() in {"C (plan stage)", "Planning Stage"}
                        else (a.customer_review or "")
                    )
                ),
                "work_action": a.outcome or "",
                "reminder_date": a.reminder_date.isoformat() if a.reminder_date else None,
                "reminder_done": bool(getattr(a, "reminder_done", False)),
                "at": a.activity_at.isoformat() if a.activity_at else None,
            })
        # One value per revision (R0, R1, R2…) from quotation form saves.
        quote_acts = (
            db.query(LeadActivity)
            .filter(LeadActivity.lead_id.in_(lead_ids), LeadActivity.activity_type == "Quotation Form")
            .order_by(LeadActivity.activity_at.asc())
            .all()
        )
        rev_order: dict = {lid: [] for lid in lead_ids}
        rev_latest: dict = {lid: {} for lid in lead_ids}
        for a in quote_acts:
            rev = (a.outcome or "R0").strip().upper() or "R0"
            if not rev.startswith("R"):
                rev = "R0"
            entry = {
                "revision": rev,
                "quotation_value": _money_str(a.quotation_value),
                "at": a.activity_at.isoformat() if a.activity_at else None,
            }
            bucket = rev_latest.setdefault(a.lead_id, {})
            order = rev_order.setdefault(a.lead_id, [])
            if rev not in bucket:
                order.append(rev)
            bucket[rev] = entry
        for lid in lead_ids:
            quote_value_hist_by_lead[lid] = [rev_latest[lid][r] for r in rev_order[lid] if r in rev_latest[lid]]
        for qrow in db.query(Quotation).filter(Quotation.lead_id.in_(lead_ids)).all():
            prev = quote_by_lead.get(qrow.lead_id)
            if not prev or (qrow.revision or "") >= (prev.revision or ""):
                quote_by_lead[qrow.lead_id] = qrow
        reassignment_by_lead = _serialize_reassignments(db, lead_ids)
    items = []
    for r in rows:
        if light_mode:
            items.append(_serialize(
                r, db,
                product_name=products.get(r.product_id, ""),
                source_name=sources.get(r.source_id, ""),
                work_history=[],
                reassignment_request=None,
            ))
            continue
        qform = None
        qrow = quote_by_lead.get(r.id)
        # Show REF in the table only after form Save (issued) — open/preview does not count.
        if qrow is not None and _quotation_is_issued(qrow):
            qform = {
                "quotation_number": qrow.quotation_number,
                "revision": qrow.revision,
                "amount_excl": _money_str(qrow.amount_excl),
                "grand_total": _money_str(qrow.grand_total),
            }
        qhist = list(quote_value_hist_by_lead.get(r.id) or [])
        # Fallback: current form/lead value when no Quotation Form activity yet
        if not qhist:
            cur_val = _money_str(qrow.grand_total) if qform else _money_str(r.quotation_value)
            cur_rev = (qrow.revision if qform else None) or "R0"
            if cur_val not in (None, ""):
                qhist = [{"revision": str(cur_rev).upper(), "quotation_value": cur_val, "at": None}]
        items.append({
            **_serialize(
                r, db,
                product_name=products.get(r.product_id, ""),
                source_name=sources.get(r.source_id, ""),
                work_history=hist_by_lead.get(r.id, []),
                reassignment_request=reassignment_by_lead.get(r.id),
            ),
            "quotation_form": qform,
            "quotation_value_history": qhist,
        })
    return {"total": total, "items": items}


@router.get("/employee-summary")
def employee_summary(db: Session = Depends(get_db), u: User = Depends(current_user),
                     employee: str = ""):
    """Counter tiles for Employee Leads as SQL aggregates, cached for 60s."""
    if u.role and u.role.name == "EMPLOYEE":
        target_id = u.id
    elif employee:
        target_id = _parse_uuid(employee, "employee")
    else:
        target_id = None

    cache_key = str(target_id) if target_id else "all"
    cached = _EMPLOYEE_SUMMARY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    filters = [Lead.is_active.is_(True)]
    if target_id:
        filters.append(Lead.primary_employee_id == target_id)

    review_expr = func.trim(func.coalesce(Lead.customer_review, ""))
    b_review = Lead.customer_review.in_(("B (6-9 months)", "B (1 year)"))
    c_review = Lead.customer_review.in_(("C (Planning Stage)", "C (plan stage)", "Planning Stage"))
    counts = (
        db.query(
            func.count(Lead.id),
            func.count(Lead.id).filter(Lead.first_contact_at.is_(None)),
            func.count(Lead.id).filter(Lead.sla_state == "OVERDUE"),
            func.count(Lead.id).filter(Lead.first_contact_at.isnot(None)),
            func.count(Lead.id).filter(review_expr == ""),
            func.count(Lead.id).filter(Lead.customer_review == "A+ (Immediate)"),
            func.count(Lead.id).filter(Lead.customer_review == "A (3-6 months)"),
            func.count(Lead.id).filter(b_review),
            func.count(Lead.id).filter(c_review),
        )
        .filter(*filters)
        .one()
    )
    total, needs_contact, overdue, responded, unreviewed, cat_aplus, cat_a, cat_b, cat_c = counts

    action_rows = (
        db.query(LeadStatus.name, func.count(Lead.id))
        .join(Lead, Lead.status_id == LeadStatus.id)
        .filter(*filters)
        .group_by(LeadStatus.name)
        .all()
    )
    work_actions: dict[str, int] = {}
    for status_name, count in action_rows:
        action = (status_name or "").strip()
        if action == "New Lead" and target_id:
            action = "Assigned"
        action = action or "—"
        work_actions[action] = work_actions.get(action, 0) + count

    result = {
        "total": total,
        "needs_contact": needs_contact,
        "overdue": overdue,
        "responded": responded,
        "unreviewed": unreviewed,
        "categories": {
            "A+ (Immediate)": cat_aplus,
            "A (3-6 months)": cat_a,
            "B (6-9 months)": cat_b,
            "C (Planning Stage)": cat_c,
        },
        "work_actions": work_actions,
    }
    _EMPLOYEE_SUMMARY_CACHE.set(cache_key, result)
    return result


def _validate_form_cars(raw, product_name: str) -> tuple[int | None, str | None]:
    """Create Lead cars rule.

    ≥ 2 any whole number: Puzzle, Pit Puzzle, Shuttle, Car Elevator, ASRS.
    ≥ 2 even only: Two Post, Four Post, Pit Stack, Tower.
    Blank is allowed (optional).
    """
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None, None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None, "You have entered wrong No. of Cars — must be a number"
    if value != int(value) or value < 2:
        return None, "You have entered wrong No. of Cars — whole number starting at 2"
    cars = int(value)
    product = canonical_product_name(product_name) or (product_name or "").strip()
    if not product or allows_odd_cars(product):
        return cars, None
    if cars % 2 != 0:
        return None, (
            "You have entered wrong No. of Cars — even numbers only for "
            "Tower / Two Post / Four Post / Pit Stack Parking"
        )
    return cars, None


@router.post("")
def create_lead(body: LeadCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """Manual Create Lead — phone or email alone is enough; other fields optional when blank."""
    from app.api.importer import (
        _default_status, _norm_product, _norm_source, _send_assignment_batches,
    )

    phone = (body.contact_number or "").strip()
    email = (body.email or "").strip()
    name = (body.customer_name or "").strip()
    product_name = (body.product_name or "").strip()
    source_name = (body.source_name or "").strip()
    cars_raw = body.number_of_cars if body.number_of_cars is not None else body.quantity_raw

    errors: list[str] = []
    if phone and not is_valid_phone(phone):
        errors.append("You have entered wrong Contact No. — 10-digit Indian mobile starting with 6–9")
    if email and not is_valid_email(email):
        errors.append("You have entered wrong Email")
    if not phone and not email:
        errors.append("Enter a phone number or an email (either one is enough)")
    if body.enquiry_date and body.enquiry_date > datetime.now(ZoneInfo("Asia/Kolkata")).date():
        errors.append("You have entered wrong Date Received — future dates are not allowed")

    cars, car_err = _validate_form_cars(cars_raw, product_name)
    if car_err:
        errors.append(car_err)

    prod = None
    if body.product_id or product_name:
        prod = db.get(Product, body.product_id) if body.product_id else _norm_product(db, product_name)
        if not prod:
            errors.append("You have entered wrong Product / Type")

    src = None
    if body.source_id or source_name:
        src = db.get(LeadSource, body.source_id) if body.source_id else _norm_source(db, source_name)
        if not src:
            errors.append("You have entered wrong Lead Source")

    chosen = None
    if body.primary_employee_id:
        chosen = db.get(User, body.primary_employee_id)
        try:
            chosen = validate_assignee(chosen)
        except ValueError:
            errors.append("You have entered wrong Select employee")
            chosen = None
    elif (body.employee_name or "").strip():
        chosen = employee_by_name(db, body.employee_name)
        if not chosen:
            errors.append("You have entered wrong Select employee")

    phone_n = norm_phone(phone) if phone and is_valid_phone(phone) else ""
    if phone_n and db.query(Lead).filter_by(contact_number_norm=phone_n).first():
        errors.append("You have entered wrong Contact No. — duplicate phone already exists")

    if errors:
        raise HTTPException(400, " · ".join(errors))

    st = _default_status(db)
    # Enquiry numbers are always system-assigned (1…n). Client / Excel values are ignored.
    enquiry_number = next_enquiry_number(db)
    lead = Lead(
        enquiry_number=enquiry_number,
        legacy_enquiry_no=None,
        enquiry_date=body.enquiry_date or date.today(),
        customer_name=name,
        company_name=(body.company_name or "").strip(),
        contact_number=phone,
        contact_number_norm=phone_n,
        alternate_contact=(body.alternate_contact or "").strip(),
        email=email,
        city=(body.city or body.location or "").strip(),
        product_raw=prod.name if prod else product_name,
        requirement=(body.requirement or "").strip(),
        quantity_raw=str(cars) if cars is not None else "",
        quantity_num=cars,
        priority=(body.priority or "").strip(),
        source_id=src.id if src else None,
        product_id=prod.id if prod else None,
        status_id=st.id,
        sla_state="PENDING",
        created_by=admin.id,
    )
    apply_pricing_to_lead(lead, product=prod)
    db.add(lead)
    db.flush()
    db.add(LeadStatusHistory(
        lead_id=lead.id, old_status_id=None, new_status_id=st.id,
        changed_by=admin.id, reason="manual create lead",
    ))

    assigned = None
    if chosen:
        assign(db, lead, chosen)
        remember_assignment(db, chosen)
        assigned = chosen
    else:
        assigned = auto_assign(db, lead, admin, ignore_limit=True)

    db.commit()
    live.bump()
    if assigned:
        try:
            _send_assignment_batches(db, {assigned.id: [lead.id]})
        except Exception as exc:
            log.error("create-lead assignment mail failed: %s", exc)

    db.refresh(lead)
    return _serialize(lead, db)


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
    acts = (
        db.query(LeadActivity)
        .filter_by(lead_id=lid)
        .order_by(LeadActivity.activity_at.asc(), LeadActivity.created_at.asc())
        .all()
    )
    hist = (
        db.query(LeadStatusHistory)
        .filter_by(lead_id=lid)
        .order_by(LeadStatusHistory.changed_at.asc(), LeadStatusHistory.id.asc())
        .all()
    )
    quotes = db.query(Quotation).filter_by(lead_id=lid).all()
    visits = db.query(SiteVisit).filter_by(lead_id=lid).all()
    docs = db.query(LeadDocument).filter_by(lead_id=lid).all()
    d = _serialize(lead, db)
    d["activities"] = [{"id": str(a.id), "type": a.activity_type, "notes": a.notes, "reminder_date": a.reminder_date.isoformat() if getattr(a, "reminder_date", None) else None, "reminder_done": bool(getattr(a, "reminder_done", False)), "at": a.activity_at.isoformat() if a.activity_at else None} for a in acts]
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
        "enquiry_date", "customer_name", "company_name",
        "contact_number", "city", "email", "source_id",
    }
    if "enquiry_number" in data:
        data.pop("enquiry_number", None)
        raise HTTPException(403, "Enquiry number is auto-assigned and cannot be changed")
    if role != "ADMIN" and any(key in data for key in admin_fields):
        raise HTTPException(403, "Only an admin can edit these lead details")
    if "enquiry_date" in data:
        new_enquiry_date = data.pop("enquiry_date")
        if new_enquiry_date and new_enquiry_date > datetime.now(ZoneInfo("Asia/Kolkata")).date():
            raise HTTPException(400, "You have entered wrong Date Received — future dates are not allowed")
        lead.enquiry_date = new_enquiry_date
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
    if "reminder_date" in data:
        rd = data.pop("reminder_date")
        if rd is not None and rd < date.today():
            raise HTTPException(400, "Reminder date cannot be in the past")
        if rd != lead.reminder_date:
            lead.reminder_done = False
        lead.reminder_date = rd
    if "reminder_done" in data:
        lead.reminder_done = bool(data.pop("reminder_done"))
        # One tick declares the remainder done: mirror onto same-date entries.
        if getattr(lead, "reminder_date", None) is not None:
            db.query(LeadActivity).filter(
                LeadActivity.lead_id == lead.id,
                LeadActivity.reminder_date == lead.reminder_date,
            ).update({"reminder_done": lead.reminder_done}, synchronize_session=False)
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
        product_name = lead.product_raw or ""
        if lead.product_id:
            current_product = db.get(Product, lead.product_id)
            if current_product:
                product_name = current_product.name
        count, car_error = normalize_car_count(raw, product_name)
        if car_error:
            raise HTTPException(400, car_error)
        lead.quantity_raw = str(count)
        lead.quantity_num = count
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

    _clear_reminder_dues(db, lead)
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
    if customer_review in {"B (1 year)"}:
        customer_review = "B (6-9 months)"
    if customer_review in {"C (plan stage)", "Planning Stage"}:
        customer_review = "C (Planning Stage)"
    if customer_review and customer_review not in {"A+ (Immediate)", "A (3-6 months)", "B (6-9 months)", "C (Planning Stage)"}:
        raise HTTPException(400, "Invalid customer review")
    if body.reminder_date is not None and body.reminder_date < date.today():
        raise HTTPException(400, "Reminder date cannot be in the past")
    if body.sla_state is not None and body.sla_state not in {"PENDING", "COMPLETED"}:
        raise HTTPException(400, "Invalid overdue state")
    completion_only = (
        body.sla_state is not None
        and (body.sla_state == "COMPLETED" or lead.sla_state == "COMPLETED")
        and lead.status_id == body.new_status_id
        and (lead.employee_remarks or "").strip() == remarks
        and (lead.customer_review or "").strip() == customer_review
        and (body.quotation_value is None or body.quotation_value == lead.quotation_value)
        and (body.reminder_date is None or lead.reminder_date is None or lead.reminder_date == body.reminder_date)
    )
    if completion_only:
        # Blank reminder means "leave unchanged" — only an explicitly picked date overwrites.
        if body.reminder_date is not None:
            if body.reminder_date != lead.reminder_date:
                lead.reminder_done = False
            lead.reminder_date = body.reminder_date
        if status.name in SLA_STOP_STATUSES or body.sla_state == "COMPLETED":
            stop_followup_sla(lead)
        elif body.reminder_date is not None:
            # Explicit new reminder on Done/Reopen path also moves this lead's overdue date.
            set_followup_deadline(db, lead, body.reminder_date)
        else:
            refresh_followup_sla(db, lead, hours=FOLLOWUP_SLA_HOURS)
        db.commit()
        return {"ok": True, "sla_state": lead.sla_state, "status": status.name, "activity_recorded": False,
                "reminder_date": str(lead.reminder_date) if lead.reminder_date else None,
                "reminder_done": bool(getattr(lead, "reminder_done", False))}
    # First talk after assignment records contact and starts a fresh follow-up window
    if not lead.first_contact_at and lead.primary_employee_id == u.id:
        record_first_contact(db, lead, u, body.method or "Call", status.name, remarks)
    change_status(db, lead, body.new_status_id, u, remarks)
    lead.employee_remarks = remarks
    lead.customer_review = customer_review
    # Auto-strike: saving a follow-up (category + progress + remarks) completes the
    # previous remainder. Old pending entries are struck so they vanish from the
    # login-pulse "Reminders due" bucket (which filters reminder_done=False).
    _prior_pending: list = []
    try:
        _fetched = db.query(LeadActivity).filter(
            LeadActivity.lead_id == lead.id,
            LeadActivity.activity_type == "Work Progress",
            LeadActivity.reminder_date.isnot(None),
            LeadActivity.reminder_done.is_(False),
        ).all()
        _prior_pending = list(_fetched) if _fetched is not None else []
    except TypeError:
        # Unit tests use a bare Mock for db whose .query().filter().all()
        # returns a non-iterable Mock — treat as "no prior pending".
        _prior_pending = []
    # Blank reminder means "no new remainder" — only an explicitly picked date overwrites.
    if body.reminder_date is not None:
        for _old in _prior_pending:
            if _old.reminder_date != body.reminder_date:
                _old.reminder_done = True
        if body.reminder_date != lead.reminder_date:
            lead.reminder_done = False
        lead.reminder_date = body.reminder_date
    else:
        for _old in _prior_pending:
            _old.reminder_done = True
        # Keep the old date for struck display, but mark done so the popup clears.
        if lead.reminder_date is not None:
            lead.reminder_done = True
    if status.name == "Quotation sent" and body.quotation_value is not None:
        rounded = round_money(body.quotation_value)
        if rounded is None:
            raise HTTPException(400, "Quotation value must be a whole number (no decimals)")
        lead.quotation_value = rounded
    # Only explicit Done (sla_state=COMPLETED) stops overdue. Save restarts the
    # per-lead window: picked reminder date (23:59 IST) or 24h/72h fallback.
    if body.sla_state == "COMPLETED":
        stop_followup_sla(lead)
    else:
        set_followup_deadline(db, lead, body.reminder_date)
    q_for_activity = round_money(body.quotation_value) if status.name == "Quotation sent" and body.quotation_value is not None else None
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Work Progress",
        notes=remarks, outcome=status.name, customer_review=customer_review,
        quotation_value=q_for_activity, reminder_date=body.reminder_date,
        reminder_done=False,
    ))
    _clear_reminder_dues(db, lead)
    db.commit()
    return {"ok": True, "sla_state": lead.sla_state, "status": status.name, "activity_recorded": True,
            "reminder_date": str(lead.reminder_date) if lead.reminder_date else None,
            "reminder_done": bool(getattr(lead, "reminder_done", False))}


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
                "lead_id": str(fresh.id),
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


@router.post("/{lid}/activities/{aid}/reminder-done")
def set_activity_reminder_done(lid: UUID, aid: UUID, body: ReminderDoneIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Tick/untick a single work-history entry's reminder date."""
    _require_lead_write(u)
    lead = _owned_lead(db, lid, u)
    a = db.get(LeadActivity, aid)
    if not a or a.lead_id != lead.id:
        raise HTTPException(404, "Activity not found")
    if u.role and u.role.name == "EMPLOYEE" and lead.sla_state == "COMPLETED":
        status = db.get(LeadStatus, lead.status_id)
        if status and status.name in ("Converted", "Not Interested", "Not Interested/Spam"):
            raise HTTPException(403, "This lead cannot be edited or reopened")
    a.reminder_done = bool(body.done)
    # One tick declares the remainder done: mirror onto the lead when this
    # entry carries the lead's current remainder date (clears popup/reports).
    act_date = getattr(a, "reminder_date", None)
    lead_date = getattr(lead, "reminder_date", None)
    if act_date is not None and lead_date is not None and act_date == lead_date:
        lead.reminder_done = a.reminder_done
    _clear_reminder_dues(db, lead)
    db.commit()
    return {"ok": True, "reminder_done": a.reminder_done,
            "lead_reminder_done": bool(getattr(lead, "reminder_done", False))}


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


def _quotation_is_issued(quote: Quotation | None) -> bool:
    """True only after form Save — opening alone does not reserve the Q count."""
    if quote is None:
        return False
    notes = _quote_notes_payload(quote)
    if notes.get("issued"):
        return True
    if quote.amount_excl is not None:
        try:
            return float(quote.amount_excl) > 0
        except (TypeError, ValueError):
            return False
    return False


def _next_revision(current: str | None) -> str:
    raw = (current or "R0").strip().upper()
    if raw.startswith("R") and raw[1:].isdigit():
        return f"R{int(raw[1:]) + 1}"
    return "R1"


def _quotation_form_dict(db: Session, lead: Lead, quote: Quotation | None = None) -> dict:
    from app.services.quotation_form import (
        DEFAULT_PAYMENT_TERMS, DEFAULT_POST_WARRANTY, DEFAULT_INTRODUCTION,
        normalize_delivery_period,
        build_quotation_ref, calc_form_totals, clean_extra_lines, enquiry_ddmm,
        next_quote_seq,
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
    # Current lead values, unfrozen by any saved quotation. The form uses these
    # only when the user explicitly clicks "Use current lead details".
    lead_units = float(lead.quantity_num) if lead.quantity_num is not None else 0
    lead_unit_cost = float(lead.price_per_car) if lead.price_per_car is not None else 0
    lead_to_name = (lead.company_name or lead.customer_name or "").strip()
    lead_to_address = "\n".join(address_parts)
    lead_cars_label = (
        int(lead_units) if lead_units and float(lead_units) == int(float(lead_units)) else (lead_units or "")
    )
    lead_subject = f"Offer for {product_name}- {lead_cars_label} Cars"
    lead_product_description = f"Design, Manufacture, Supply and Erection of {product_name}"
    payment_terms = (notes.get("payment_terms") or "").strip() or DEFAULT_PAYMENT_TERMS
    delivery_period = normalize_delivery_period(notes.get("delivery_period"))
    post_warranty = (notes.get("post_warranty") or "").strip() or DEFAULT_POST_WARRANTY
    introduction = notes["introduction"] if "introduction" in notes else DEFAULT_INTRODUCTION
    extra_lines = clean_extra_lines(notes.get("extra_lines") or [])
    table_copies = max(1, min(int(notes.get("table_copies") or 1), 10))
    revision = (quote.revision if quote and _quotation_is_issued(quote) else "R0") or "R0"
    issued = _quotation_is_issued(quote)
    qdate = quote.quotation_date if quote and quote.quotation_date and issued else date.today()
    if issued and quote and quote.quotation_number:
        quotation_number = quote.quotation_number
    else:
        # Preview next count only — not reserved until form Save.
        quotation_number = build_quotation_ref(enquiry_ddmm(lead, qdate), next_quote_seq(db), revision)
    totals = calc_form_totals(unit_cost, units, extra_lines)
    totals = {key: value * table_copies for key, value in totals.items()}
    return {
        "id": str(quote.id) if quote and issued else None,
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
        "introduction": introduction,
        "unit_cost": int(round(unit_cost)) if unit_cost else 0,
        "units": units,
        "extra_lines": extra_lines,
        "table_copies": table_copies,
        "amount_excl": totals["amount_excl"] if issued else 0,
        "gst": totals["gst"] if issued else 0,
        "grand_total": totals["grand_total"] if issued else 0,
        "status": quote.status if quote and issued else "Draft",
        "customer_name": lead.customer_name or "",
        "company_name": lead.company_name or "",
        "city": lead.city or "",
        "enquiry_number": lead.enquiry_number or "",
        "product_name": product_name,
        "issued": issued,
        "preview": not issued,
        # Live lead snapshot for the explicit "Use current lead details" action.
        "lead_product_name": product_name,
        "lead_units": lead_units,
        "lead_unit_cost": int(round(lead_unit_cost)) if lead_unit_cost else 0,
        "lead_to_name": lead_to_name,
        "lead_to_address": lead_to_address,
        "lead_city": lead.city or "",
        "lead_subject": lead_subject,
        "lead_product_description": lead_product_description,
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
    # Open only previews the next Q count — Save is what reserves it.
    return _quotation_form_dict(db, lead, quote if _quotation_is_issued(quote) else None)


@router.put("/{lid}/quotation-form")
def save_quotation_form(lid: UUID, body: QuoteFormIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    import json
    from datetime import date as date_cls

    from app.services.quotation_form import calc_form_totals, build_quotation_number, clean_extra_lines, DEFAULT_INTRODUCTION

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
    table_copies = max(1, min(int(body.table_copies or 1), 10))
    totals = {key: value * table_copies for key, value in totals.items()}
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
        "introduction": body.introduction if body.introduction is not None else "",
        "units": float(body.units),
        "extra_lines": extra_lines,
        "table_copies": table_copies,
        "quotation_date": qdate.isoformat() if hasattr(qdate, "isoformat") else str(qdate),
    }
    # Q count is reserved on Save only. First save = R0; later changed saves bump Rn.
    if quote:
        prev_number = quote.quotation_number
        old = _quote_notes_payload(quote)
        already_issued = _quotation_is_issued(quote)
        old_snap = {k: old.get(k) for k in snap}
        if old.get("units") is None and quote.units is not None:
            old_snap["units"] = float(quote.units)
        if not old_snap.get("quotation_date") and quote.quotation_date is not None:
            old_snap["quotation_date"] = quote.quotation_date.isoformat()
        if not old_snap.get("extra_lines"):
            old_snap["extra_lines"] = []
        if "introduction" not in old and (snap.get("introduction") or "").strip() == DEFAULT_INTRODUCTION.strip():
            old_snap["introduction"] = snap["introduction"]
        changed = any(old_snap.get(k) != snap[k] for k in snap)
        if already_issued and changed:
            quote.revision = _next_revision(quote.revision)
        else:
            quote.revision = (quote.revision or "R0") if already_issued else "R0"
        if already_issued:
            new_number = build_quotation_number(
                db, lead, quote.revision, existing_number=prev_number, on_date=qdate,
            )
        else:
            # First real save — take next free Q count (open/preview never reserved it).
            new_number = build_quotation_number(db, lead, quote.revision, on_date=qdate)
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
    # Keep lead quotation_value in sync (grand total incl. GST, whole rupees)
    lead.quotation_value = round_money(totals["grand_total"])
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=u.id, activity_type="Quotation Form",
        notes=f"Saved quotation {quote.quotation_number} (units={body.units}, unit_cost={int(round(float(body.unit_cost)))})",
        outcome=quote.revision,
        quotation_value=round_money(totals["grand_total"]),
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
    if not quote or not _quotation_is_issued(quote):
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
