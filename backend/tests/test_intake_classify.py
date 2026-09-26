"""Unit tests for shared Excel + Sheets intake classification."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.importer import classify_intake_row


def _db(phones=(), enqs=()):
    db = MagicMock()

    def filter_by(**kwargs):
        q = MagicMock()
        if "contact_number_norm" in kwargs:
            q.first.return_value = SimpleNamespace() if kwargs["contact_number_norm"] in phones else None
        elif "legacy_enquiry_no" in kwargs:
            q.first.return_value = SimpleNamespace() if kwargs["legacy_enquiry_no"] in enqs else None
        elif "enquiry_number" in kwargs:
            q.first.return_value = SimpleNamespace() if kwargs["enquiry_number"] in enqs else None
        else:
            q.first.return_value = None
        return q

    db.query.return_value.filter_by.side_effect = filter_by
    return db


def test_ok_row():
    out = classify_intake_row(_db(), name="A", phone="9840098400", enq=10, email="a@x.com")
    assert out["reason"] == "OK"
    assert out["dups"] == []
    assert out["errs"] == []


def test_duplicate_phone_in_db():
    out = classify_intake_row(_db(phones={"9840098400"}), name="A", phone="9840098400", enq=10, email="")
    assert out["reason"] == "DUPLICATE"
    assert "duplicate phone" in out["dups"]


def test_duplicate_enq_in_batch():
    out = classify_intake_row(_db(), name="A", phone="9840098400", enq=10, email="", seen_enqs={10})
    assert out["reason"] == "DUPLICATE"
    assert "duplicate enquiry no" in out["dups"][0]


def test_same_upload_rejects_second_copy_of_enquiry():
    seen: set[int] = set()
    first = classify_intake_row(_db(), name="A", phone="9840098400", enq="ENQ-000225", email="", seen_enqs=seen)
    assert first["reason"] == "OK"
    assert first["legacy_enq"] == 225
    seen.add(first["legacy_enq"])
    second = classify_intake_row(_db(), name="B", phone="9840098401", enq=225, email="", seen_enqs=seen)
    third = classify_intake_row(_db(), name="C", phone="9840098402", enq="ENQ-225", email="", seen_enqs=seen)
    other = classify_intake_row(_db(), name="D", phone="9840098403", enq=226, email="", seen_enqs=seen)
    assert second["reason"] == "DUPLICATE"
    assert "ENQ-000225" in second["dups"][0]
    assert third["reason"] == "DUPLICATE"
    assert other["reason"] == "OK"
    assert other["legacy_enq"] == 226


def test_force_add_cannot_reuse_enquiry_number():
    from uuid import uuid4
    from fastapi import HTTPException
    from app.api.importer import _create_lead_from_raw

    db = _db(enqs={225, "ENQ-000225"})
    try:
        _create_lead_from_raw(
            db,
            {"name": "A", "phone": "9840098400", "enq": "ENQ-225"},
            SimpleNamespace(id=uuid4()),
            force=True,
        )
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 400
        assert "ENQ-000225" in exc.detail
    assert raised


def test_phone_alone_is_enough():
    out = classify_intake_row(_db(), name="", phone="9840098400", enq="", email="not-an-email")
    assert out["reason"] == "OK"
    assert out["legacy_enq"] is None
    assert out["errs"] == []


def test_invalid_missing_name_phone_enq_email():
    out = classify_intake_row(_db(), name="", phone="123", enq="", email="bad")
    assert out["reason"] == "INVALID"
    assert out["errs"] == ["missing/invalid phone (123)"]


def test_email_alone_is_enough():
    out = classify_intake_row(_db(), name="", phone="", enq="", email="lead@example.com")
    assert out["reason"] == "OK"
    assert out["phone_norm"] == ""
    assert out["errs"] == []


def test_invalid_phone_is_rejected_even_with_email():
    out = classify_intake_row(_db(), name="", phone="123", enq="", email="lead@example.com")
    assert out["reason"] == "INVALID"
    assert out["errs"] == ["missing/invalid phone (123)"]


def test_duplicate_wins_over_invalid():
    out = classify_intake_row(_db(phones={"9840098400"}), name="", phone="9840098400", enq="", email="")
    assert out["reason"] == "DUPLICATE"
    assert out["dups"]
    assert out["errs"] == []
