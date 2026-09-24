"""Round-robin with OPEN_LEAD_LIMIT open leads per employee; extras stay unassigned (pending)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import (
    AssignmentState, EnquirySequence, Lead, LeadActivity, LeadAssignment,
    LeadReassignmentRequest, LeadSource, LeadStatus, LeadStatusHistory, Notification, Role, User,
)

DIRECT_CALL_SOURCE = "Direct Call"


def is_direct_call_name(name: str | None) -> bool:
    return (name or "").strip().lower() == DIRECT_CALL_SOURCE.lower()


def source_name_for_lead(db: Session, lead: Lead) -> str:
    if not getattr(lead, "source_id", None):
        return ""
    src = db.get(LeadSource, lead.source_id)
    return src.name if src else ""


def sla_hours_for_lead(db: Session, lead: Lead) -> int:
    """Direct Call must be updated within 24 hours. Every other source stays at 72 hours."""
    return 24 if is_direct_call_name(source_name_for_lead(db, lead)) else 72


def _ensure_quote_ref(db: Session, lead: Lead) -> None:
    """Allocate EEPLCP…QnR0 REF when lead gets a primary assignee."""
    try:
        from app.services.quotation_form import ensure_quotation_on_assign
        ensure_quotation_on_assign(db, lead)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "quotation REF on assign failed for lead %s", getattr(lead, "id", None),
        )


def format_enquiry_number(number: int) -> str:
    """Sheet/Excel enquiry 1 becomes ENQ-000001. Wider numbers keep every digit."""
    return f"ENQ-{int(number):06d}"


def next_enquiry_number(db: Session) -> str:
    seq = db.query(EnquirySequence).with_for_update().first()
    if not seq:
        seq = EnquirySequence(last_number=0)
        db.add(seq)
        db.flush()
    seq.last_number += 1
    db.flush()
    return f"ENQ-{seq.last_number:06d}"


def eligible_employees(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name == "EMPLOYEE")
        .options(joinedload(User.role))
        .order_by(User.name)
        .all()
    )


def _open_workload_map(db: Session) -> dict:
    """One GROUP BY query: open work per employee (assigned, needs first contact)."""
    rows = (
        db.query(Lead.primary_employee_id, func.count(Lead.id))
        .filter(
            Lead.is_active.is_(True),
            Lead.first_contact_at.is_(None),
            Lead.primary_employee_id.isnot(None),
        )
        .group_by(Lead.primary_employee_id)
        .all()
    )
    return {uid: c for uid, c in rows}


def open_workload(db: Session, user_id) -> int:
    """Open work = assigned active leads that still need first contact."""
    return (
        db.query(Lead)
        .filter(
            Lead.primary_employee_id == user_id,
            Lead.is_active.is_(True),
            Lead.first_contact_at.is_(None),
        )
        .count()
    )


def free_employees(db: Session) -> list[User]:
    limit = max(1, int(settings.OPEN_LEAD_LIMIT))
    loads = _open_workload_map(db)
    return [u for u in eligible_employees(db) if loads.get(u.id, 0) < limit]


def auto_assign(db: Session, lead: Lead, by: User | None = None) -> User | None:
    """Round-robin among employees under OPEN_LEAD_LIMIT; otherwise leave pending."""
    if lead.primary_employee_id:
        return None
    free = free_employees(db)
    if not free:
        return None  # all at capacity (or none exist); stays pending
    all_emps = eligible_employees(db)
    st = db.query(AssignmentState).with_for_update().first()
    if not st:
        st = AssignmentState()
        db.add(st)
        db.flush()
    all_ids = [u.id for u in all_emps]
    free_ids = {u.id for u in free}
    try:
        start = all_ids.index(st.last_employee_id) + 1 if st.last_employee_id in all_ids else 0
    except ValueError:
        start = 0
    chosen = None
    for i in range(len(all_ids)):
        cand_id = all_ids[(start + i) % len(all_ids)]
        if cand_id in free_ids:
            chosen = next(u for u in free if u.id == cand_id)
            break
    if not chosen:
        return None
    st.last_employee_id = chosen.id
    assign(db, lead, chosen, role="PRIMARY", by=by)
    return chosen


def validate_assignee(emp: User | None) -> User:
    """PRIMARY/TECHNICAL/SECONDARY assignees must be active EMPLOYEE accounts."""
    if not emp:
        raise ValueError("Employee not found")
    if not emp.is_active:
        raise ValueError("Cannot assign leads to an inactive employee")
    if not emp.role or emp.role.name != "EMPLOYEE":
        raise ValueError("Leads can only be assigned to employees")
    return emp


def assign_pending_leads(db: Session, by: User | None = None) -> int:
    """After an employee frees up, assign oldest pending leads while capacity remains."""
    assigned = 0
    while True:
        if not free_employees(db):
            break
        pending = (
            db.query(Lead)
            .filter(
                Lead.is_active.is_(True),
                Lead.primary_employee_id.is_(None),
            )
            .order_by(Lead.created_at.asc())
            .first()
        )
        if not pending:
            break
        if auto_assign(db, pending, by):
            assigned += 1
        else:
            break
    return assigned


def notify_admins(db: Session, *, lead_id, kind: str, title: str, body: str) -> None:
    admins = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name == "ADMIN")
        .all()
    )
    for admin in admins:
        db.add(Notification(user_id=admin.id, lead_id=lead_id, kind=kind, title=title, body=body))


def open_reassignment_request(db: Session, lead_id) -> LeadReassignmentRequest | None:
    """Latest PENDING or ACCEPTED request for a lead (if any)."""
    return (
        db.query(LeadReassignmentRequest)
        .filter(
            LeadReassignmentRequest.lead_id == lead_id,
            LeadReassignmentRequest.status.in_(("PENDING", "ACCEPTED")),
        )
        .order_by(LeadReassignmentRequest.created_at.desc())
        .first()
    )


def fulfill_accepted_reassignment(db: Session, lead: Lead, by: User | None = None) -> None:
    """Mark ACCEPTED reassignment request as FULFILLED after admin manually assigns."""
    req = (
        db.query(LeadReassignmentRequest)
        .filter(
            LeadReassignmentRequest.lead_id == lead.id,
            LeadReassignmentRequest.status == "ACCEPTED",
        )
        .order_by(LeadReassignmentRequest.created_at.desc())
        .first()
    )
    if not req:
        return
    now = datetime.now(timezone.utc)
    req.status = "FULFILLED"
    req.reviewed_at = req.reviewed_at or now
    if by and not req.reviewed_by:
        req.reviewed_by = by.id
    if req.requested_by:
        db.add(Notification(
            user_id=req.requested_by, lead_id=lead.id, kind="REASSIGN_FULFILLED",
            title="Lead reassigned",
            body=f"{lead.enquiry_number} was reassigned by admin after your request.",
        ))


def assign(db: Session, lead: Lead, emp: User, role: str = "PRIMARY", by: User | None = None):
    import logging
    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    hours = sla_hours_for_lead(db, lead) if role == "PRIMARY" else 72
    direct_call = hours == 24
    deadline = now + timedelta(hours=hours)
    db.query(LeadAssignment).filter(
        LeadAssignment.lead_id == lead.id, LeadAssignment.role == role,
        LeadAssignment.is_current.is_(True)).update({"is_current": False})
    db.add(LeadAssignment(
        lead_id=lead.id, employee_id=emp.id, role=role,
        assigned_by=by.id if by else None, assigned_at=now, sla_deadline=deadline, is_current=True,
    ))
    if role == "PRIMARY":
        prior_owner = lead.primary_employee_id
        lead.primary_employee_id = emp.id
        lead.sla_deadline = deadline
        lead.sla_state = "PENDING"
        # New assignment window: the overdue digest may fire again for the new due date.
        lead.overdue_digest_at = None
        # Reset first-contact SLA only when reassigning — never null out NOT NULL
        # string columns on a brand-new lead (that breaks Sheets/Excel intake).
        if prior_owner is not None or lead.first_contact_at is not None:
            lead.first_contact_at = None
            lead.first_contact_method = ""
            lead.first_contact_result = ""
            lead.first_contact_by = None
            lead.first_contact_notes = ""
            lead.assignment_email_sent_at = None
        # New Lead -> Assigned on (auto or manual) primary assignment.
        try:
            current = db.get(LeadStatus, lead.status_id) if lead.status_id else None
            if current is not None and current.name == "New Lead":
                assigned_st = db.query(LeadStatus).filter_by(name="Assigned").first()
                if assigned_st is not None and assigned_st.id != lead.status_id:
                    old = lead.status_id
                    lead.status_id = assigned_st.id
                    db.add(LeadStatusHistory(
                        lead_id=lead.id, old_status_id=old, new_status_id=assigned_st.id,
                        changed_by=by.id if by else None, reason="assigned to employee",
                    ))
        except Exception:
            log.exception("assign status flip failed for lead %s", lead.id)
        # Close approved reassignment workflow after manual assign.
        if prior_owner is not None and prior_owner != emp.id:
            fulfill_accepted_reassignment(db, lead, by)
        # Every assigned lead gets a quotation REF (EEPLCP…QnR0) for the form.
        _ensure_quote_ref(db, lead)
    elif role == "TECHNICAL":
        lead.technical_employee_id = emp.id
    elif role == "SECONDARY":
        lead.secondary_support_employee_id = emp.id
    if direct_call:
        note_title = "URGENT Direct Call assigned"
        note_body = (
            f"{lead.enquiry_number} is a Direct Call. Update the process within 24 hours "
            f"(by {deadline:%d-%b-%Y %H:%M})."
        )
    else:
        note_title = "New lead assigned"
        note_body = (
            f"{lead.enquiry_number} assigned. Contact the customer within 3 days "
            f"(by {deadline:%d-%b-%Y %H:%M})."
        )
    db.add(Notification(
        user_id=emp.id, lead_id=lead.id, kind="ASSIGNMENT",
        title=note_title,
        body=note_body,
    ))
    db.flush()


def change_status(db: Session, lead: Lead, new_status_id, by: User | None, reason: str = ""):
    old = lead.status_id
    if old == new_status_id:
        return
    lead.status_id = new_status_id
    db.add(LeadStatusHistory(
        lead_id=lead.id, old_status_id=old, new_status_id=new_status_id,
        changed_by=by.id if by else None, reason=reason,
    ))
    db.flush()


def record_first_contact(db: Session, lead: Lead, by: User, method: str, result: str, notes: str = ""):
    now = datetime.now(timezone.utc)
    lead.first_contact_at = now
    lead.first_contact_method = method
    lead.first_contact_result = result
    lead.first_contact_by = by.id
    lead.first_contact_notes = notes
    lead.sla_state = "COMPLETED" if (not lead.sla_deadline or now <= lead.sla_deadline) else "OVERDUE"
    db.add(LeadActivity(
        lead_id=lead.id, employee_id=by.id, activity_type="First Contact",
        activity_at=now, notes=notes or result, outcome=result,
    ))
    db.flush()
    # Employee is free for next pending lead
    assign_pending_leads(db, by)
