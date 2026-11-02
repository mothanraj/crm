from datetime import datetime
from unittest.mock import Mock, patch

from app.api.dashboard import _converted_amounts, _dashboard_history_payload


def _fake_db(activity_rows, history_rows):
    activity_q = Mock()
    activity_q.filter.return_value.all.return_value = activity_rows
    history_q = Mock()
    history_q.join.return_value.filter.return_value.all.return_value = history_rows
    db = Mock()
    db.query.side_effect = [activity_q, history_q]
    return db


def test_direct_conversion_ignores_quotation_saved_after_conversion():
    db = _fake_db(
        [
            ("lead", "Work Progress", "Converted", datetime(2026, 10, 22, 12, 24)),
            ("lead", "Quotation Form", "R0", datetime(2026, 10, 22, 12, 25)),
        ],
        [],
    )

    assert _converted_amounts(db, [("lead", 450_000, 354_000)]) == {"lead": 450_000}


def test_conversion_after_quotation_uses_quotation_value():
    db = _fake_db(
        [
            ("lead", "Quotation Form", "R0", datetime(2026, 10, 22, 10, 0)),
            ("lead", "Work Progress", "Converted", datetime(2026, 10, 22, 12, 0)),
        ],
        [],
    )

    assert _converted_amounts(db, [("lead", 450_000, 354_000)]) == {"lead": 354_000}


def test_quotation_sent_status_history_before_conversion_counts():
    db = _fake_db(
        [],
        [
            ("lead", "Quotation sent", datetime(2026, 10, 22, 10, 0)),
            ("lead", "Converted", datetime(2026, 10, 22, 12, 0)),
        ],
    )

    assert _converted_amounts(db, [("lead", 450_000, 354_000)]) == {"lead": 354_000}


def test_zero_quotation_before_conversion_stays_zero():
    db = _fake_db(
        [
            ("lead", "Quotation Form", "R0", datetime(2026, 10, 22, 10, 0)),
            ("lead", "Work Progress", "Converted", datetime(2026, 10, 22, 12, 0)),
        ],
        [],
    )

    assert _converted_amounts(db, [("lead", 450_000, 0)]) == {"lead": 0}


def test_legacy_lead_without_events_uses_quotation_presence():
    db = _fake_db([], [])

    assert _converted_amounts(db, [("quoted", 450_000, 354_000), ("direct", 250_000, None)]) == {
        "quoted": 354_000,
        "direct": 250_000,
    }


def test_missing_values_are_zero():
    db = _fake_db([], [])

    assert _converted_amounts(db, [("lead", None, None)]) == {"lead": 0}


def test_dashboard_history_mixes_quote_and_direct_conversions():
    db = Mock()
    rows = [
        ("quoted", 250_000, 1, None, "Google Ads", "Puzzle Parking System", "Converted", None, 310_000),
        ("direct", 180_000, 1, None, None, None, "Converted", None, None),
    ]
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.all.return_value = rows

    with patch("app.api.dashboard._history_events_by_lead", return_value={}), patch(
        "app.api.dashboard._converted_amounts",
        return_value={"quoted": 310_000, "direct": 180_000},
    ):
        payload = _dashboard_history_payload(db, None, None, "custom")

    assert payload["tiles"]["converted"] == 2
    assert payload["tiles"]["converted_lead_value"] == 490_000
