"""Transactional email via SMTP (stdlib smtplib, no extra dependency).

Failures only log — email must never break imports, assigns, or sweeps.

Logic (Sep 2026):
- Employee: one batched email on assignment with full customer details.
  Every distinct lead appears once (keyed by lead id). Large lists are
  split into parts so messages stay small.
- Admin: one daily email listing customers past the 3-day due with no
  talk/status update, including assigned date.
"""
from __future__ import annotations

import logging
import smtplib
import threading
import time
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import text

from app.core.config import settings

log = logging.getLogger(__name__)

# Fewer, larger messages reduce SMTP handshakes and shared-host rate limits.
ASSIGNMENT_EMAIL_CHUNK = max(1, int(settings.ASSIGNMENT_EMAIL_CHUNK))
_SMTP_RETRY_DELAYS = (1.0, 3.0, 8.0)
_ASSIGNMENT_MAIL_LOCK_KEY = 0x5E4A7E11
_assignment_process_lock = threading.Lock()


def emails_enabled() -> bool:
    return bool(settings.EMAIL_ENABLED and settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


@contextmanager
def assignment_mail_lock():
    """Serialize all assignment mail sends across threads and workers.

    Yields True when this caller owns the lock, False when another dispatch is
    already running. A process lock covers a single worker; a PostgreSQL
    advisory lock covers multiple Render workers without blocking them.
    """
    if not _assignment_process_lock.acquire(blocking=False):
        yield False
        return
    conn = None
    db_locked = False
    locked = False
    try:
        try:
            from app.db.session import engine
            conn = engine.connect()
            db_locked = bool(
                conn.execute(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": _ASSIGNMENT_MAIL_LOCK_KEY},
                ).scalar()
            )
            locked = db_locked
        except Exception as exc:
            log.warning("assignment mail advisory lock unavailable; using process lock: %s", exc)
            locked = True
        yield locked
    finally:
        if conn is not None:
            try:
                if db_locked:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"),
                        {"key": _ASSIGNMENT_MAIL_LOCK_KEY},
                    )
            except Exception as exc:
                log.warning("assignment mail advisory unlock failed: %s", exc)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        _assignment_process_lock.release()


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


def _build_message(to_email: str, to_name: str, subject: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL))
    msg["To"] = formataddr((to_name or to_email, to_email))
    # Plaintext fallback for clients that ignore HTML; HTML is the real body.
    msg.set_content("Please view this email in an HTML-capable mail client.")
    msg.add_alternative(html, subtype="html")
    return msg


def _transient_smtp_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused),
    ):
        return False
    if isinstance(exc, smtplib.SMTPDataError):
        code = int(getattr(exc, "smtp_code", 0) or 0)
        return 400 <= code < 500
    return isinstance(exc, (smtplib.SMTPException, OSError, TimeoutError))


class SMTPMailer:
    """Reuse one SMTP connection for a batch of messages.

    Bluehost/Exim advertises MAILMAX=50; rotate the session before that limit.
    A broken connection is reopened for the next attempt instead of leaking it.
    """

    def __init__(self, *, message_limit: int | None = None,
                 retry_delays: tuple[float, ...] | None = None):
        self.message_limit = max(
            1, int(message_limit if message_limit is not None else settings.EMAIL_SESSION_MESSAGE_LIMIT)
        )
        self.retry_delays = tuple(retry_delays if retry_delays is not None else _SMTP_RETRY_DELAYS)
        self._smtp: smtplib.SMTP | None = None
        self._sent = 0
        self.connect_seconds = 0.0
        self.login_seconds = 0.0

    def open(self) -> "SMTPMailer":
        self.close()
        timeout = max(5, int(settings.SMTP_TIMEOUT or 30))
        started = time.perf_counter()
        if settings.SMTP_USE_SSL:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST, int(settings.SMTP_PORT), timeout=timeout
            )
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, int(settings.SMTP_PORT), timeout=timeout)
        connected = time.perf_counter()
        try:
            if not settings.SMTP_USE_SSL and settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        except Exception:
            try:
                smtp.quit()
            except Exception:
                pass
            raise
        logged_in = time.perf_counter()
        self._smtp = smtp
        self._sent = 0
        self.connect_seconds = connected - started
        self.login_seconds = logged_in - connected
        log.info(
            "SMTP session opened host=%s port=%s connect=%.2fs login=%.2fs",
            settings.SMTP_HOST, int(settings.SMTP_PORT),
            self.connect_seconds, self.login_seconds,
        )
        return self

    def close(self) -> None:
        smtp, self._smtp = self._smtp, None
        if smtp is None:
            return
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass

    def __enter__(self) -> "SMTPMailer":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def noop(self):
        if self._smtp is None:
            self.open()
        assert self._smtp is not None
        return self._smtp.noop()

    def _send_once(self, msg: EmailMessage) -> None:
        if self._smtp is None or self._sent >= self.message_limit:
            self.open()
        assert self._smtp is not None
        self._smtp.send_message(msg)
        self._sent += 1

    def send(self, to_email: str, to_name: str, subject: str, html: str) -> bool:
        if not emails_enabled():
            log.info("email disabled — skipping '%s' to %s", subject, to_email)
            return False
        if not to_email:
            log.warning("email skipped — empty recipient for '%s'", subject)
            return False
        msg = _build_message(to_email, to_name, subject, html)
        attempts = max(1, int(settings.EMAIL_SEND_ATTEMPTS))
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                self._send_once(msg)
                log.info(
                    "email sent '%s' to %s in %.2fs attempt=%d session_messages=%d html=%d bytes",
                    subject, to_email, time.perf_counter() - started, attempt,
                    self._sent, len(html),
                )
                return True
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.close()
                log.warning(
                    "email attempt %d/%d failed '%s' to %s after %.2fs: %s: %s",
                    attempt, attempts, subject, to_email, elapsed,
                    type(exc).__name__, exc,
                )
                if not _transient_smtp_error(exc) or attempt >= attempts:
                    log.error("email send failed '%s' to %s: %s", subject, to_email, exc)
                    return False
                delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
                if delay > 0:
                    time.sleep(delay)
        return False


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    *,
    mailer: SMTPMailer | None = None,
) -> bool:
    """Send one transactional email via SMTP. Returns True on accept."""
    if mailer is not None:
        return mailer.send(to_email, to_name, subject, html)
    with SMTPMailer() as smtp:
        return smtp.send(to_email, to_name, subject, html)


