from app.services.email_service import (
    build_assignment_email,
    build_overdue_digest,
    send_assignment_email,
)


def _lead(n: int) -> dict:
    return {
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
