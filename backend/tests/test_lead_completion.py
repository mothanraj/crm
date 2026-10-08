from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.api import leads
from app.schemas import StatusChange

REMINDER = date.today() + timedelta(days=3)


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
                           customer_review="A+ (Immediate)", sla_state=previous, first_contact_at=True,
                           quotation_value=None, reminder_date=REMINDER)
    user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE"))
    db = Mock()
    db.get.return_value = SimpleNamespace(name=status_name)
    body = StatusChange(new_status_id=status_id, reason="New conversation" if changed else "Called customer",
                        customer_review="A+ (Immediate)", sla_state=target, reminder_date=REMINDER)
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


@pytest.mark.parametrize("amount", ["0", "150000"])
def test_quotation_value_saved_on_lead_and_history(amount):
    status_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), status_id=status_id, employee_remarks="Old remarks",
                           customer_review="A+ (Immediate)", sla_state="PENDING", first_contact_at=True,
                           quotation_value=None, reminder_date=REMINDER)
    db = Mock()
    db.get.return_value = SimpleNamespace(name="Quotation sent")
    body = StatusChange(new_status_id=status_id, reason="Sent quotation", customer_review="A+ (Immediate)",
                        sla_state="PENDING", quotation_value=amount, reminder_date=REMINDER)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        result = leads.set_status(lead.id, body, db, SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE")))
        assert lead.quotation_value == int(amount)
        assert db.add.call_args.args[0].quotation_value == int(amount)
        assert result["activity_recorded"] is True
        db.reset_mock()
        body.sla_state = "COMPLETED"
        result = leads.set_status(lead.id, body, db, SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE")))
        assert result["activity_recorded"] is False
        db.add.assert_not_called()


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "1.234", "150000.50"])
def test_invalid_quotation_values_rejected(amount):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        StatusChange(new_status_id=uuid4(), quotation_value=amount)


def test_reminder_date_optional_but_not_in_past():
    status_id = uuid4()
    base_lead = dict(id=uuid4(), status_id=status_id, employee_remarks="Old remarks",
                     customer_review="A+ (Immediate)", sla_state="PENDING", first_contact_at=True,
                     quotation_value=None, reminder_date=REMINDER)
    db = Mock()
    db.get.return_value = SimpleNamespace(name="In Followup")
    emp = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE"))
    # Missing reminder date -> still saves (optional), stored date and flag preserved
    body = StatusChange(new_status_id=status_id, reason="Called", customer_review="A (3-6 months)")
    lead = SimpleNamespace(**base_lead)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        result = leads.set_status(lead.id, body, db, emp)
        assert result["activity_recorded"] is True
        assert lead.reminder_date == REMINDER
        assert result["reminder_date"] == REMINDER.isoformat()
        assert db.add.call_args.args[0].reminder_date is None
    # Past reminder date -> 400
    body = StatusChange(new_status_id=status_id, reason="Called", customer_review="A (3-6 months)",
                        reminder_date=date.today() - timedelta(days=1))
    with patch.object(leads, "_owned_lead", return_value=SimpleNamespace(**base_lead)), patch.object(leads, "change_status"):
        with pytest.raises(leads.HTTPException, match="cannot be in the past") as error:
            leads.set_status(base_lead["id"], body, db, emp)
        assert error.value.status_code == 400
    # Valid date stored on lead and activity
    body = StatusChange(new_status_id=status_id, reason="Called", customer_review="A (3-6 months)",
                        reminder_date=REMINDER)
    lead = SimpleNamespace(**base_lead)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        result = leads.set_status(lead.id, body, db, emp)
        assert lead.reminder_date == REMINDER
        assert db.add.call_args.args[0].reminder_date == REMINDER
        assert result["reminder_date"] == REMINDER.isoformat()


