from types import SimpleNamespace

import pytest

from app.models import EnquirySequence, Lead
from app.services import lead_service


class FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def with_for_update(self):
        return self

    def first(self):
        rows = self.db.store.get(self.model, [])
        return rows[0] if rows else None

    def all(self):
        if self.model is EnquirySequence:
            return list(self.db.store.get(self.model, []))
        if self.model is Lead:
            return list(self.db.store.get(self.model, []))
        # Lead.enquiry_number column query -> return list of 1-tuples
        return list(self.db.store.get("enquiry_numbers", []))

    def count(self):
        return len(self.db.store.get(self.model, []))


class FakeDB:
    def __init__(self, seqs=None, enquiry_numbers=()):
        self.store = {
            EnquirySequence: list(seqs or []),
            Lead: [SimpleNamespace(enquiry_number=n) for n in enquiry_numbers],
            "enquiry_numbers": [(n,) for n in enquiry_numbers],
        }
        self.added = []
        self.deleted = []

    def query(self, *args):
        # db.query(Lead.enquiry_number) comes through as an InstrumentedAttribute,
        # not the Lead class itself — route it to the tuple store.
        if len(args) == 1 and args[0] is not EnquirySequence and args[0] is not Lead:
            return FakeQuery(self, "enquiry_numbers")
        return FakeQuery(self, args[0])

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, EnquirySequence):
            self.store.setdefault(EnquirySequence, []).append(obj)

    def delete(self, obj):
        self.deleted.append(obj)
        rows = self.store.get(EnquirySequence, [])
        if obj in rows:
            rows.remove(obj)

    def flush(self):
        pass


def test_parse_enquiry_suffix():
    assert lead_service.parse_enquiry_suffix("ENQ-000001") == 1
    assert lead_service.parse_enquiry_suffix("ENQ-225") == 225
    assert lead_service.parse_enquiry_suffix("42") == 42
    assert lead_service.parse_enquiry_suffix(None) is None
    assert lead_service.parse_enquiry_suffix("") is None
    assert lead_service.parse_enquiry_suffix("abc") is None


def test_reset_to_zero_on_empty_db():
    db = FakeDB(seqs=[EnquirySequence(last_number=57)])
    result = lead_service.reset_enquiry_sequence(db, 0)
    assert result["last_number"] == 0
    assert result["next_enquiry"] == "ENQ-000001"
    assert db.store[EnquirySequence][0].last_number == 0


def test_reset_creates_row_when_missing():
    db = FakeDB(seqs=[])
    result = lead_service.reset_enquiry_sequence(db, 0)
    assert result["last_number"] == 0
    assert len(db.store[EnquirySequence]) == 1


def test_reset_blocked_below_max_without_force():
    db = FakeDB(
        seqs=[EnquirySequence(last_number=10)],
        enquiry_numbers=("ENQ-000005", "ENQ-000010"),
    )
    with pytest.raises(ValueError, match="existing max"):
        lead_service.reset_enquiry_sequence(db, 0)
    # counter untouched
    assert db.store[EnquirySequence][0].last_number == 10


def test_reset_below_max_allowed_with_force():
    db = FakeDB(
        seqs=[EnquirySequence(last_number=10)],
        enquiry_numbers=("ENQ-000005", "ENQ-000010"),
    )
    result = lead_service.reset_enquiry_sequence(db, 0, force=True)
    assert result["last_number"] == 0
    assert result["next_enquiry"] == "ENQ-000001"


def test_reset_at_or_above_max_allowed():
    db = FakeDB(
        seqs=[EnquirySequence(last_number=3)],
        enquiry_numbers=("ENQ-000005",),
    )
    result = lead_service.reset_enquiry_sequence(db, 5)
    assert result["next_enquiry"] == "ENQ-000006"


def test_reset_collapses_duplicate_rows():
    keep = EnquirySequence(last_number=9)
    extra = EnquirySequence(last_number=4)
    db = FakeDB(seqs=[keep, extra])
    lead_service.reset_enquiry_sequence(db, 0)
    assert db.store[EnquirySequence] == [keep]
    assert extra in db.deleted


def test_reset_rejects_negative():
    db = FakeDB(seqs=[EnquirySequence(last_number=1)])
    with pytest.raises(ValueError, match=">= 0"):
        lead_service.reset_enquiry_sequence(db, -1)


def test_info_reports_next_and_max():
    db = FakeDB(
        seqs=[EnquirySequence(last_number=7)],
        enquiry_numbers=("ENQ-000002", "ENQ-000007"),
    )
    info = lead_service.enquiry_sequence_info(db)
    assert info["last_number"] == 7
    assert info["next_enquiry"] == "ENQ-000008"
    assert info["leads_count"] == 2
    assert info["max_number"] == 7
