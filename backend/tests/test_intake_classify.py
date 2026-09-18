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
    assert "duplicate enquiry no" in out["dups"]


def test_invalid_missing_name_phone_enq_email():
    out = classify_intake_row(_db(), name="", phone="123", enq="", email="bad")
    assert out["reason"] == "INVALID"
    assert "missing name" in out["errs"]
    assert "missing/invalid phone" in out["errs"]
    assert "missing/invalid enquiry no" in out["errs"]
    assert "invalid email" in out["errs"]


def test_duplicate_wins_over_invalid():
    out = classify_intake_row(_db(phones={"9840098400"}), name="", phone="9840098400", enq=10, email="")
    assert out["reason"] == "DUPLICATE"
    assert out["dups"]
    assert out["errs"]  # still recorded, but reason prefers duplicate
