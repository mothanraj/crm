"""Transactional email via Brevo REST API (httpx, no extra dependency).

Failures only log — email must never break imports, assigns, or sweeps.

Logic (Sep 2026):
- Employee: one batched email on assignment with full customer details.
- Admin: one daily email listing customers past the 3-day due with no
  talk/status update, including assigned date.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def emails_enabled() -> bool:
    return bool(settings.EMAIL_ENABLED and settings.BREVO_API_KEY and settings.BREVO_SENDER_EMAIL)


def send_email(to_email: str, to_name: str, subject: str, html: str) -> bool:
    """POST one transactional email via Brevo. Returns True on accept."""
    if not emails_enabled():
        log.info("email disabled — skipping '%s' to %s", subject, to_email)
        return False
    if not to_email:
        log.warning("email skipped — empty recipient for '%s'", subject)
        return False
    payload = {
        "sender": {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    try:
        resp = httpx.post(
            BREVO_SEND_URL,
            json=payload,
            headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json",
                     "Accept": "application/json"},
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            log.info("email sent '%s' to %s", subject, to_email)
            return True
        log.error("Brevo rejected email '%s' to %s: %s %s", subject, to_email,
                  resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        log.error("email send failed '%s' to %s: %s", subject, to_email, exc)
        return False


def _is_direct_call(item: dict) -> bool:
    return str(item.get("source") or "").strip().lower() == "direct call"


def _lead_card(item: dict) -> str:
    """Full customer details card for one assigned lead."""
    if _is_direct_call(item):
        due = (
            f"<li><b>URGENT — Direct Call. Update the process within 24 hours. Due:</b> "
            f"{item.get('deadline_str') or '—'}</li>"
        )
    else:
        due = f"<li><b>Due date (contact within 3 days):</b> {item.get('deadline_str') or '—'}</li>"
    return f"""<hr>
<h3>{item.get('customer_name') or '—'} ({item.get('enquiry_number') or '—'})</h3>
<ul>
<li><b>Enquiry number:</b> {item.get('enquiry_number') or '—'}{(' / Excel #' + str(item.get('legacy_enq'))) if item.get('legacy_enq') is not None else ''}</li>
<li><b>Enquiry date:</b> {item.get('enquiry_date') or '—'}</li>
<li><b>Assigned date:</b> {item.get('assigned_date_str') or '—'}</li>
<li><b>Customer name:</b> {item.get('customer_name') or '—'}</li>
<li><b>Phone number:</b> {item.get('contact_number') or '—'}{(' / ' + str(item.get('alternate_contact'))) if item.get('alternate_contact') else ''}</li>
<li><b>Product details:</b> {item.get('product') or '—'}{(' (' + str(item.get('quantity_raw')) + ')') if item.get('quantity_raw') else ''}</li>
{due}
<li><b>Email:</b> {item.get('email') or '—'}</li>
<li><b>Company:</b> {item.get('company_name') or '—'}</li>
<li><b>City:</b> {item.get('city') or '—'}</li>
<li><b>Source:</b> {item.get('source') or '—'}</li>
<li><b>Open in CRM:</b> <a href="{item.get('lead_url') or '#'}">{item.get('lead_url') or '—'}</a></li>
</ul>"""


def build_assignment_email(employee_name: str, leads: list[dict]) -> tuple[str, str]:
    """(subject, html) for the batched assignment email to the employee.

    leads: [{enquiry_number, legacy_enq, enquiry_date, assigned_date_str,
      customer_name, contact_number, alternate_contact, email, company_name,
      city, source, product, quantity_raw, deadline_str, lead_url}]
    Direct Call rows ask for an update within 24 hours. Other sources stay at 3 days.
    """
    n = len(leads)
    enqs = ", ".join(str(x.get("enquiry_number") or "") for x in leads[:5] if x.get("enquiry_number"))
    direct = [x for x in leads if _is_direct_call(x)]
    if direct and len(direct) == n:
        subject = (
            f"URGENT Direct Call — update within 24 hours: {n} ({enqs})"
            if enqs else f"URGENT Direct Call — update within 24 hours: {n}"
        )
        intro = (
            f"{n} Direct Call customer(s) have been assigned to you. "
            "This is urgent. Please update the work progress in the CRM within 24 hours."
        )
    else:
        subject = f"New customers assigned: {n} ({enqs})" if enqs else f"New customers assigned: {n}"
        intro = (
            f"{n} new customer(s) have been assigned to you. "
            "Please talk to each customer and update the work progress in the CRM within 3 days."
        )
        if direct:
            intro += " Direct Call leads in this list are urgent — update those within 24 hours."
    cards = "".join(_lead_card(x) for x in leads)
    html = f"""<p>Hi {employee_name or 'there'},</p>
