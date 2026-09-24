from app.api.importer import header_score, parse_legacy_enq, suggest_sheet


def test_parse_legacy_enq_float():
    assert parse_legacy_enq(1.0) == 1
    assert parse_legacy_enq(76.0) == 76
    assert parse_legacy_enq(5) == 5
    assert parse_legacy_enq("449") == 449
    assert parse_legacy_enq("ENQ-000001") == 1
    assert parse_legacy_enq("ENQ-225") == 225
    assert parse_legacy_enq("ENQ-000225") == 225
    assert parse_legacy_enq(None) is None
    assert parse_legacy_enq("") is None
    assert parse_legacy_enq("abc") is None
    assert parse_legacy_enq(0) is None


def test_enquiry_number_normalization():
    from app.services.lead_service import format_enquiry_number
    assert format_enquiry_number(parse_legacy_enq(1)) == "ENQ-000001"
    assert format_enquiry_number(parse_legacy_enq(225)) == "ENQ-000225"
    assert format_enquiry_number(parse_legacy_enq("ENQ-225")) == "ENQ-000225"
    assert format_enquiry_number(parse_legacy_enq("ENQ-000225")) == "ENQ-000225"


def test_header_score_tracker():
    hdr = [" Enq no", "Date Received", "Lead Name / Full Name", "Company / Organisation",
           "Contact No.", "City", "No. of Cars", "x", "x", "x", "x", "x", "x", "Staus",
           "x", "x", "Lead Source", "x", "x", "Product / Type"]
    assert header_score(hdr) >= 3


def test_header_score_dashboard_rejected():
    assert header_score(["LEADS FUNNEL - LIVE DASHBOARD", "", "Total Leads"]) < 3


def test_suggest_sheet_prefers_tracker():
    names = ["Dashboard (1)", "Leads Tracker (1)", "meta leads"]
    assert suggest_sheet(names) == "Leads Tracker (1)"
