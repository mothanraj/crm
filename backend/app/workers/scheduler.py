"""APScheduler: SLA sweeps + Brevo email (assignment batches + admin overdue digest).

- Every 15 min: mark SLA-overdue leads (72h after assignment with no
  first contact) + in-app notify + mail admins immediately, grouped by
  employee. Each lead mailed once (overdue_digest_at). No fixed daily slot.
- Hourly backstop: resend for any OVERDUE rows missed earlier (server was
  down at deadline, or Brevo failed last time).
- Assignment retry: resend failed assignment emails (once per lead).
Email failures only log — they never break the sweep.
"""
import logging
import math
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Lead, LeadAssignment, LeadSource, Notification, Product, User
from app.services import email_service

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _admins(db) -> list:
    from app.models import Role
    from sqlalchemy.orm import joinedload
    return (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name == "ADMIN")
        .options(joinedload(User.role))
        .all()
    )


def _lead_url(lead) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/leads/{lead.id}"


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
        admins = _admins(db)
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
        _send_overdue_now(db, [x for x in overdue if x.overdue_digest_at is None], now)
        _assignment_retry_sweep(db, now)
    finally:
        db.close()


def _digest_groups(db, rows, now) -> list[dict]:
    """Group overdue leads by employee for the admin digest payload."""
    owner_ids = {x.primary_employee_id for x in rows if x.primary_employee_id}
    owners = {u.id: u for u in db.query(User).filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    assigns = db.query(LeadAssignment).filter(
        LeadAssignment.lead_id.in_([x.id for x in rows]),
        LeadAssignment.is_current.is_(True),
    ).all()
    assign_by_lead = {a.lead_id: a for a in assigns}
    groups: dict[str, dict] = {}
    for lead in rows:
        owner = owners.get(lead.primary_employee_id)
        key = owner.name if owner else "Unassigned"
        bucket = groups.setdefault(key, {"employee": key, "leads": []})
        assign = assign_by_lead.get(lead.id)
        assigned_at = assign.assigned_at if assign else lead.created_at
        try:
            assigned_str = assigned_at.strftime("%d-%b-%Y") if assigned_at else "—"
        except Exception:
            assigned_str = "—"
        if lead.sla_deadline:
            days = max(1, math.ceil((now - lead.sla_deadline).total_seconds() / 86400))
        else:
            days = 1
        bucket["leads"].append({
            "enquiry_number": lead.enquiry_number,
            "customer_name": lead.customer_name or "",
            "phone": lead.contact_number or "",
            "assigned_date_str": assigned_str,
            "deadline_str": lead.sla_deadline.strftime("%d-%b-%Y %H:%M") if lead.sla_deadline else "—",
            "days_overdue": days,
            "lead_url": _lead_url(lead),
        })
    return list(groups.values())


def _send_overdue_now(db, rows, now) -> bool:
    """Mail admins immediately for freshly-overdue leads. Returns True if mailed."""
    rows = [x for x in rows if x.overdue_digest_at is None]
    if not rows:
        return False
    admins = [a for a in _admins(db) if a.email]
    if not admins:
        db.rollback()
        return False
    if not email_service.emails_enabled():
        return False
    payload = _digest_groups(db, rows, now)
    date_str = now.strftime("%d-%b-%Y")
    try:
        results = [email_service.send_overdue_digest(a.email, a.name, payload, date_str)
                   for a in admins]
    except Exception as exc:
        log.error("overdue immediate send failed: %s", exc)
        db.rollback()
        return False
    if all(results):
        for lead in rows:
            lead.overdue_digest_at = now
        db.commit()
        return True
    db.rollback()
    return False


def _assignment_item(db, lead) -> dict:
    src = db.get(LeadSource, lead.source_id) if lead.source_id else None
    prod = db.get(Product, lead.product_id) if lead.product_id else None
    try:
        cur = db.query(LeadAssignment).filter(
            LeadAssignment.lead_id == lead.id,
            LeadAssignment.is_current.is_(True),
        ).order_by(LeadAssignment.assigned_at.desc()).first()
        at = cur.assigned_at if cur else lead.created_at
        assigned_str = at.strftime("%d-%b-%Y") if at else "—"
    except Exception:
        assigned_str = "—"
    return {
        "enquiry_number": lead.enquiry_number,
        "legacy_enq": lead.legacy_enquiry_no,
        "enquiry_date": str(lead.enquiry_date) if lead.enquiry_date else "—",
        "assigned_date_str": assigned_str,
        "customer_name": lead.customer_name or "",
        "contact_number": lead.contact_number or "",
        "alternate_contact": lead.alternate_contact or "",
        "email": lead.email or "",
        "company_name": lead.company_name or "",
        "city": lead.city or "",
        "source": src.name if src else "—",
        "product": (lead.product_raw or (prod.name if prod else "") or "—"),
        "quantity_raw": lead.quantity_raw or "",
        "deadline_str": lead.sla_deadline.strftime("%d-%b-%Y %H:%M") if lead.sla_deadline else "—",
        "lead_url": _lead_url(lead),
    }


def _assignment_retry_sweep(db, now):
    """Resend batched assignment emails that failed earlier (once per lead).

    Rows are claimed with FOR UPDATE SKIP LOCKED so two workers never
    double-mail the same customer's PII.
    """
    if not email_service.emails_enabled():
        return
    try:
        # Group first without holding locks; each group is then re-selected
        # FOR UPDATE SKIP LOCKED so a second worker skips rows being mailed
        # instead of double-mailing customer PII. The sent flag is set only
        # after a successful send (fail-open retry).
        pending = db.query(Lead.id, Lead.primary_employee_id).filter(
            Lead.is_active.is_(True),
            Lead.primary_employee_id.isnot(None),
            Lead.assignment_email_sent_at.is_(None),
        ).order_by(Lead.created_at.asc()).limit(200).all()
        if not pending:
            return
        by_emp: dict = {}
        for lid, emp_id in pending:
            by_emp.setdefault(emp_id, []).append(lid)
        for emp_id, lead_ids in by_emp.items():
            try:
                leads = db.query(Lead).filter(
                    Lead.id.in_(lead_ids),
                    Lead.assignment_email_sent_at.is_(None),
                ).with_for_update(skip_locked=True).all()
                if not leads:
                    db.rollback()
                    continue
                owner = db.get(User, emp_id)
                if not owner:
                    db.rollback()
                    continue
                items = [_assignment_item(db, x) for x in leads]
                if not email_service.send_assignment_email(owner.email, owner.name, items):
                    db.rollback()  # retry next sweep
                    continue
                for x in leads:
                    x.assignment_email_sent_at = now
                db.commit()
            except Exception as exc:
                log.error("assignment retry failed for %s: %s", emp_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass
    except Exception as exc:
        log.error("assignment retry sweep failed: %s", exc)


def _overdue_digest():
    """Backstop: mail any OVERDUE rows missed earlier (downtime / Brevo failure).

    Runs hourly. Normal path mails immediately inside _sla_sweep the moment
    the 72h deadline passes, so this usually finds nothing.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(Lead).filter(
            Lead.is_active.is_(True),
            Lead.sla_state == "OVERDUE",
            Lead.first_contact_at.is_(None),
            Lead.primary_employee_id.isnot(None),
            Lead.overdue_digest_at.is_(None),
        ).order_by(Lead.sla_deadline.asc()).all()
        if not rows:
            return
        _send_overdue_now(db, rows, now)
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.add_job(_sla_sweep, "interval", minutes=15, id="sla", replace_existing=True)
        scheduler.add_job(_overdue_digest, "interval", hours=1, id="digest",
                          replace_existing=True)
        scheduler.start()


def stop():
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
