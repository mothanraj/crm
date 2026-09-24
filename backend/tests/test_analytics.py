from datetime import date

from app.models import LeadSource, Product, User
from app.services.analytics import LeadFilters, build_summary, percent_change, query_rows


def test_percent_change_normal():
    assert percent_change(15, 10) == 50.0
    assert percent_change(8, 10) == -20.0


def test_percent_change_zero_baseline_is_not_a_number():
    assert percent_change(5, 0) is None
    assert percent_change(0, 0) is None
    assert percent_change(5, None) is None


def test_percent_change_treats_missing_current_as_zero_when_baseline_exists():
    assert percent_change(None, 10) == -100.0


def _assert_current_balance(summary: dict):
    total = summary["kpi"]["leads"]
    for key in ("by_source", "by_product", "by_employee", "by_city", "by_category", "by_progress"):
        assert sum(row["leads"] for row in summary[key]) == total, key
    assert sum(row["leads"] for row in summary["by_month"]) + summary["kpi"]["undated"] == total
    assert sum(row["lead_value"] for row in summary["by_source"]) == summary["kpi"]["lead_value"]
    assert sum(row["quotation_value"] for row in summary["by_source"]) == summary["kpi"]["quotation_value"]
    assert summary["kpi"]["leads_with_quote"] + summary["kpi"]["leads_without_quote"] == total
    assert summary["kpi"]["zero_quotes"] <= summary["kpi"]["leads_with_quote"]
    for key, value in summary["kpi"].items():
        assert value != float("inf")
        assert value == value if isinstance(value, float) else True


def test_live_filters_keep_one_lead_per_total():
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        bare = LeadFilters()
        summary = build_summary(
            db, bare, compare_years=(2025, 2026),
            period_a=(date(2025, 1, 1), date(2025, 3, 31)),
            period_b=(date(2026, 1, 1), date(2026, 3, 31)),
        )
        _assert_current_balance(summary)
        assert summary["year_compare"]["left_year"] == 2025
        assert summary["year_compare"]["right_year"] == 2026
        assert len(summary["year_compare"]["months"]) == 12
        if summary["year_compare"]["totals"]["left"]["leads"] == 0:
            assert summary["year_compare"]["totals"]["pct_change"]["leads"] is None

        only_2025 = build_summary(db, LeadFilters(years=[2025]))
        _assert_current_balance(only_2025)
        assert all(row["year"] == 2025 for row in only_2025["by_year"])

        only_2026 = build_summary(db, LeadFilters(years=[2026]))
        _assert_current_balance(only_2026)
        assert only_2025["kpi"]["leads"] + only_2026["kpi"]["leads"] <= summary["kpi"]["leads"]

        january = build_summary(db, LeadFilters(months=[1]))
        december = build_summary(db, LeadFilters(months=[12]))
        _assert_current_balance(january)
        _assert_current_balance(december)
        assert sum(row["leads"] for row in january["by_month"] if row["month"] != 1) == 0
        assert sum(row["leads"] for row in december["by_month"] if row["month"] != 12) == 0

        for category in ("A+ (Immediate)", "A (3-6 months)", "B (1 year)", "C (Planning Stage)"):
            scoped = build_summary(db, LeadFilters(categories=[category]))
            _assert_current_balance(scoped)
            assert scoped["kpi"]["leads"] <= summary["kpi"]["leads"]
            assert sum(row["leads"] for row in scoped["by_category"] if row["name"] != category) == 0

        for progress in ("In Followup", "Not Interested", "Meeting", "Site Visit", "Converted", "Quotation sent"):
            scoped = build_summary(db, LeadFilters(progress=[progress]))
            _assert_current_balance(scoped)
            assert sum(row["leads"] for row in scoped["by_progress"] if row["name"] != progress) == 0

        combined = build_summary(db, LeadFilters(years=[2026], months=[7], categories=["A+ (Immediate)"]))
        _assert_current_balance(combined)
        assert combined["kpi"]["leads"] <= only_2026["kpi"]["leads"]

        valued = build_summary(db, LeadFilters(lead_min=0, lead_max=100000))
        quoted = build_summary(db, LeadFilters(quote_min=0, quote_max=100000))
        _assert_current_balance(valued)
        _assert_current_balance(quoted)
        assert valued["kpi"]["leads"] == valued["kpi"]["leads_with_value"]
        assert quoted["kpi"]["leads_without_quote"] == 0

        empty = build_summary(db, LeadFilters(customer="___no_such_customer___"))
        assert empty["kpi"]["leads"] == 0
        assert query_rows(db, LeadFilters(customer="___no_such_customer___"), page=1, page_size=25, sort="date", direction="desc")["total"] == 0

        historical = build_summary(db, LeadFilters(view="historical"))
        assert historical["kpi"]["leads"] == summary["kpi"]["leads"]
        page = query_rows(db, bare, page=1, page_size=10, sort="lead_value", direction="desc")
        assert page["total"] == summary["kpi"]["leads"]
        assert len(page["rows"]) <= 10

        city = next((row for row in summary["by_city"] if row["leads"] and row["name"] != "Unspecified"), None)
        if city:
            scoped = build_summary(db, LeadFilters(cities=[city["name"]]))
            _assert_current_balance(scoped)
            assert scoped["kpi"]["leads"] == city["leads"]

        source = next((row for row in summary["by_source"] if row["leads"] and row["name"] != "Unspecified"), None)
        if source:
            src = db.query(LeadSource).filter(LeadSource.name == source["name"]).one()
            scoped = build_summary(db, LeadFilters(source_ids=[src.id]))
            _assert_current_balance(scoped)
            assert scoped["kpi"]["leads"] == source["leads"]

        product = next((row for row in summary["by_product"] if row["leads"] and row["name"] != "Unmapped"), None)
        if product:
            prod = db.query(Product).filter(Product.name == product["name"]).first()
            if prod:
                scoped = build_summary(db, LeadFilters(product_ids=[prod.id]))
                _assert_current_balance(scoped)
                assert scoped["kpi"]["leads"] == product["leads"]

        staff = [row for row in summary["by_employee"] if row["leads"] and row["name"] != "Unassigned"][:2]
        if staff:
            matched = []
            for row in staff:
                users = db.query(User).filter(User.name == row["name"]).all()
                if len(users) == 1:
                    matched.append((users[0].id, row["leads"]))
            if matched:
                scoped = build_summary(db, LeadFilters(employee_ids=[item[0] for item in matched]))
                _assert_current_balance(scoped)
                assert scoped["kpi"]["leads"] == sum(item[1] for item in matched)
                narrowed = build_summary(db, LeadFilters(employee_ids=[matched[0][0]], categories=["A+ (Immediate)"]))
                _assert_current_balance(narrowed)
                assert narrowed["kpi"]["leads"] <= scoped["kpi"]["leads"]
    finally:
        db.close()


