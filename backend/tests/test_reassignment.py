"""Employee reassignment request → admin accept/decline → manual assign."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import leads
from app.schemas import ReassignDecisionIn, ReassignRequestIn


def _employee(uid=None):
    return SimpleNamespace(
        id=uid or uuid4(),
        name="Emp One",
        role=SimpleNamespace(name="EMPLOYEE"),
        is_active=True,
    )


def _admin(uid=None):
    return SimpleNamespace(
        id=uid or uuid4(),
        name="Admin",
        role=SimpleNamespace(name="ADMIN"),
        is_active=True,
    )


def test_employee_can_request_reassignment():
    emp = _employee()
    lead = SimpleNamespace(
        id=uuid4(),
        enquiry_number="ENQ-1",
        customer_name="Acme",
        primary_employee_id=emp.id,
    )
    db = Mock()
    db.get.side_effect = lambda model, pk: lead if pk == lead.id else None
    body = ReassignRequestIn(reason="Customer speaks another language")

    with patch.object(leads, "_owned_lead", return_value=lead), \
         patch.object(leads, "open_reassignment_request", return_value=None), \
         patch.object(leads, "notify_admins") as notify, \
         patch.object(leads, "_serialize_reassignment", return_value={"status": "PENDING"}):
        result = leads.request_reassignment(lead.id, body, db, emp)

    assert result["ok"] is True
    assert db.add.call_count >= 2  # request + activity
    notify.assert_called_once()
    db.commit.assert_called()


def test_employee_cannot_double_request():
    emp = _employee()
    lead = SimpleNamespace(id=uuid4(), enquiry_number="ENQ-1", customer_name="Acme", primary_employee_id=emp.id)
    db = Mock()
    existing = SimpleNamespace(status="PENDING")
    with patch.object(leads, "_owned_lead", return_value=lead), \
         patch.object(leads, "open_reassignment_request", return_value=existing):
        with pytest.raises(HTTPException) as err:
            leads.request_reassignment(lead.id, ReassignRequestIn(reason="Already asked"), db, emp)
    assert err.value.status_code == 400


def test_accept_keeps_owner_unchanged():
    admin = _admin()
    owner_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), enquiry_number="ENQ-9", primary_employee_id=owner_id)
    req = SimpleNamespace(
        id=uuid4(), lead_id=lead.id, requested_by=owner_id,
        status="PENDING", reviewed_by=None, reviewed_at=None, review_note="",
    )
    db = Mock()
    db.get.side_effect = lambda model, pk: req if pk == req.id else lead if pk == lead.id else None

    result = leads.accept_reassignment(req.id, ReassignDecisionIn(note="OK"), db, admin)

    assert result["status"] == "ACCEPTED"
    assert req.status == "ACCEPTED"
    assert lead.primary_employee_id == owner_id  # unchanged
    db.commit.assert_called()


def test_decline_keeps_owner_unchanged():
    admin = _admin()
    owner_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), enquiry_number="ENQ-9", primary_employee_id=owner_id)
    req = SimpleNamespace(
        id=uuid4(), lead_id=lead.id, requested_by=owner_id,
        status="PENDING", reviewed_by=None, reviewed_at=None, review_note="",
    )
    db = Mock()
    db.get.side_effect = lambda model, pk: req if pk == req.id else lead if pk == lead.id else None

    result = leads.decline_reassignment(req.id, ReassignDecisionIn(note="Stay"), db, admin)

    assert result["status"] == "DECLINED"
    assert req.status == "DECLINED"
    assert lead.primary_employee_id == owner_id
    db.commit.assert_called()


def test_assign_blocked_without_accepted_request():
    admin = _admin()
    lead = SimpleNamespace(id=uuid4(), primary_employee_id=uuid4())
    emp = SimpleNamespace(id=uuid4(), is_active=True, role=SimpleNamespace(name="EMPLOYEE"))
    db = Mock()
    db.get.side_effect = lambda model, pk: lead if pk == lead.id else emp
    body = SimpleNamespace(employee_id=emp.id, role="PRIMARY")

    with patch.object(leads, "validate_assignee", return_value=emp), \
         patch.object(leads, "open_reassignment_request", return_value=None):
        with pytest.raises(HTTPException) as err:
            leads.assign_lead(lead.id, body, db, admin)
    assert err.value.status_code == 400
    assert "Accept" in err.value.detail
