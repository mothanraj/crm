import smtplib

import app.services.email_service as email_service
from app.services.email_service import (
    ASSIGNMENT_EMAIL_CHUNK,
    SMTPMailer,
    build_assignment_email,
    build_overdue_digest,
    dedupe_assignment_items,
    send_assignment_email,
    send_email,
    smtp_diagnose,
)


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logins = 0
        self.sent = []
        self.quit_called = False
        self.fail_next = 0
        FakeSMTP.instances.append(self)

    def login(self, username, password):
        self.logins += 1

    def send_message(self, msg):
        if self.fail_next:
            self.fail_next -= 1
            raise smtplib.SMTPServerDisconnected("temporary disconnect")
        self.sent.append(msg)

    def noop(self):
        return 250, b"OK"

    def quit(self):
        self.quit_called = True

    def close(self):
        pass


def _smtp_env(monkeypatch, **overrides):
    FakeSMTP.instances = []
    values = {
        "EMAIL_ENABLED": True,
        "SMTP_HOST": "smtp.test",
        "SMTP_PORT": 465,
        "SMTP_USE_SSL": True,
        "SMTP_USE_TLS": False,
        "SMTP_USERNAME": "user@test",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM_EMAIL": "from@test",
        "SMTP_FROM_NAME": "Test",
        "SMTP_TIMEOUT": 5,
        "EMAIL_SEND_ATTEMPTS": 2,
        "EMAIL_SESSION_MESSAGE_LIMIT": 40,
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(email_service.settings, key, value)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def test_smtp_mailer_reuses_one_connection(monkeypatch):
    fake = _smtp_env(monkeypatch)
    with SMTPMailer() as mailer:
        assert send_email("a@test", "A", "one", "<p>1</p>", mailer=mailer) is True
        assert send_email("b@test", "B", "two", "<p>2</p>", mailer=mailer) is True
    assert len(fake.instances) == 1
    assert fake.instances[0].logins == 1
    assert len(fake.instances[0].sent) == 2


def test_smtp_mailer_rotates_session_at_limit(monkeypatch):
    fake = _smtp_env(monkeypatch)
    with SMTPMailer(message_limit=1, retry_delays=(0,)) as mailer:
        assert send_email("a@test", "A", "one", "<p>1</p>", mailer=mailer) is True
        assert send_email("b@test", "B", "two", "<p>2</p>", mailer=mailer) is True
    assert len(fake.instances) == 2
    assert all(len(s.sent) == 1 for s in fake.instances)


def test_smtp_mailer_retries_transient_error(monkeypatch):
    fake = _smtp_env(monkeypatch, EMAIL_SEND_ATTEMPTS=2)
    original_init = FakeSMTP.__init__

    def flaky_init(self, host, port, timeout=None):
        original_init(self, host, port, timeout)
        if len(FakeSMTP.instances) == 1:
            self.fail_next = 1

    monkeypatch.setattr(FakeSMTP, "__init__", flaky_init)
    with SMTPMailer(retry_delays=(0,)) as mailer:
        assert mailer.send("a@test", "A", "one", "<p>1</p>") is True
    assert len(fake.instances) == 2
    assert len(fake.instances[1].sent) == 1


def test_smtp_diagnose_does_not_send(monkeypatch):
    fake = _smtp_env(monkeypatch)
    result = smtp_diagnose()
    assert result["ok"] is True
    assert result["smtp_code"] == 250
    assert len(fake.instances) == 1
    assert fake.instances[0].sent == []


def _lead(n: int) -> dict:
    return {
        "lead_id": f"lead-{n}",
        "enquiry_number": f"ENQ-00000{n}",
        "legacy_enq": 100 + n,
        "enquiry_date": "2026-09-10",
        "assigned_date_str": "11-Sep-2026",
        "customer_name": f"Customer{n}",
        "contact_number": f"900000000{n}",
        "alternate_contact": "",
        "email": f"customer{n}@example.com",
        "company_name": f"Company{n}",
        "city": "Chennai",
        "source": "Facebook/Instagram",
        "product": "Puzzle Parking System",
        "quantity_raw": "2",
        "deadline_str": "14-Sep-2026 10:00",
        "lead_url": f"http://localhost:5173/leads/lead-{n}",
    }


def test_assignment_multi_lead_template():
    leads = [_lead(n) for n in range(1, 5)]
    subject, html = build_assignment_email("hari", leads)
    assert "4" in subject
    for n in range(1, 5):
        assert f"ENQ-00000{n}" in html
        assert f"Customer{n}" in html
        assert f"900000000{n}" in html
        assert f"http://localhost:5173/leads/lead-{n}" in html
    # Full details present
    assert "Facebook/Instagram" in html
    assert "Puzzle Parking System" in html
    assert "14-Sep-2026 10:00" in html
    assert "2026-09-10" in html
    assert "11-Sep-2026" in html


def test_assignment_single_lead_template():
    subject, html = build_assignment_email("mothan", [_lead(1)])
    assert "1" in subject
    assert "ENQ-000001" in html
    assert "Customer1" in html


def test_assignment_empty_sends_nothing():
    assert send_assignment_email("hari@example.com", "hari", []) is False


def test_assignment_dedupes_same_lead_id():
    a = _lead(1)
    dup = dict(a)
    b = _lead(2)
    unique = dedupe_assignment_items([a, dup, b])
    assert [x["enquiry_number"] for x in unique] == ["ENQ-000001", "ENQ-000002"]
    subject, html = build_assignment_email("hari", [a, dup, b])
    assert "2" in subject
    assert html.count("<h3>1. Customer1") == 1
    assert "Customer2" in html


def test_assignment_keeps_distinct_leads_with_same_enquiry_text():
    """Two real leads must both appear even if enquiry labels match."""
    a = _lead(1)
    b = _lead(2)
    b["enquiry_number"] = a["enquiry_number"]
    unique = dedupe_assignment_items([a, b])
    assert len(unique) == 2
    _, html = build_assignment_email("hari", [a, b])
    assert "Customer1" in html and "Customer2" in html
    assert html.count("<h3>") == 2


def test_assignment_chunk_label_for_large_batches():
    leads = [_lead(n) for n in range(1, ASSIGNMENT_EMAIL_CHUNK + 3)]
    first = leads[:ASSIGNMENT_EMAIL_CHUNK]
    subject, html = build_assignment_email(
        "hari", first, total=len(leads), batch=1, batches=2,
    )
    assert f"{ASSIGNMENT_EMAIL_CHUNK} of {len(leads)}" in subject
    assert "part 1/2" in subject
    assert f"{ASSIGNMENT_EMAIL_CHUNK} of {len(leads)}" in html


def test_direct_call_assignment_is_urgent():
    lead = _lead(1)
    lead["source"] = "Direct Call"
    subject, html = build_assignment_email("hari", [lead])
    assert "URGENT" in subject
    assert "24 hours" in subject
    assert "24 hours" in html
    assert "3 days" not in html


def test_overdue_digest_template():
    groups = [{
        "employee": "hari",
        "leads": [{
            "enquiry_number": "ENQ-000002", "customer_name": "Anub",
            "phone": "8017185820", "assigned_date_str": "08-Sep-2026",
            "deadline_str": "10-Sep-2026 10:00",
            "days_overdue": 2, "lead_url": "http://localhost:5173/leads/xyz",
        }],
    }]
    subject, html = build_overdue_digest("11-Sep-2026", groups)
    assert "1 customer(s)" in subject
    assert "hari" in html
    assert "ENQ-000002" in html
    assert "08-Sep-2026" in html
    assert "2 day(s) overdue" in html


def test_direct_call_overdue_digest():
    groups = [{
        "employee": "hari",
        "leads": [{
            "enquiry_number": "ENQ-000009", "customer_name": "Anub",
            "phone": "8017185820", "assigned_date_str": "22-Sep-2026",
            "deadline_str": "23-Sep-2026 10:00",
            "days_overdue": 1, "source": "Direct Call",
            "lead_url": "http://localhost:5173/leads/xyz",
        }],
    }]
    subject, html = build_overdue_digest("23-Sep-2026", groups)
    assert "Direct Call not followed" in subject
    assert "24 hours" in subject
    assert "has not followed" in html
    assert "ENQ-000009" in html
