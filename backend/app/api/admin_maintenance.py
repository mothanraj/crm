"""Admin maintenance: manual overdue-digest run with diagnostics.

The scheduled digest is silent (logs only) and runs once daily at
OVERDUE_DIGEST_HOUR + once per lead via overdue_digest_at. This endpoint
lets an admin see WHY no mail arrived and trigger a send on demand.
"""
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.deps import admin_only
from app.db.session import get_db
from app.models import Lead, LeadAssignment, LeadSource, Role, User
from app.services import email_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _mailable_admins(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name == "ADMIN")
        .options(joinedload(User.role))
        .all()
    )


def _diagnose(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    base = db.query(Lead).filter(Lead.is_active.is_(True))
    return {
        "now_utc": now.isoformat(),
        "overdue_digest_hour_ist": int(settings.OVERDUE_DIGEST_HOUR),
        "emails_enabled": bool(email_service.emails_enabled()),
        "email_enabled_flag": bool(settings.EMAIL_ENABLED),
        "brevo_key_set": bool(settings.BREVO_API_KEY),
        "sender_set": bool(settings.BREVO_SENDER_EMAIL),
        "sender_name": settings.BREVO_SENDER_NAME,
        "counts": {
            "pending": base.filter(Lead.sla_state == "PENDING").count(),
            "overdue_total": base.filter(Lead.sla_state == "OVERDUE").count(),
            "overdue_uncontacted_assigned": base.filter(
                Lead.sla_state == "OVERDUE",
                Lead.first_contact_at.is_(None),
                Lead.primary_employee_id.isnot(None),
            ).count(),
            "overdue_ready_to_mail": base.filter(
                Lead.sla_state == "OVERDUE",
                Lead.first_contact_at.is_(None),
                Lead.primary_employee_id.isnot(None),
                Lead.overdue_digest_at.is_(None),
            ).count(),
            "overdue_already_mailed": base.filter(
                Lead.sla_state == "OVERDUE",
                Lead.overdue_digest_at.isnot(None),
            ).count(),
        },
    }


@router.get("/overdue-digest/status")
def digest_status(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    diag = _diagnose(db)
    admins = _mailable_admins(db)
    diag["admins"] = [
        {"name": a.name, "email": a.email, "is_active": a.is_active} for a in admins
    ]
    return diag


@router.post("/overdue-digest/run")
def digest_run(
    resend: bool = Query(False, description="Include already-mailed OVERDUE leads too"),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    now = datetime.now(timezone.utc)
    q = db.query(Lead).filter(
        Lead.is_active.is_(True),
        Lead.sla_state == "OVERDUE",
        Lead.first_contact_at.is_(None),
        Lead.primary_employee_id.isnot(None),
    )
    if not resend:
        q = q.filter(Lead.overdue_digest_at.is_(None))
    rows = q.order_by(Lead.sla_deadline.asc()).limit(500).all()

    admins = [a for a in _mailable_admins(db) if a.email]
    diag = _diagnose(db)
    sample = [x.enquiry_number for x in rows[:10]]

    if not rows:
        return {
            "mailed": False,
            "reason": "no mailable OVERDUE rows (already mailed, contacted, unassigned, or still PENDING)",
            "resend": resend,
            "sample": [],
            "diagnostics": diag,
            "admins": [a.email for a in admins],
        }
    if not admins:
        return {
            "mailed": False,
            "reason": "no active ADMIN with email",
            "resend": resend,
            "sample": sample,
            "diagnostics": diag,
            "admins": [],
        }
    if not email_service.emails_enabled():
        return {
            "mailed": False,
            "reason": "email not configured (EMAIL_ENABLED/BREVO_API_KEY/BREVO_SENDER_EMAIL)",
            "resend": resend,
            "sample": sample,
            "diagnostics": diag,
            "admins": [a.email for a in admins],
        }

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
        days = (
            max(1, math.ceil((now - lead.sla_deadline).total_seconds() / 86400))
            if lead.sla_deadline
            else 1
        )
        src = db.get(LeadSource, lead.source_id) if lead.source_id else None
        bucket["leads"].append({
            "enquiry_number": lead.enquiry_number,
            "customer_name": lead.customer_name or "",
            "phone": lead.contact_number or "",
            "assigned_date_str": assigned_str,
            "deadline_str": lead.sla_deadline.strftime("%d-%b-%Y %H:%M") if lead.sla_deadline else "—",
            "days_overdue": days,
            "source": src.name if src else "",
            "lead_url": f"{settings.FRONTEND_URL.rstrip('/')}/leads/{lead.id}",
        })
    payload = list(groups.values())
    date_str = now.strftime("%d-%b-%Y")
    results = {}
    try:
        for a in admins:
            ok = email_service.send_overdue_digest(a.email, a.name, payload, date_str)
            results[a.email] = bool(ok)
    except Exception as exc:
        log.error("manual overdue digest send failed: %s", exc)
        db.rollback()
        return {
            "mailed": False,
            "reason": f"send exception: {exc}",
            "resend": resend,
            "sample": sample,
            "diagnostics": diag,
            "admins": [a.email for a in admins],
        }
    if all(results.values()):
        for lead in rows:
            lead.overdue_digest_at = now
        db.commit()
        return {
            "mailed": True,
            "count": len(rows),
            "groups": len(payload),
            "resend": resend,
            "sample": sample,
            "results": results,
            "diagnostics": diag,
        }
    db.rollback()
    return {
        "mailed": False,
        "reason": "Brevo rejected or send failed for at least one admin (see backend logs)",
        "resend": resend,
        "sample": sample,
        "results": results,
        "diagnostics": diag,
        "admins": [a.email for a in admins],
    }
