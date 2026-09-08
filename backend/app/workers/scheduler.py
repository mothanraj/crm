"""APScheduler: every 15 min mark SLA-overdue leads + notify admins/owners."""
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.models import Lead, LeadAssignment, Notification, User

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
        ).all()
        if not overdue:
            return
        admins = db.query(User).filter(User.is_active.is_(True)).all()
        admin_ids = [a.id for a in admins if a.role and a.role.name == "ADMIN"]
        for lead in overdue:
            lead.sla_state = "OVERDUE"
            owner = lead.primary_employee_id
            targets = set(admin_ids + ([owner] if owner else []))
            for uid in targets:
                db.add(Notification(
                    user_id=uid, lead_id=lead.id, kind="SLA_OVERDUE",
                    title="SLA OVERDUE",
                    body=f"Enquiry {lead.enquiry_number} ({lead.customer_name or lead.company_name}) assigned, deadline {lead.sla_deadline}, first contact not completed.",
                ))
        db.commit()
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.add_job(_sla_sweep, "interval", minutes=15, id="sla")
        scheduler.start()
