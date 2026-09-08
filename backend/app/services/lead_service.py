"""Round-robin with workload check; single intake seam for all future sources."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AssignmentState, EnquirySequence, Lead, LeadAssignment, LeadStatusHistory, Notification, User
from app.services.normalize import norm_phone


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
    return [u for u in users if u.role and u.role.name in ("EMPLOYEE", "ADMIN")]


def auto_assign(db: Session, lead: Lead, by: User | None = None) -> User | None:
    cand = eligible_employees(db)
    if not cand:
        return None
    # workload filter: open leads < limit
    open_counts = {}
    for u in cand:
        open_counts[u.id] = db.query(Lead).filter(
            Lead.primary_employee_id == u.id, Lead.is_active.is_(True)).count()
    light = [u for u in cand if open_counts[u.id] < settings.OPEN_LEAD_LIMIT] or cand
    st = db.query(AssignmentState).first()
    if not st:
        st = AssignmentState()
        db.add(st)
        db.flush()
    ids = [u.id for u in cand]
    try:
        i = ids.index(st.last_employee_id) + 1 if st.last_employee_id in ids else 0
    except ValueError:
        i = 0
    # walk ring until a light candidate
    chosen = None
    for k in range(len(cand)):
        u = cand[(i + k) % len(cand)]
        if u in light:
            chosen = u
            break
    chosen = chosen or light[0]
    st.last_employee_id = chosen.id
    assign(db, lead, chosen, role="PRIMARY", by=by)
    return chosen


def assign(db: Session, lead: Lead, emp: User, role: str = "PRIMARY", by: User | None = None):
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=72)
    # retire current of same role
    db.query(LeadAssignment).filter(
        LeadAssignment.lead_id == lead.id, LeadAssignment.role == role,
        LeadAssignment.is_current.is_(True)).update({"is_current": False})
    db.add(LeadAssignment(lead_id=lead.id, employee_id=emp.id, role=role,
                          assigned_by=by.id if by else None, assigned_at=now, sla_deadline=deadline))
    if role == "PRIMARY":
        lead.primary_employee_id = emp.id
        lead.sla_deadline = deadline
        lead.sla_state = "PENDING"
    elif role == "TECHNICAL":
        lead.technical_employee_id = emp.id
    elif role == "SECONDARY":
        lead.secondary_support_employee_id = emp.id
    db.add(Notification(user_id=emp.id, lead_id=lead.id, kind="ASSIGNMENT",
                        title="New lead assigned",
                        body=f"{lead.enquiry_number} assigned. Contact within 3 days (by {deadline:%d-%b-%Y %H:%M})."))
    db.flush()


def change_status(db: Session, lead: Lead, new_status_id, by: User | None, reason: str = ""):
    old = lead.status_id
    if old == new_status_id:
        return
    lead.status_id = new_status_id
    db.add(LeadStatusHistory(lead_id=lead.id, old_status_id=old, new_status_id=new_status_id,
                             changed_by=by.id if by else None, reason=reason))
    db.flush()


def record_first_contact(db: Session, lead: Lead, by: User, method: str, result: str, notes: str = ""):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    lead.first_contact_at = now
    lead.first_contact_method = method
    lead.first_contact_result = result
    lead.first_contact_by = by.id
    lead.first_contact_notes = notes
    lead.sla_state = "COMPLETED" if (not lead.sla_deadline or now <= lead.sla_deadline) else "OVERDUE"
    db.flush()
