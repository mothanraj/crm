"""Round-robin with 1-open-lead-per-employee; extras stay unassigned (pending)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AssignmentState, EnquirySequence, Lead, LeadActivity, LeadAssignment, LeadStatusHistory, Notification, User


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
    users = db.query(User).filter(User.is_active.is_(True)).all()
    return [u for u in users if u.role and u.role.name == "EMPLOYEE"]


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
    return [u for u in eligible_employees(db) if open_workload(db, u.id) < limit]


def auto_assign(db: Session, lead: Lead, by: User | None = None) -> User | None:
    """Assign one free employee. If none free, leave lead pending (unassigned)."""
    if lead.primary_employee_id:
        return None
    light = free_employees(db)
    if not light:
        return None  # stay pending
    st = db.query(AssignmentState).first()
    if not st:
        st = AssignmentState()
        db.add(st)
        db.flush()
    ids = [u.id for u in light]
    all_ids = [u.id for u in eligible_employees(db)]
    try:
        start = all_ids.index(st.last_employee_id) + 1 if st.last_employee_id in all_ids else 0
    except ValueError:
        start = 0
    # Prefer next in ring among free employees
    chosen = None
    for k in range(len(all_ids)):
        uid = all_ids[(start + k) % len(all_ids)]
        match = next((u for u in light if u.id == uid), None)
        if match:
            chosen = match
            break
    chosen = chosen or light[0]
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