<p>{intro}</p>
{cards}
<p>— {settings.BREVO_SENDER_NAME}</p>"""
    return subject, html


def send_assignment_email(employee_email: str, employee_name: str,
                          leads: list[dict]) -> bool:
    if not leads:
        return False
    subject, html = build_assignment_email(employee_name, leads)
    return send_email(employee_email, employee_name, subject, html)


def build_overdue_digest(date_str: str, groups: list[dict]) -> tuple[str, str]:
    """(subject, html) for the daily admin digest.

    groups: [{employee, leads: [{enquiry_number, customer_name, phone,
      assigned_date_str, deadline_str, days_overdue, lead_url}]}]
    """
    total = sum(len(g.get("leads", [])) for g in groups)
    all_items = [item for g in groups for item in g.get("leads", [])]
    direct_n = sum(1 for item in all_items if _is_direct_call(item))
    if direct_n and direct_n == total:
        subject = f"Direct Call not followed: {total} customer(s) past 24 hours ({date_str})"
        intro = (
            "The following Direct Call customers were not updated within 24 hours. "
            "The assigned employee has not followed them yet:"
        )
    elif direct_n:
        subject = f"Not updated: {total} customer(s) past due ({date_str})"
        intro = (
            "The following assigned customers were not updated on time. "
            "Direct Call leads were due within 24 hours. Other leads were due within 3 days:"
        )
    else:
        subject = f"Not updated: {total} customer(s) past 3-day due ({date_str})"
        intro = (
            "The following assigned customers were not talked to and their status "
            "was not updated within the 3-day due date:"
        )
    rows = ""
    for g in groups:
        rows += f"<h3>{g.get('employee', '—')} — {len(g.get('leads', []))} not updated</h3><ul>"
        for item in g.get("leads", []):
            if _is_direct_call(item):
                rows += (
                    f"<li><b>{g.get('employee', 'Employee')}</b> has not followed "
                    f"<b>{item.get('customer_name') or '—'}</b> "
                    f"({item.get('enquiry_number')}) yet. Direct Call — process was not updated "
                    f"within 24 hours. Phone {item.get('phone') or '—'}, "
                    f"assigned {item.get('assigned_date_str') or '—'}, "
                    f"due {item.get('deadline_str')} — "
                    f"<a href=\"{item.get('lead_url')}\">open lead</a></li>"
                )
            else:
                rows += (
                    f"<li><b>{item.get('customer_name') or '—'}</b> "
                    f"({item.get('enquiry_number')}) — {item.get('phone') or '—'}, "
                    f"assigned {item.get('assigned_date_str') or '—'}, "
                    f"due {item.get('deadline_str')}, {item.get('days_overdue')} day(s) overdue — "
                    f"<a href=\"{item.get('lead_url')}\">open lead</a></li>"
                )
        rows += "</ul>"
    html = f"""<p>{intro}</p>
{rows}
<p>— {settings.BREVO_SENDER_NAME}</p>"""
    return subject, html


def send_overdue_digest(admin_email: str, admin_name: str, groups: list[dict],
                        date_str: str) -> bool:
    subject, html = build_overdue_digest(date_str, groups)
    return send_email(admin_email, admin_name, subject, html)
