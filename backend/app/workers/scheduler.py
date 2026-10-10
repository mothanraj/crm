"""APScheduler: SLA sweeps + Brevo email (assignment batches + admin overdue digest).

- Every 15 min: mark PENDING leads past sla_deadline as OVERDUE (assignment
  window or each follow-up window after progress updates). Converted /
  Not Interested are excluded. Notify + mail admins; each deadline window
  mailed once via overdue_digest_at (cleared when SLA is refreshed).
- Hourly backstop: resend for any OVERDUE rows missed earlier.
- Assignment retry: resend failed assignment emails (once per lead).
Email failures only log — they never break the sweep.
"""
import logging
import math
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Lead, LeadAssignment, LeadSource, LeadStatus, Notification, Product, User
from app.services.lead_service import SLA_STOP_STATUSES, is_direct_call_name
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


def _is_reminder_deadline(lead) -> bool:
    """True when this lead's overdue deadline came from its picked reminder date."""
    rem = getattr(lead, "reminder_date", None)
    dl = getattr(lead, "sla_deadline", None)
    if rem is None or dl is None:
        return False
    try:
        from zoneinfo import ZoneInfo
        dl_ist_date = dl.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        try:
            dl_ist_date = dl.date()
        except Exception:
            return False
    try:
        return dl_ist_date == rem if not hasattr(rem, "date") else dl_ist_date == rem
    except Exception:
        return str(dl_ist_date) == str(rem)


