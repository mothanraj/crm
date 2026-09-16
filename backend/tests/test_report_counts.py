from unittest.mock import Mock, patch

from app.api.dashboard import _by_source_matrix, _source_details_payload, _product_details_payload
from app.services.normalize import CANONICAL_SOURCES


def test_sources_include_zeros_and_merge_alias_counts():
    db = Mock()
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.all.return_value = [
        ("meta", "In Followup", 2), ("Facebook/Instagram", "In Followup", 3),
        (None, None, 1),
    ]
    matrix = _by_source_matrix(db)
    assert list(matrix) == CANONICAL_SOURCES
    assert matrix["Facebook/Instagram"] == {"total": 5, "In Followup": 5}
    assert matrix["Others"]["total"] == 1
    assert matrix["Google Ads"]["total"] == 0
    with patch("app.api.dashboard._by_source_matrix", return_value=matrix), patch("app.api.dashboard._quote_sums_by_source", return_value={}):
        report = _source_details_payload(db, None, None, "custom")
    assert report["totals"]["total"] == 6
    google = next(row for row in report["rows"] if row["source"] == "Google Ads")
    assert all(value == 0 for key, value in google.items() if key != "source")


def test_product_details_count_unmapped_and_missing_status():
    db = Mock()
    db.query.return_value.select_from.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.all.return_value = [
        (None, None, 2), ("Puzzle Parking System", "Meeting", 3),
    ]
    report = _product_details_payload(db, None, None, "custom")
    assert report["totals"]["total"] == 5
    assert report["totals"]["meeting"] == 3
    assert next(row for row in report["rows"] if row["product"] == "Unmapped")["total"] == 2