def smtp_diagnose() -> dict:
    """Connect, authenticate, and NOOP without sending any email."""
    result = {
        "enabled": emails_enabled(),
        "host": settings.SMTP_HOST,
        "port": int(settings.SMTP_PORT),
        "ssl": bool(settings.SMTP_USE_SSL),
        "tls": bool(settings.SMTP_USE_TLS),
        "message_limit": int(settings.EMAIL_SESSION_MESSAGE_LIMIT),
        "chunk_size": int(ASSIGNMENT_EMAIL_CHUNK),
    }
    if not result["enabled"]:
        return {**result, "ok": False, "error": "email not configured"}
    mailer = SMTPMailer()
    try:
        started = time.perf_counter()
        mailer.open()
        noop_started = time.perf_counter()
        code, message = mailer.noop()
        noop_seconds = time.perf_counter() - noop_started
        return {
            **result,
            "ok": True,
            "connect_ms": round(mailer.connect_seconds * 1000),
            "login_ms": round(mailer.login_seconds * 1000),
            "noop_ms": round(noop_seconds * 1000),
            "total_ms": round((time.perf_counter() - started) * 1000),
            "smtp_code": int(code),
            "smtp_message": str(message)[:200],
        }
    except Exception as exc:
        log.exception("SMTP diagnose failed: %s", exc)
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        mailer.close()


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
<p>— {settings.SMTP_FROM_NAME}</p>"""
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
    with SMTPMailer() as mailer:
        for index in range(batches):
            chunk = unique[index * chunk_size:(index + 1) * chunk_size]
            subject, html = build_assignment_email(
                employee_name, chunk, total=len(unique), batch=index + 1, batches=batches,
            )
            if not send_email(employee_email, employee_name, subject, html, mailer=mailer):
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
    direct_n = sum(1 for item in all_items if _is_direct_call(item) and not item.get("is_reminder_due"))
    reminder_n = sum(1 for item in all_items if item.get("is_reminder_due"))
    if direct_n and direct_n == total:
        subject = f"Direct Call not followed: {total} customer(s) past 24 hours ({date_str})"
        intro = (
            "The following Direct Call customers were not updated within 24 hours. "
            "The assigned employee has not followed them yet:"
        )
    elif reminder_n and reminder_n == total:
        subject = f"Not updated: {total} customer(s) past reminder date ({date_str})"
        intro = (
            "The following assigned customers were not talked to by their reminder date. "
            "The assigned employee has not updated them yet:"
        )
    elif direct_n:
        subject = f"Not updated: {total} customer(s) past due ({date_str})"
        intro = (
            "The following assigned customers were not updated on time. "
            "Direct Call leads were due within 24 hours. Reminder-date leads were due on their "
            "reminder date. Other leads were due within 3 days:"
        )
    elif reminder_n:
        subject = f"Not updated: {total} customer(s) past due ({date_str})"
        intro = (
            "The following assigned customers were not updated on time. "
            "Reminder-date leads were due on their reminder date. Other leads were due within 3 days:"
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
            if _is_direct_call(item) and not item.get("is_reminder_due"):
                rows += (
                    f"<li><b>{g.get('employee', 'Employee')}</b> has not followed "
                    f"<b>{item.get('customer_name') or '—'}</b> "
                    f"({item.get('enquiry_number')}) yet. Direct Call — process was not updated "
                    f"within 24 hours. Phone {item.get('phone') or '—'}, "
                    f"assigned {item.get('assigned_date_str') or '—'}, "
                    f"due {item.get('deadline_str')} — "
                    f"<a href=\"{item.get('lead_url')}\">open lead</a></li>"
                )
            elif item.get("is_reminder_due"):
                rows += (
                    f"<li><b>{g.get('employee', 'Employee')}</b> did not talk to "
                    f"<b>{item.get('customer_name') or '—'}</b> "
                    f"({item.get('enquiry_number')}) by the reminder date. "
                    f"Phone {item.get('phone') or '—'}, "
                    f"assigned {item.get('assigned_date_str') or '—'}, "
                    f"reminder/overdue {item.get('deadline_str')}, {item.get('days_overdue')} day(s) overdue — "
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
<p>— {settings.SMTP_FROM_NAME}</p>"""
    return subject, html


def send_overdue_digest(admin_email: str, admin_name: str, groups: list[dict],
                        date_str: str, *, mailer: SMTPMailer | None = None) -> bool:
    subject, html = build_overdue_digest(date_str, groups)
    return send_email(admin_email, admin_name, subject, html, mailer=mailer)
