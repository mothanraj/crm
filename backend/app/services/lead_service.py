"""Round-robin with OPEN_LEAD_LIMIT open leads per employee; extras stay unassigned (pending)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import AssignmentState, EnquirySequence, Lead, LeadActivity, LeadAssignment, LeadStatus, LeadStatusHistory, Notification, Role, User


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
    """Assign the next employee in the ring. Every lead gets an owner — no pending queue."""
    if lead.primary_employee_id:
        return None
    all_emps = eligible_employees(db)
    if not all_emps:
        return None  # no employees exist yet; stays pending until one is created
    st = db.query(AssignmentState).with_for_update().first()
    if not st:
        st = AssignmentState()
        db.add(st)
        db.flush()
    all_ids = [u.id for u in all_emps]
    try:
        start = all_ids.index(st.last_employee_id) + 1 if st.last_employee_id in all_ids else 0
    except ValueError:
        start = 0
    chosen = next(u for u in all_emps if u.id == all_ids[start % len(all_ids)])
    st.last_employee_id = chosen.id
    assign(db, lead, chosen, role="PRIMARY", by=by)
    return chosen


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


def assign(db: Session, lead: Lead, emp: User, role: str = "PRIMARY", by: User | None = None):
    import logging
    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=72)
    db.query(LeadAssignment).filter(
        LeadAssignment.lead_id == lead.id, LeadAssignment.role == role,
        LeadAssignment.is_current.is_(True)).update({"is_current": False})
    db.add(LeadAssignment(
        lead_id=lead.id, employee_id=emp.id, role=role,
        assigned_by=by.id if by else None, assigned_at=now, sla_deadline=deadline, is_current=True,
    ))
    if role == "PRIMARY":
        lead.primary_employee_id = emp.id
        lead.sla_deadline = deadline
        lead.sla_state = "PENDING"
        # New assignment window: the overdue digest may fire again for the new due date.
        lead.overdue_digest_at = None
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
    elif role == "TECHNICAL":
        lead.technical_employee_id = emp.id
    elif role == "SECONDARY":
        lead.secondary_support_employee_id = emp.id
    db.add(Notification(
        user_id=emp.id, lead_id=lead.id, kind="ASSIGNMENT",
        title="New lead assigned",
        body=f"{lead.enquiry_number} assigned. Contact the customer within 3 days (by {deadline:%d-%b-%Y %H:%M}).",
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