def test_reminder_done_flags():
    from app.schemas import LeadUpdate, ReminderDoneIn
    emp = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE"))
    db = Mock()
    # New different date resets a struck flag; same date keeps it
    lead = SimpleNamespace(id=uuid4(), status_id=uuid4(), employee_remarks="R",
                           customer_review="A+ (Immediate)", sla_state="PENDING",
                           first_contact_at=True, quotation_value=None,
                           reminder_date=REMINDER, reminder_done=True)
    db.get.return_value = SimpleNamespace(name="In Followup")
    other = REMINDER + timedelta(days=1)
    body = StatusChange(new_status_id=lead.status_id, reason="R", customer_review="A+ (Immediate)",
                        reminder_date=other)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        leads.set_status(lead.id, body, db, emp)
        assert lead.reminder_date == other
        assert lead.reminder_done is False
    lead = SimpleNamespace(id=uuid4(), status_id=uuid4(), employee_remarks="R",
                           customer_review="A+ (Immediate)", sla_state="PENDING",
                           first_contact_at=True, quotation_value=None,
                           reminder_date=REMINDER, reminder_done=True)
    body = StatusChange(new_status_id=lead.status_id, reason="R", customer_review="A+ (Immediate)",
                        reminder_date=REMINDER)
    with patch.object(leads, "_owned_lead", return_value=lead), patch.object(leads, "change_status"):
        leads.set_status(lead.id, body, db, emp)
        assert lead.reminder_done is True
    # Lead-level toggle via PUT
    lead = SimpleNamespace(id=uuid4(), reminder_date=REMINDER, reminder_done=False, lead_value=1)
    with patch.object(leads, "_owned_lead", return_value=lead), \
         patch.object(leads, "_serialize", return_value={"reminder_done": True}):
        leads.update_lead(lead.id, LeadUpdate(reminder_done=True), db, emp)
        assert lead.reminder_done is True
    # Per-entry toggle
    act = SimpleNamespace(id=uuid4(), lead_id=uuid4(), reminder_done=False)
    lead2 = SimpleNamespace(id=act.lead_id, status_id=uuid4(), sla_state="PENDING")
    db.get.side_effect = [act, SimpleNamespace(name="In Followup")]
    with patch.object(leads, "_owned_lead", return_value=lead2):
        result = leads.set_activity_reminder_done(act.lead_id, act.id, ReminderDoneIn(done=True), db, emp)
        assert act.reminder_done is True
        assert result["reminder_done"] is True


def test_put_clears_or_sets_reminder_date():
    from app.schemas import LeadUpdate
    emp = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="EMPLOYEE"))
    # Clear via explicit null
    lead = SimpleNamespace(id=uuid4(), reminder_date=REMINDER, lead_value=1)
    db = Mock()
    with patch.object(leads, "_owned_lead", return_value=lead), \
         patch.object(leads, "_serialize", return_value={"reminder_date": None}):
        result = leads.update_lead(lead.id, LeadUpdate(reminder_date=None), db, emp)
        assert lead.reminder_date is None
        assert result["reminder_date"] is None
    # Set a future date
    lead = SimpleNamespace(id=uuid4(), reminder_date=None, lead_value=1)
    with patch.object(leads, "_owned_lead", return_value=lead), \
         patch.object(leads, "_serialize", return_value={"reminder_date": REMINDER.isoformat()}):
        result = leads.update_lead(lead.id, LeadUpdate(reminder_date=REMINDER), db, emp)
        assert lead.reminder_date == REMINDER
        assert result["reminder_date"] == REMINDER.isoformat()
    # Past date rejected
    lead = SimpleNamespace(id=uuid4(), reminder_date=None, lead_value=1)
    with patch.object(leads, "_owned_lead", return_value=lead):
        with pytest.raises(leads.HTTPException, match="cannot be in the past") as error:
            leads.update_lead(lead.id, LeadUpdate(reminder_date=date.today() - timedelta(days=1)), db, emp)
        assert error.value.status_code == 400