def _sla_sweep():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        overdue = (
            db.query(Lead)
            .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
            .filter(
                Lead.is_active.is_(True),
                Lead.sla_state == "PENDING",
                Lead.sla_deadline.isnot(None),
                Lead.sla_deadline < now,
                Lead.primary_employee_id.isnot(None),
                # Keep ticking until Converted (Not Interested also stops the clock).
                or_(LeadStatus.name.is_(None), ~LeadStatus.name.in_(tuple(SLA_STOP_STATUSES))),
            )
            .all()
        )
        admins = _admins(db)
        for lead in overdue:
            lead.sla_state = "OVERDUE"
            owner = db.get(User, lead.primary_employee_id) if lead.primary_employee_id else None
            owner_name = owner.name if owner else "Unassigned employee"
            src = db.get(LeadSource, lead.source_id) if lead.source_id else None
            st = db.get(LeadStatus, lead.status_id) if lead.status_id else None
            direct = is_direct_call_name(src.name if src else "") and not lead.first_contact_at
            progress = (st.name if st else "") or "follow-up"
            reminder_driven = _is_reminder_deadline(lead)
            if direct and not reminder_driven:
                body = (
                    f"{owner_name} has not followed Direct Call customer "
                    f"{lead.customer_name or '—'} ({lead.enquiry_number}) within 24 hours. "
                    f"Phone: {lead.contact_number or '—'}. Deadline was {lead.sla_deadline:%d-%b-%Y %H:%M}."
                )
                admin_title = "Direct Call not followed"
                owner_body = (
                    f"You have not updated the Direct Call process for {lead.enquiry_number} "
                    f"({lead.customer_name}) within 24 hours."
                )
            elif reminder_driven:
                body = (
                    f"{owner_name} did not talk to customer "
                    f"{lead.customer_name or '—'} ({lead.enquiry_number}) by the reminder date. "
                    f"Phone: {lead.contact_number or '—'}. Reminder/overdue was {lead.sla_deadline:%d-%b-%Y %H:%M}."
                )
                admin_title = "Employee did not follow up"
                owner_body = (
                    f"You missed the reminder date follow-up and this lead is overdue for "
                    f"{lead.enquiry_number} ({lead.customer_name}). Current progress: {progress}."
                )
            else:
                body = (
                    f"{owner_name} did not update {progress} for customer "
                    f"{lead.customer_name or '—'} ({lead.enquiry_number}) within 3 days. "
                    f"Phone: {lead.contact_number or '—'}. Deadline was {lead.sla_deadline:%d-%b-%Y %H:%M}."
                )
                admin_title = "Employee did not follow up"
                owner_body = (
                    f"You missed the 3-day follow-up and this lead is overdue for "
                    f"{lead.enquiry_number} ({lead.customer_name}). Current progress: {progress}."
                )
            for admin in admins:
                db.add(Notification(
                    user_id=admin.id, lead_id=lead.id, kind="SLA_OVERDUE",
                    title=admin_title,
                    body=body,
                ))
            if owner:
                db.add(Notification(
                    user_id=owner.id, lead_id=lead.id, kind="SLA_OVERDUE",
                    title="Follow-up overdue",
                    body=owner_body,
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
        src = db.get(LeadSource, lead.source_id) if lead.source_id else None
        rem = getattr(lead, "reminder_date", None)
        bucket["leads"].append({
            "enquiry_number": lead.enquiry_number,
            "customer_name": lead.customer_name or "",
            "phone": lead.contact_number or "",
            "assigned_date_str": assigned_str,
            "deadline_str": lead.sla_deadline.strftime("%d-%b-%Y %H:%M") if lead.sla_deadline else "—",
            "days_overdue": days,
            "source": src.name if src else "",
            "lead_url": _lead_url(lead),
            "reminder_date": rem.isoformat() if rem is not None and hasattr(rem, "isoformat") else (str(rem) if rem else ""),
            "is_reminder_due": bool(_is_reminder_deadline(lead)),
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
        "lead_id": str(lead.id),
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
        ).order_by(Lead.created_at.asc()).limit(1000).all()
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
                # One lead once. Already-sent rows stay out of the batch.
                unique = []
                seen = set()
                for lead in leads:
                    if lead.id in seen or lead.assignment_email_sent_at is not None:
                        continue
                    seen.add(lead.id)
                    unique.append(lead)
                if not unique:
                    db.rollback()
                    continue
                items = [_assignment_item(db, x) for x in unique]
                chunk_size = max(1, int(email_service.ASSIGNMENT_EMAIL_CHUNK))
                all_ok = True
                for index in range(0, len(items), chunk_size):
                    chunk_items = items[index:index + chunk_size]
                    chunk_leads = unique[index:index + chunk_size]
                    batches = (len(items) + chunk_size - 1) // chunk_size
                    subject, html = email_service.build_assignment_email(
                        owner.name, chunk_items,
                        total=len(items), batch=(index // chunk_size) + 1, batches=batches,
                    )
                    if not email_service.send_email(owner.email, owner.name, subject, html):
                        all_ok = False
                        break
                    for x in chunk_leads:
                        x.assignment_email_sent_at = now
                    db.commit()
                if not all_ok and not any(x.assignment_email_sent_at for x in unique):
                    db.rollback()  # nothing sent — retry next sweep
            except Exception as exc:
                log.error("assignment retry failed for %s: %s", emp_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass
    except Exception as exc:
        log.error("assignment retry sweep failed: %s", exc)


def _reminder_sweep():
    """Hourly bell entries for today's due remainders (employee side).

    One unread REMINDER_DUE per lead per reminder_date per hour max:
    skips leads touched via reminder_sent_at within the hour or with a
    recent unread REMINDER_DUE for the same date. Stops automatically
    once the employee saves Work Progress (reminder_done=True clears
    the due filter). Failures only log — they never break the sweep.
    """
    db = SessionLocal()
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            today = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
        except Exception:
            today = now.date()
        cutoff = now - timedelta(hours=1)
        due = (
            db.query(Lead)
            .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
            .filter(
                Lead.is_active.is_(True),
                Lead.primary_employee_id.isnot(None),
                Lead.sla_state != "COMPLETED",
                Lead.reminder_date.isnot(None),
                Lead.reminder_date <= today,
                Lead.reminder_done.is_(False),
                or_(LeadStatus.name.is_(None), ~LeadStatus.name.in_(tuple(SLA_STOP_STATUSES))),
                or_(Lead.reminder_sent_at.is_(None), Lead.reminder_sent_at < cutoff),
            )
            .order_by(Lead.reminder_date.asc())
            .limit(1000)
            .all()
        )
        for lead in due:
            try:
                recent = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id == lead.primary_employee_id,
                        Notification.lead_id == lead.id,
                        Notification.kind == "REMINDER_DUE",
                        Notification.is_read.is_(False),
                        Notification.created_at >= cutoff,
                    )
                    .first()
                )
                if recent:
                    continue
                rem = str(lead.reminder_date) if lead.reminder_date else "—"
                db.add(Notification(
                    user_id=lead.primary_employee_id,
                    lead_id=lead.id,
                    kind="REMINDER_DUE",
                    title="Reminder due",
                    body=f"Reminder date {rem} | {lead.customer_name or '—'} | {lead.enquiry_number}",
                ))
                lead.reminder_sent_at = now
            except Exception as exc:
                log.error("reminder sweep failed for %s: %s", getattr(lead, "id", "?"), exc)
        db.commit()
    except Exception as exc:
        log.error("reminder sweep failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _overdue_digest():
    """Backstop: mail any OVERDUE rows missed earlier (downtime / Brevo failure).

    Runs hourly. Normal path mails immediately inside _sla_sweep the moment
    the 72h deadline passes, so this usually finds nothing.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = (
            db.query(Lead)
            .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
            .filter(
                Lead.is_active.is_(True),
                Lead.sla_state == "OVERDUE",
                Lead.primary_employee_id.isnot(None),
                Lead.overdue_digest_at.is_(None),
                or_(LeadStatus.name.is_(None), ~LeadStatus.name.in_(tuple(SLA_STOP_STATUSES))),
            )
            .order_by(Lead.sla_deadline.asc())
            .all()
        )
        if not rows:
            return
        _send_overdue_now(db, rows, now)
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.add_job(_sla_sweep, "interval", minutes=15, id="sla", replace_existing=True)
        scheduler.add_job(_reminder_sweep, "interval", hours=1, id="reminder",
                          replace_existing=True)
        scheduler.add_job(_overdue_digest, "interval", hours=1, id="digest",
                          replace_existing=True)
        scheduler.start()


def stop():
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
