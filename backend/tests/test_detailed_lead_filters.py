"""Lead-page filters on the Detailed Lead Report (table, Excel export and PDF)."""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dashboard import (
    _detailed_filter_labels,
    _detailed_lead_filters,
    _detailed_leads_payload,
    _escape_like,
)


def _query_chain(db: Mock):
    """db.query(...).outerjoin() x4 .filter() .order_by() .all()"""
    chain = db.query.return_value
    for _ in range(4):
        chain = chain.outerjoin.return_value
    chain.filter.return_value.order_by.return_value.all.return_value = []
    return chain


def _mock_db():
    db = Mock()
    _query_chain(db)
    # Name lookups used for the applied-filter summary.
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_filter_defaults_are_empty():
    filters = _detailed_lead_filters()
    assert filters == {
        "search": "",
        "status": None,
        "source": None,
        "customer_review": "",
        "sla": "",
        "starred": False,
        "sort": "",
    }


def test_filter_values_are_cleaned():
    status, source = uuid4(), uuid4()
    filters = _detailed_lead_filters(
        search="  ravi  ", status=str(status), source=str(source),
        customer_review="B (6-9 months)", sla="COMPLETED", starred="1", sort="lead_value_desc",
    )
    assert filters["search"] == "ravi"
    assert filters["status"] == status
    assert filters["source"] == source
    assert filters["customer_review"] == "B (6-9 months)"
    assert filters["sla"] == "COMPLETED"
    assert filters["starred"] is True
    assert filters["sort"] == "lead_value_desc"


def test_invalid_sla_and_ids_rejected():
    with pytest.raises(HTTPException) as exc:
        _detailed_lead_filters(sla="WHATEVER")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _detailed_lead_filters(status="not-a-uuid")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _detailed_lead_filters(source="not-a-uuid")
    assert exc.value.status_code == 400


def test_payload_without_lead_filters_only_scopes_by_date():
    db = _mock_db()
    payload = _detailed_leads_payload(db, date(2026, 1, 1), date(2026, 1, 31), None, None, "month")
    chain = _query_chain(db)
    # is_active + enquiry_date >= start + enquiry_date <= end
    assert len(chain.filter.call_args[0]) == 3
    assert payload["filters"] == {}
    assert payload["count"] == 0
    assert "enquiry_date" in str(chain.filter.return_value.order_by.call_args[0][0])


def test_payload_applies_every_lead_filter_and_labels_them():
    db = _mock_db()
    status_id, source_id = uuid4(), uuid4()
    lead_filters = {
        "search": "ravi",
        "status": status_id,
        "source": source_id,
        "customer_review": "B (6-9 months)",
        "sla": "COMPLETED",
        "starred": True,
        "sort": "lead_value_desc",
    }
    payload = _detailed_leads_payload(
        db, date(2026, 1, 1), date(2026, 1, 31), None, None, "month", lead_filters,
    )
    chain = _query_chain(db)
    # is_active + 2 dates + search + status + source + category + sla + starred
    assert len(chain.filter.call_args[0]) == 9
    assert "lead_value" in str(chain.filter.return_value.order_by.call_args[0][0])
    assert payload["filters"] == {
        "search": "ravi",
        "status": str(status_id),
        "source": str(source_id),
        "category": "B (6-9 months)",
        "lead_status": "Completed",
        "starred": "Starred only",
        "sort": "Lead value: high to low",
    }


def test_not_interested_sla_filters_by_status_names():
    db = _mock_db()
    _detailed_leads_payload(db, None, None, None, None, "month", {"sla": "NOT_INTERESTED"})
    chain = _query_chain(db)
    criteria = chain.filter.call_args[0]
    assert len(criteria) == 2  # is_active + Not Interested statuses
    sql = str(criteria[-1].compile(compile_kwargs={"literal_binds": True}))
    assert "Not Interested" in sql and "Not Interested/Spam" in sql


def test_filter_labels_resolve_names():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = ("In Followup",)
    labels = _detailed_filter_labels(db, {"status": uuid4(), "search": " ", "sla": "NOT_INTERESTED"})
    assert labels == {"status": "In Followup", "lead_status": "Not Interested"}


def test_escape_like_escapes_wildcards():
    assert _escape_like("100%_off\\") == "100\\%\\_off\\\\"
