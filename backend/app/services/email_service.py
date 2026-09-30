"""Transactional email via Brevo REST API (httpx, no extra dependency).

Failures only log — email must never break imports, assigns, or sweeps.

Logic (Sep 2026):
- Employee: one batched email on assignment with full customer details.
  Every distinct lead appears once (keyed by lead id). Large lists are
  split into parts so Brevo accepts the HTML.
- Admin: one daily email listing customers past the 3-day due with no
  talk/status update, including assigned date.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
# Keep each message small enough for Brevo. Large Excel imports are split.
ASSIGNMENT_EMAIL_CHUNK = 25


def emails_enabled() -> bool:
    return bool(settings.EMAIL_ENABLED and settings.BREVO_API_KEY and settings.BREVO_SENDER_EMAIL)


def dedupe_assignment_items(leads: list[dict]) -> list[dict]:
    """Keep each lead once. Prefer lead_id so identical enquiry text cannot collapse rows."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in leads or []:
        lead_id = str(item.get("lead_id") or "").strip()
        enquiry = str(item.get("enquiry_number") or "").strip()
        key = lead_id or enquiry
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


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
            timeout=60.0,
        )
        if resp.status_code in (200, 201):
            log.info("email sent '%s' to %s (%s bytes html)", subject, to_email, len(html))
            return True
        log.error("Brevo rejected email '%s' to %s: %s %s", subject, to_email,
                  resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        log.error("email send failed '%s' to %s: %s", subject, to_email, exc)
        return False


def _is_direct_call(item: dict) -> bool:
    return str(item.get("source") or "").strip().lower() == "direct call"


def _lead_card(index: int, item: dict) -> str:
    """Full customer details card for one assigned lead."""
    if _is_direct_call(item):
        due = (
            f"<li><b>URGENT — Direct Call. Update the process within 24 hours. Due:</b> "
            f"{item.get('deadline_str') or '—'}</li>"
        )
    else:
        due = f"<li><b>Due date (contact within 3 days):</b> {item.get('deadline_str') or '—'}</li>"
    return f"""<hr>
<h3>{index}. {item.get('customer_name') or '—'} ({item.get('enquiry_number') or '—'})</h3>
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


def build_assignment_email(
    employee_name: str,
    leads: list[dict],
    *,
    total: int | None = None,
    batch: int = 1,
    batches: int = 1,
) -> tuple[str, str]:
    """(subject, html) for the batched assignment email to the employee.

    Each lead appears exactly once. When the assignment is split across
    several emails, batch/batches label the part (e.g. part 1/3).
    """
    leads = dedupe_assignment_items(leads)
    n = len(leads)
    total_n = total if total is not None else n
    enqs = ", ".join(
        str(x.get("enquiry_number") or "") for x in leads if x.get("enquiry_number")
    )
    if len(enqs) > 180:
        enqs = enqs[:177] + "…"
    part = f" · part {batch}/{batches}" if batches > 1 else ""
    count_label = f"{n} of {total_n}" if batches > 1 else str(n)
    direct = [x for x in leads if _is_direct_call(x)]
    if direct and len(direct) == n:
        subject = (
            f"URGENT Direct Call — update within 24 hours: {count_label} ({enqs}){part}"
            if enqs else f"URGENT Direct Call — update within 24 hours: {count_label}{part}"
        )
        intro = (
            f"{count_label} Direct Call customer(s) have been assigned to you{part}. "
            "This is urgent. Please update the work progress in the CRM within 24 hours. "
            f"Every lead below is listed once ({n} detail block(s) in this email)."
        )
    else:
        subject = (
            f"New customers assigned: {count_label} ({enqs}){part}"
            if enqs else f"New customers assigned: {count_label}{part}"
        )
        intro = (
            f"{count_label} new customer(s) have been assigned to you{part}. "
            "Please talk to each customer and update the work progress in the CRM within 3 days. "
            f"Every lead below is listed once ({n} detail block(s) in this email)."
        )
        if direct:
            intro += " Direct Call leads in this list are urgent — update those within 24 hours."
    index_rows = "".join(
        f"<li>{i}. {x.get('enquiry_number') or '—'} — {x.get('customer_name') or '—'} — "
        f"{x.get('contact_number') or '—'}</li>"
        for i, x in enumerate(leads, start=1)
    )
    cards = "".join(_lead_card(i, x) for i, x in enumerate(leads, start=1))
    html = f"""<p>Hi {employee_name or 'there'},</p>
<p>{intro}</p>
<p><b>Leads in this email ({n}):</b></p>
<ol>
{index_rows}
</ol>
{cards}
<p>— {settings.BREVO_SENDER_NAME}</p>"""
    return subject, html


def send_assignment_email(employee_email: str, employee_name: str,
                          leads: list[dict]) -> bool:
    """Send one or more assignment emails. Large lists are split into chunks.

    Returns True only when every chunk is accepted. Callers should mark
    assignment_email_sent_at only after a True result, or use
    send_assignment_email_chunks for per-chunk marking.
    """
    return send_assignment_email_chunks(employee_email, employee_name, leads)[0]


def send_assignment_email_chunks(
    employee_email: str,
    employee_name: str,
    leads: list[dict],
) -> tuple[bool, list[list[dict]]]:
    """Send assignment mail in chunks. Returns (all_sent, chunks that were sent)."""
    unique = dedupe_assignment_items(leads)
    if not unique:
        return False, []
    chunk_size = max(1, int(ASSIGNMENT_EMAIL_CHUNK))
    batches = (len(unique) + chunk_size - 1) // chunk_size
    sent_chunks: list[list[dict]] = []
    for index in range(batches):
        chunk = unique[index * chunk_size:(index + 1) * chunk_size]
        subject, html = build_assignment_email(
            employee_name, chunk, total=len(unique), batch=index + 1, batches=batches,
        )
        if not send_email(employee_email, employee_name, subject, html):
            return False, sent_chunks
        sent_chunks.append(chunk)
    return True, sent_chunks


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
