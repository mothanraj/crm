from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.api import leads
from app.schemas import StatusChange


@pytest.mark.parametrize("status_name", ["In Followup", "Converted", "Not Interested"])
@pytest.mark.parametrize("previous,target,changed,recorded", [
    ("PENDING", "COMPLETED", False, False),
    ("COMPLETED", "COMPLETED", False, False),
    ("COMPLETED", "PENDING", False, False),
    ("PENDING", "COMPLETED", True, True),
    ("PENDING", "PENDING", False, True),
])
def test_completion_preserves_history_but_new_work_is_recorded(status_name, previous, target, changed, recorded):
    status_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), status_id=status_id, employee_remarks="Called customer",
                           customer_review="A+ (Immediate)", sla_state=previous, first_contact_at=True)
    user = SimpleNamespace(id=uuid4())
    db = Mock()
    db.get.return_value = SimpleNamespace(name=status_name)
    body = StatusChange(new_status_id=status_id, reason="New conversation" if changed else "Called customer",
                        customer_review="A+ (Immediate)", sla_state=target)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        result = leads.set_status(lead.id, body, db, user)
    assert result["activity_recorded"] is recorded
    assert result["sla_state"] == target
    assert db.add.call_count == int(recorded)
    db.commit.assert_called_once()


@pytest.mark.parametrize("status_name,state,role,locked", [
    ("Converted", "COMPLETED", "EMPLOYEE", True),
    ("Converted", "PENDING", "EMPLOYEE", False),
    ("Not Interested", "COMPLETED", "EMPLOYEE", False),
    ("In Followup", "COMPLETED", "EMPLOYEE", False),
    ("Converted", "COMPLETED", "ADMIN", False),
])
def test_converted_completion_locks_employee_mutations(status_name, state, role, locked):
    user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name=role))
    lead = SimpleNamespace(id=uuid4(), primary_employee_id=user.id, status_id=uuid4(), sla_state=state)
    db = Mock()
    db.get.side_effect = [lead, SimpleNamespace(name=status_name)]
    if locked:
        with pytest.raises(leads.HTTPException, match="cannot be edited or reopened") as error:
            leads._owned_lead(db, lead.id, user)
        assert error.value.status_code == 403
    else:
        assert leads._owned_lead(db, lead.id, user) is lead


@pytest.mark.parametrize("amount", ["0", "150000.50"])
def test_quotation_value_saved_on_lead_and_history(amount):
    from decimal import Decimal
    status_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), status_id=status_id, employee_remarks="Old remarks",
                           customer_review="A+ (Immediate)", sla_state="PENDING", first_contact_at=True,
                           quotation_value=None)
    db = Mock()
    db.get.return_value = SimpleNamespace(name="Quotation sent")
    body = StatusChange(new_status_id=status_id, reason="Sent quotation", customer_review="A+ (Immediate)",
                        sla_state="PENDING", quotation_value=amount)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        result = leads.set_status(lead.id, body, db, SimpleNamespace(id=uuid4()))
        assert lead.quotation_value == Decimal(amount)
        assert db.add.call_args.args[0].quotation_value == Decimal(amount)
        assert result["activity_recorded"] is True
        db.reset_mock()
        body.sla_state = "COMPLETED"
        result = leads.set_status(lead.id, body, db, SimpleNamespace(id=uuid4()))
        assert result["activity_recorded"] is False
        db.add.assert_not_called()


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "1.234"])
def test_invalid_quotation_values_rejected(amount):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        StatusChange(new_status_id=uuid4(), quotation_value=amount)
