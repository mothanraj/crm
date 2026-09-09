"""APScheduler: every 15 min mark SLA-overdue leads + notify admin that employee did not follow up."""
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.models import Lead, Notification, User

scheduler = BackgroundScheduler()


def _sla_sweep():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        overdue = db.query(Lead).filter(
            Lead.is_active.is_(True),
            Lead.sla_state == "PENDING",
            Lead.sla_deadline.isnot(None),
            Lead.sla_deadline < now,
            Lead.first_contact_at.is_(None),
            Lead.primary_employee_id.isnot(None),
        ).all()
        if not overdue:
            return
        admins = [a for a in db.query(User).filter(User.is_active.is_(True)).all()
                  if a.role and a.role.name == "ADMIN"]
        for lead in overdue:
            lead.sla_state = "OVERDUE"
            owner = db.get(User, lead.primary_employee_id) if lead.primary_employee_id else None
            owner_name = owner.name if owner else "Unassigned employee"
            body = (
                f"{owner_name} did not follow up with customer "
                f"{lead.customer_name or '—'} ({lead.enquiry_number}) within 3 days. "
                f"Phone: {lead.contact_number or '—'}. Deadline was {lead.sla_deadline:%d-%b-%Y %H:%M}."
            )
            for admin in admins:
                db.add(Notification(
                    user_id=admin.id, lead_id=lead.id, kind="SLA_OVERDUE",
                    title="Employee did not follow up",
                    body=body,
                ))
            if owner:
                db.add(Notification(
                    user_id=owner.id, lead_id=lead.id, kind="SLA_OVERDUE",
                    title="Follow-up overdue",
                    body=f"You missed the 3-day contact SLA for {lead.enquiry_number} ({lead.customer_name}).",
                ))
        db.commit()
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.add_job(_sla_sweep, "interval", minutes=15, id="sla")
        scheduler.start()