def test_period_label_for_month_groups():
    from app.services.analytics import _period_label

    assert _period_label([1, 2, 3]) == "Jan–Mar"
    assert _period_label([1]) == "Jan"
    assert _period_label([1, 3, 8]) == "Selected total"
    assert _period_label(list(range(1, 13))) == "Total"


def test_comparison_counts_each_lead_once():
    from app.db.session import SessionLocal
    from app.services.analytics import build_comparison

    db = SessionLocal()
    try:
        years = [2024, 2025, 2026]
        months = [1, 2, 3]
        scoped = LeadFilters(years=years, months=months)
        leads = build_comparison(db, scoped, "lead_value", "leads")
        summary = build_summary(db, scoped)
        assert leads["years"] == years
        assert [row["month"] for row in leads["months"]] == months
        assert leads["period_label"] == "Jan–Mar"
        assert leads["measure"] == "leads"
        for year in years:
            key = str(year)
            assert sum(row["values"][key] for row in leads["months"]) == leads["selected_total"][key]
        assert sum(leads["selected_total"].values()) == summary["kpi"]["leads"]

        money = build_comparison(db, scoped, "lead_value", "lead_value")
        assert money["money"] is True
        assert sum(money["selected_total"].values()) == summary["kpi"]["lead_value"]

        quotations = build_comparison(db, scoped, "quotation_value", "quotations")
        assert quotations["measure"] == "quotations"
        assert sum(quotations["selected_total"].values()) == summary["kpi"]["leads_with_quote"]

        quote_value = build_comparison(db, scoped, "quotation_value", "quotation_value")
        assert sum(quote_value["selected_total"].values()) == summary["kpi"]["quotation_value"]
        assert build_comparison(db, scoped, "progress", "lead_value")["measure"] == "leads"

        for kind in ("progress", "category", "product", "cars"):
            detail = build_comparison(db, scoped, kind, "leads")
            assert detail["details"]
            for year in years:
                assert sum(row["values"][str(year)] for row in detail["details"]) == leads["selected_total"][str(year)]

        odd = build_comparison(db, LeadFilters(years=[2025, 2026], months=[1, 3, 8]), "lead_value", "leads")
        assert [row["month"] for row in odd["months"]] == [1, 3, 8]
        assert odd["period_label"] == "Selected total"
        assert odd["years"] == [2025, 2026]

        single = build_comparison(db, LeadFilters(years=[2025], months=[1]), "category", "leads")
        assert single["years"] == [2025]
        assert [row["month"] for row in single["months"]] == [1]

        empty_year = build_comparison(db, LeadFilters(years=[1999], months=[1, 2, 3]), "product", "leads")
        assert empty_year["years"] == [1999]
        assert empty_year["selected_total"]["1999"] == 0
        assert all(row["values"]["1999"] == 0 for row in empty_year["details"])

        ranged = build_comparison(
            db,
            LeadFilters(years=[2024, 2025], from_date=date(2025, 1, 1), to_date=date(2025, 3, 31)),
            "lead_value",
            "leads",
        )
        assert ranged["years"] == [2024, 2025]
        assert all(row["values"]["2024"] == 0 for row in ranged["months"])
        april = next(row for row in ranged["months"] if row["month"] == 4)
        assert april["values"]["2025"] == 0

        combined = LeadFilters(years=[2026], months=[7], categories=["A+ (Immediate)"])
        narrowed = build_comparison(db, combined, "product", "leads")
        assert sum(narrowed["selected_total"].values()) == build_summary(db, combined)["kpi"]["leads"]

        full = build_comparison(db, LeadFilters(), "cars", "leads")
        full_summary = build_summary(db, LeadFilters())
        assert sum(full["selected_total"].values()) == full_summary["kpi"]["leads"] - full_summary["kpi"]["undated"]
        assert full_summary["kpi"]["leads_with_quote"] >= full_summary["kpi"]["zero_quotes"]
    finally:
        db.close()
