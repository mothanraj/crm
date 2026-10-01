"""Server-side lead analytics.

Each active lead is counted once. Status, category, remarks, lead value, and
quotation value are the current values stored on the lead (latest state).

Quotation value is ``leads.quotation_value``:
- NULL means no quotation has been saved
- 0 is a real zero quotation
- activity history and the quotations table are not summed into this figure

Lead value is ``leads.lead_value``. NULL is excluded from sum, average, min,
max, and median. Dates use ``enquiry_date`` (a date column, no timezone shift).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Date, Integer, String, and_, case, cast, exists, func, or_
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, LeadSource, LeadStatus, Product, User

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Display order for categories the CRM already uses. Any other stored value
# is appended from the database. B+ is not invented when it is absent.
KNOWN_CATEGORIES = (
    "A+ (Immediate)",
    "A (3-6 months)",
    "B (1 year)",
    "C (Planning Stage)",
)
CATEGORY_ALIASES = {
    "C (plan stage)": "C (Planning Stage)",
    "Planning Stage": "C (Planning Stage)",
}

NOT_INTERESTED = ("Not Interested", "Not Interested/Spam")

# Inclusive rupee bounds. The last bucket has no maximum.
# Kept in one place and returned by the meta API so the UI does not duplicate them.
VALUE_BUCKETS = (
    {"id": "0_1l", "label": "0 – 1 Lakh", "min": 0, "max": 100_000},
    {"id": "1_5l", "label": "1 – 5 Lakhs", "min": 100_000, "max": 500_000},
    {"id": "5_10l", "label": "5 – 10 Lakhs", "min": 500_000, "max": 1_000_000},
    {"id": "10_25l", "label": "10 – 25 Lakhs", "min": 1_000_000, "max": 2_500_000},
    {"id": "25_50l", "label": "25 – 50 Lakhs", "min": 2_500_000, "max": 5_000_000},
    {"id": "50l_1cr", "label": "50 Lakhs – 1 Crore", "min": 5_000_000, "max": 10_000_000},
    {"id": "above_1cr", "label": "Above 1 Crore", "min": 10_000_000, "max": None},
)

PROGRESS_KEYS = (
    ("converted", "Converted"),
    ("followup", "In Followup"),
    ("not_interested", NOT_INTERESTED),
    ("meeting", "Meeting"),
    ("site_visit", "Site Visit"),
    ("quotation_sent", "Quotation sent"),
)


def percent_change(current: float | None, previous: float | None) -> float | None:
    """((current - previous) / previous) * 100. None when the baseline is 0 or missing."""
    if previous is None or float(previous) == 0:
        return None
    cur = 0.0 if current is None else float(current)
    return round((cur - float(previous)) / float(previous) * 100, 1)


def _rupee(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def _rupee0(value) -> int:
    return 0 if value is None else int(round(float(value)))


def _int(value) -> int:
    return 0 if value is None else int(value)


def category_expr():
    blank = or_(Lead.customer_review.is_(None), func.trim(Lead.customer_review) == "")
    clauses = [(blank, "Uncategorised")]
    for old, new in CATEGORY_ALIASES.items():
        clauses.append((Lead.customer_review == old, new))
    return case(*clauses, else_=Lead.customer_review)


def status_expr():
    """Current work progress. A new lead that already has an owner is shown as Assigned."""
    return case(
        (and_(LeadStatus.name == "New Lead", Lead.primary_employee_id.isnot(None)), "Assigned"),
        (LeadStatus.name.is_(None), "Missing"),
        else_=LeadStatus.name,
    )


def city_expr():
    return func.coalesce(func.nullif(func.trim(Lead.city), ""), "Unspecified")


def source_expr():
    return func.coalesce(LeadSource.name, "Unspecified")


def product_expr():
    raw = func.nullif(func.trim(Lead.product_raw), "")
    return func.coalesce(Product.name, raw, "Unmapped")


def employee_expr():
    return func.coalesce(User.name, "Unassigned")


def cars_expr():
    """Same cars text the lead report shows: the typed value, otherwise the number."""
    raw = func.nullif(func.trim(Lead.quantity_raw), "")
    numeric = cast(cast(func.trunc(Lead.quantity_num), Integer), String)
    from_num = case((Lead.quantity_num.is_(None), None), else_=numeric)
    return func.coalesce(raw, from_num, "Unspecified")


def _like(term: str) -> str:
    cleaned = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned}%"


@dataclass
class DateScope:
    years: list[int] = field(default_factory=list)
    months: list[int] = field(default_factory=list)
    start: date | None = None
    end: date | None = None


@dataclass
class LeadFilters:
    years: list[int] = field(default_factory=list)
    months: list[int] = field(default_factory=list)
    from_date: date | None = None
    to_date: date | None = None
    lead_min: int | None = None
    lead_max: int | None = None
    quote_min: int | None = None
    quote_max: int | None = None
    categories: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    source_ids: list[UUID] = field(default_factory=list)
    source_unspecified: bool = False
    product_ids: list[UUID] = field(default_factory=list)
    product_unmapped: bool = False
    employee_ids: list[UUID] = field(default_factory=list)
    employee_unassigned: bool = False
    cities: list[str] = field(default_factory=list)
    cars_min: int | None = None
    cars_max: int | None = None
    customer: str = ""
    enquiry: str = ""
    cars: list[str] = field(default_factory=list)
    view: str = "current"

    def global_scope(self) -> DateScope:
        return DateScope(self.years, self.months, self.from_date, self.to_date)


def _base(db: Session):
    return (
        db.query(Lead)
        .outerjoin(LeadStatus, Lead.status_id == LeadStatus.id)
        .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
        .outerjoin(Product, Lead.product_id == Product.id)
        .outerjoin(User, Lead.primary_employee_id == User.id)
    )


def apply_filters(q, f: LeadFilters, scope: DateScope | None = None):
    """AND across filter groups. Caller passes OR-lists already collected."""
    scope = scope or f.global_scope()
    q = q.filter(Lead.is_active.is_(True))
    dated = bool(scope.years or scope.months or scope.start or scope.end)
    if scope.years:
        q = q.filter(func.extract("year", Lead.enquiry_date).in_(scope.years))
    if scope.months:
        q = q.filter(func.extract("month", Lead.enquiry_date).in_(scope.months))
    if scope.start:
        q = q.filter(Lead.enquiry_date >= scope.start)
    if scope.end:
        q = q.filter(Lead.enquiry_date <= scope.end)
    if dated:
        q = q.filter(Lead.enquiry_date.isnot(None))
    if f.lead_min is not None:
        q = q.filter(Lead.lead_value >= f.lead_min)
    if f.lead_max is not None:
        q = q.filter(Lead.lead_value <= f.lead_max)
    if f.quote_min is not None:
        q = q.filter(Lead.quotation_value >= f.quote_min)
    if f.quote_max is not None:
        q = q.filter(Lead.quotation_value <= f.quote_max)
    if f.categories:
        q = q.filter(category_expr().in_(f.categories))
    if f.statuses:
        q = q.filter(status_expr().in_(f.statuses))
    if f.progress:
        if f.view == "historical":
            q = q.filter(exists().where(and_(
                LeadActivity.lead_id == Lead.id,
                LeadActivity.activity_type == "Work Progress",
                LeadActivity.outcome.in_(f.progress),
            )))
        else:
            q = q.filter(status_expr().in_(f.progress))
    source_conds = []
    if f.source_ids:
        source_conds.append(Lead.source_id.in_(f.source_ids))
    if f.source_unspecified:
        source_conds.append(Lead.source_id.is_(None))
    if source_conds:
        q = q.filter(or_(*source_conds))
    product_conds = []
    if f.product_ids:
        product_conds.append(Lead.product_id.in_(f.product_ids))
    if f.product_unmapped:
        product_conds.append(Lead.product_id.is_(None))
    if product_conds:
        q = q.filter(or_(*product_conds))
    employee_conds = []
    if f.employee_ids:
        employee_conds.append(Lead.primary_employee_id.in_(f.employee_ids))
    if f.employee_unassigned:
        employee_conds.append(Lead.primary_employee_id.is_(None))
    if employee_conds:
        q = q.filter(or_(*employee_conds))
    if f.cities:
        q = q.filter(city_expr().in_(f.cities))
    if f.cars:
        q = q.filter(cars_expr().in_(f.cars))
    if f.cars_min is not None:
        q = q.filter(Lead.quantity_num >= f.cars_min)
    if f.cars_max is not None:
        q = q.filter(Lead.quantity_num <= f.cars_max)
    if f.customer.strip():
        q = q.filter(Lead.customer_name.ilike(_like(f.customer), escape="\\"))
    if f.enquiry.strip():
        q = q.filter(Lead.enquiry_number.ilike(_like(f.enquiry), escape="\\"))
    return q


def _status_counts():
    status = status_expr()
    cols = []
    for key, names in PROGRESS_KEYS:
        if isinstance(names, tuple):
            cols.append(func.coalesce(func.sum(case((status.in_(names), 1), else_=0)), 0).label(key))
        else:
            cols.append(func.coalesce(func.sum(case((status == names, 1), else_=0)), 0).label(key))
    return cols


def _kpi_columns():
    return [
        func.count(Lead.id).label("leads"),
        func.coalesce(func.sum(Lead.lead_value), 0).label("lead_value"),
        func.coalesce(func.sum(Lead.quotation_value), 0).label("quotation_value"),
        func.avg(Lead.lead_value).label("avg_lead"),
        func.avg(Lead.quotation_value).label("avg_quote"),
        func.min(Lead.lead_value).label("min_lead"),
        func.max(Lead.lead_value).label("max_lead"),
        func.min(Lead.quotation_value).label("min_quote"),
        func.max(Lead.quotation_value).label("max_quote"),
        func.count(Lead.lead_value).label("leads_with_value"),
        func.count(Lead.quotation_value).label("leads_with_quote"),
        func.coalesce(func.sum(case((Lead.quotation_value.is_(None), 1), else_=0)), 0).label("leads_without_quote"),
        func.coalesce(func.sum(case((Lead.quotation_value == 0, 1), else_=0)), 0).label("zero_quotes"),
        func.coalesce(func.sum(case((Lead.enquiry_date.is_(None), 1), else_=0)), 0).label("undated"),
        *_status_counts(),
    ]


def _pack_kpi(row) -> dict:
    leads = _int(row.leads)
    valued = _int(row.leads_with_value)
    quoted = _int(row.leads_with_quote)
    lead_value = _rupee0(row.lead_value)
    quote_value = _rupee0(row.quotation_value)
    return {
        "leads": leads,
        "lead_value": lead_value,
        "quotation_value": quote_value,
        "avg_lead_value": _rupee(row.avg_lead) if valued else None,
        "avg_quotation_value": _rupee(row.avg_quote) if quoted else None,
        "min_lead_value": _rupee(row.min_lead),
        "max_lead_value": _rupee(row.max_lead),
        "min_quotation_value": _rupee(row.min_quote),
        "max_quotation_value": _rupee(row.max_quote),
        "median_lead_value": None,
        "median_quotation_value": None,
        "leads_with_value": valued,
        "leads_with_quote": quoted,
        "leads_without_quote": _int(row.leads_without_quote),
        "zero_quotes": _int(row.zero_quotes),
        "undated": _int(getattr(row, "undated", 0)),
        "converted": _int(row.converted),
        "followup": _int(row.followup),
        "not_interested": _int(row.not_interested),
        "meeting": _int(row.meeting),
        "site_visit": _int(row.site_visit),
        "quotation_sent": _int(row.quotation_sent),
        "conversion_pct": round(100.0 * _int(row.converted) / leads, 1) if leads else None,
    }


def _query_kpi(db: Session, f: LeadFilters, scope: DateScope | None = None) -> dict:
    q = apply_filters(_base(db), f, scope)
    row = q.with_entities(*_kpi_columns()).one()
    packed = _pack_kpi(row)
    packed["median_lead_value"] = _median(db, f, scope, Lead.lead_value)
    packed["median_quotation_value"] = _median(db, f, scope, Lead.quotation_value)
    return packed


def _median(db: Session, f: LeadFilters, scope: DateScope | None, column):
    try:
        q = apply_filters(_base(db), f, scope).filter(column.isnot(None))
        value = q.with_entities(func.percentile_cont(0.5).within_group(column.asc())).scalar()
    except Exception:
        return None
    return _rupee(value)


def _share(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(100.0 * count / total, 1)


def _dim_row(name: str, row, total_leads: int) -> dict:
    leads = _int(row.leads)
    valued = _int(row.leads_with_value)
    quoted = _int(row.leads_with_quote)
    return {
        "name": name or "—",
        "leads": leads,
        "pct": _share(leads, total_leads),
        "lead_value": _rupee0(row.lead_value),
        "quotation_value": _rupee0(row.quotation_value),
        "avg_lead_value": _rupee(row.avg_lead) if valued else None,
        "avg_quotation_value": _rupee(row.avg_quote) if quoted else None,
        "converted": _int(row.converted),
        "followup": _int(row.followup),
        "not_interested": _int(row.not_interested),
        "meeting": _int(row.meeting),
        "site_visit": _int(row.site_visit),
        "quotation_sent": _int(row.quotation_sent),
        "conversion_pct": round(100.0 * _int(row.converted) / leads, 1) if leads else None,
    }


def _group_columns():
    return [
        func.count(Lead.id).label("leads"),
        func.coalesce(func.sum(Lead.lead_value), 0).label("lead_value"),
        func.coalesce(func.sum(Lead.quotation_value), 0).label("quotation_value"),
        func.avg(Lead.lead_value).label("avg_lead"),
        func.avg(Lead.quotation_value).label("avg_quote"),
        func.count(Lead.lead_value).label("leads_with_value"),
        func.count(Lead.quotation_value).label("leads_with_quote"),
        *_status_counts(),
    ]


def _grouped(db: Session, f: LeadFilters, scope: DateScope | None, expr, total: int) -> list[dict]:
    label = expr.label("name")
    rows = (
        apply_filters(_base(db), f, scope)
        .with_entities(label, *_group_columns())
        .group_by(label)
        .all()
    )
    out = [_dim_row(str(r.name), r, total) for r in rows]
    out.sort(key=lambda item: (-item["leads"], item["name"]))
    return out


def _with_zeros(rows: list[dict], required: tuple[str, ...] | list[str], total: int) -> list[dict]:
    found = {row["name"]: row for row in rows}
    ordered = []
    for name in required:
        ordered.append(found.pop(name, {
            "name": name, "leads": 0, "pct": _share(0, total), "lead_value": 0, "quotation_value": 0,
            "avg_lead_value": None, "avg_quotation_value": None, "converted": 0, "followup": 0,
            "not_interested": 0, "meeting": 0, "site_visit": 0, "quotation_sent": 0, "conversion_pct": None,
        }))
    extras = sorted(found.values(), key=lambda item: (-item["leads"], item["name"]))
    return ordered + extras


def _month_rows(db: Session, f: LeadFilters, scope: DateScope | None, total: int) -> list[dict]:
    month_no = func.extract("month", Lead.enquiry_date)
    rows = (
        apply_filters(_base(db), f, scope)
        .filter(Lead.enquiry_date.isnot(None))
        .with_entities(month_no.label("month"), *_group_columns())
        .group_by(month_no)
        .all()
    )
    by_month = {int(r.month): r for r in rows if r.month is not None}
    out = []
    for number, name in enumerate(MONTH_NAMES, start=1):
        row = by_month.get(number)
        if row is None:
            out.append({
                "month": number, "name": name, "leads": 0, "pct": _share(0, total),
                "lead_value": 0, "quotation_value": 0, "avg_lead_value": None, "avg_quotation_value": None,
                "converted": 0, "followup": 0, "not_interested": 0, "meeting": 0,
                "site_visit": 0, "quotation_sent": 0, "conversion_pct": None,
            })
        else:
            packed = _dim_row(name, row, total)
            packed["month"] = number
            out.append(packed)
    return out


def _year_rows(db: Session, f: LeadFilters, scope: DateScope | None, total: int) -> list[dict]:
    year_no = func.extract("year", Lead.enquiry_date)
    rows = (
        apply_filters(_base(db), f, scope)
        .filter(Lead.enquiry_date.isnot(None))
        .with_entities(year_no.label("year"), *_group_columns())
        .group_by(year_no)
        .all()
    )
    out = []
    for row in rows:
        if row.year is None:
            continue
        packed = _dim_row(str(int(row.year)), row, total)
        packed["year"] = int(row.year)
        out.append(packed)
    out.sort(key=lambda item: item["year"])
    return out


def _historical_progress(db: Session, f: LeadFilters, scope: DateScope | None, total: int) -> list[dict]:
    """Distinct leads per progress they have ever been saved under. One lead can appear in several rows."""
    pairs = (
        db.query(
            LeadActivity.lead_id.label("lead_id"),
            func.trim(LeadActivity.outcome).label("name"),
        )
        .filter(
            LeadActivity.activity_type == "Work Progress",
            func.trim(LeadActivity.outcome) != "",
        )
        .distinct()
        .subquery()
    )
    label = pairs.c.name
    rows = (
        apply_filters(_base(db).join(pairs, pairs.c.lead_id == Lead.id), f, scope)
        .with_entities(label, *_group_columns())
        .group_by(label)
        .all()
    )
    out = [_dim_row(str(r.name), r, total) for r in rows if r.name]
    out.sort(key=lambda item: (-item["leads"], item["name"]))
    return out


def _historical_category(db: Session, f: LeadFilters, scope: DateScope | None, total: int) -> list[dict]:
    raw = func.trim(LeadActivity.customer_review)
    name = case(
        (or_(raw.is_(None), raw == ""), "Uncategorised"),
        (raw == "C (plan stage)", "C (Planning Stage)"),
        (raw == "Planning Stage", "C (Planning Stage)"),
        else_=raw,
    )
    pairs = (
        db.query(LeadActivity.lead_id.label("lead_id"), name.label("name"))
        .filter(LeadActivity.activity_type == "Work Progress")
        .distinct()
        .subquery()
    )
    rows = (
        apply_filters(_base(db).join(pairs, pairs.c.lead_id == Lead.id), f, scope)
        .with_entities(pairs.c.name.label("name"), *_group_columns())
        .group_by(pairs.c.name)
        .all()
    )
    packed = [_dim_row(str(r.name), r, total) for r in rows if r.name]
    return _with_zeros(packed, KNOWN_CATEGORIES, total)


COMPARE_METRIC_KEYS = (
    "leads", "lead_value", "quotation_value", "avg_lead_value", "avg_quotation_value",
    "converted", "followup", "not_interested", "meeting", "site_visit", "quotation_sent",
)


def _blank_side() -> dict:
    return {key: (None if key.startswith("avg_") else 0) for key in COMPARE_METRIC_KEYS}


def _side_from_kpi(kpi: dict) -> dict:
    return {key: kpi.get(key) for key in COMPARE_METRIC_KEYS}


def _compare_pair(left: dict, right: dict) -> dict:
    diff = {}
    pct = {}
    for key in COMPARE_METRIC_KEYS:
        a = left.get(key)
        b = right.get(key)
        if key.startswith("avg_") and a is None and b is None:
            diff[key] = None
            pct[key] = None
            continue
        a_num = 0 if a is None else a
        b_num = 0 if b is None else b
        diff[key] = b_num - a_num
        pct[key] = percent_change(b_num, a_num)
    return {"left": left, "right": right, "difference": diff, "pct_change": pct}


def _align_dims(left_rows: list[dict], right_rows: list[dict]) -> list[dict]:
    names = []
    seen = set()
    for row in left_rows + right_rows:
        if row["name"] not in seen:
            seen.add(row["name"])
            names.append(row["name"])
    left_map = {row["name"]: row for row in left_rows}
    right_map = {row["name"]: row for row in right_rows}
    empty = {"leads": 0, "lead_value": 0, "quotation_value": 0, "converted": 0, "pct": None}
    out = []
    for name in names:
        left = left_map.get(name, empty)
        right = right_map.get(name, empty)
        out.append({
            "name": name,
            "left_leads": left.get("leads", 0),
            "right_leads": right.get("leads", 0),
            "left_lead_value": left.get("lead_value", 0),
            "right_lead_value": right.get("lead_value", 0),
            "left_quotation_value": left.get("quotation_value", 0),
            "right_quotation_value": right.get("quotation_value", 0),
            "left_converted": left.get("converted", 0),
            "right_converted": right.get("converted", 0),
            "left_pct": left.get("pct"),
            "right_pct": right.get("pct"),
        })
    return out


def _slice(db: Session, f: LeadFilters, scope: DateScope) -> dict:
    kpi = _query_kpi(db, f, scope)
    total = kpi["leads"]
    if f.view == "historical":
        progress = _historical_progress(db, f, scope, total)
        category = _historical_category(db, f, scope, total)
    else:
        progress = _with_zeros(_grouped(db, f, scope, status_expr(), total), (), total)
        category = _with_zeros(_grouped(db, f, scope, category_expr(), total), KNOWN_CATEGORIES, total)
    return {
        "kpi": kpi,
        "by_month": _month_rows(db, f, scope, total),
        "by_category": category,
        "by_progress": progress,
        "by_source": _grouped(db, f, scope, source_expr(), total),
        "by_product": _grouped(db, f, scope, product_expr(), total),
        "by_employee": _grouped(db, f, scope, employee_expr(), total),
        "by_city": _grouped(db, f, scope, city_expr(), total),
    }


def build_summary(
    db: Session,
    f: LeadFilters,
    compare_years: tuple[int, int] | None = None,
    period_a: tuple[date, date] | None = None,
    period_b: tuple[date, date] | None = None,
) -> dict:
    scope = f.global_scope()
    current = _slice(db, f, scope)
    kpi = current["kpi"]
    payload = {
        "view": f.view if f.view in {"current", "historical"} else "current",
        "kpi": kpi,
        "by_month": current["by_month"],
        "by_year": _year_rows(db, f, scope, kpi["leads"]),
        "by_category": current["by_category"],
        "by_progress": current["by_progress"],
        "by_source": current["by_source"],
        "by_product": current["by_product"],
        "by_employee": current["by_employee"],
        "by_city": current["by_city"],
        "rules": {
            "date_field": "enquiry_date",
            "state": "current lead status, category, lead value, and quotation value",
            "quotation": "leads.quotation_value. NULL is missing. 0 is a saved zero. Not a sum of quotation revisions.",
            "lead_value": "sum of leads.lead_value. NULL values are left out of sum, average, min, max, and median.",
            "counting": "each lead is counted once",
            "historical": "Historical view counts a lead under every progress or category it was saved with. KPI totals still count each lead once.",
        },
    }
    if compare_years:
        year_a, year_b = compare_years
        # Month still applies. The global year and custom from/to do not.
        left_scope = DateScope(years=[year_a], months=f.months)
        right_scope = DateScope(years=[year_b], months=f.months)
        left = _slice(db, f, left_scope)
        right = _slice(db, f, right_scope)
        months = []
        for index, name in enumerate(MONTH_NAMES):
            months.append({
                "month": index + 1,
                "name": name,
                **_compare_pair(_side_from_kpi(left["by_month"][index]), _side_from_kpi(right["by_month"][index])),
            })
        payload["year_compare"] = {
            "left_year": year_a,
            "right_year": year_b,
            "totals": _compare_pair(_side_from_kpi(left["kpi"]), _side_from_kpi(right["kpi"])),
            "months": months,
            "by_category": _align_dims(left["by_category"], right["by_category"]),
            "by_progress": _align_dims(left["by_progress"], right["by_progress"]),
            "by_source": _align_dims(left["by_source"], right["by_source"]),
            "by_product": _align_dims(left["by_product"], right["by_product"]),
            "by_employee": _align_dims(left["by_employee"], right["by_employee"]),
            "by_city": _align_dims(left["by_city"], right["by_city"]),
            "note": "Year comparison keeps every filter except the selected year and the custom from/to dates. A selected month still applies.",
        }
    if period_a and period_b:
        left = _query_kpi(db, f, DateScope(start=period_a[0], end=period_a[1]))
        right = _query_kpi(db, f, DateScope(start=period_b[0], end=period_b[1]))
        payload["period_compare"] = {
            "left": {"from": period_a[0].isoformat(), "to": period_a[1].isoformat()},
            "right": {"from": period_b[0].isoformat(), "to": period_b[1].isoformat()},
            "totals": _compare_pair(_side_from_kpi(left), _side_from_kpi(right)),
            "note": "Date-range comparison keeps every filter except year, month, and the dashboard from/to dates.",
        }
    return payload


def _cars_sort_key(name: str):
    if name == "Unspecified":
        return (2, 0.0, "")
    try:
        return (0, float(name), "")
    except ValueError:
        return (1, 0.0, name.lower())


COMPARE_OPTIONS = {
    "leads": {"label": "No. of Leads", "measures": ("leads",), "default": "leads"},
    "lead_value": {
        "label": "Lead Value",
        "measures": ("leads", "lead_value"),
        "default": "leads",
    },
    "quotations": {"label": "No. of Quotations", "measures": ("quotations",), "default": "quotations"},
    "quotation_value": {
        "label": "Quotation",
        "measures": ("quotations", "quotation_value"),
        "default": "quotations",
    },
    "progress": {"label": "Progress", "measures": ("leads",), "default": "leads"},
    "category": {"label": "Category", "measures": ("leads",), "default": "leads"},
    "product": {"label": "Product", "measures": ("leads",), "default": "leads"},
    "source": {"label": "Source", "measures": ("leads",), "default": "leads"},
    "cars": {"label": "Cars", "measures": ("leads",), "default": "leads"},
}
DIMENSION_COMPARE = {"progress", "category", "product", "source", "cars"}

MEASURE_LABELS = {
    "leads": "No. of Leads",
    "lead_value": "Total Lead Value",
    "quotations": "No. of Quotations",
    "quotation_value": "Total Quotation Value",
}

MONEY_MEASURES = {"lead_value", "quotation_value"}


def _period_label(months: list[int]) -> str:
    ordered = sorted(set(months))
    if not ordered or ordered == list(range(1, 13)):
        return "Total"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        start = MONTH_NAMES[ordered[0] - 1][:3]
        end = MONTH_NAMES[ordered[-1] - 1][:3]
        return start if start == end else f"{start}–{end}"
    return "Selected total"


# Progress options shown on the analytics Compare-by Progress picker.
ANALYTICS_PROGRESS = (
    "In Followup",
    "Site Visit",
    "Meeting",
    "Quotation sent",
    "Converted",
    "Not Interested",
)


def _progress_names(db: Session) -> list[str]:
    """Fixed progress list for analytics. Other statuses stay off this page."""
    del db
    return list(ANALYTICS_PROGRESS)


def _category_names(db: Session) -> list[str]:
    stored = [
        name for (name,) in (
            db.query(func.distinct(category_expr())).filter(Lead.is_active.is_(True)).all()
        )
        if name
    ]
    names = list(KNOWN_CATEGORIES)
    for name in sorted(stored):
        if name not in names and name != "Uncategorised":
            names.append(name)
    if "Uncategorised" not in names:
        names.append("Uncategorised")
    return names


def _source_names(db: Session) -> list[str]:
    from app.services.normalize import CANONICAL_SOURCES

    stored = [
        name for (name,) in (
            db.query(func.distinct(source_expr()))
            .select_from(Lead)
            .outerjoin(LeadSource, Lead.source_id == LeadSource.id)
            .filter(Lead.is_active.is_(True))
            .all()
        )
        if name
    ]
    names = [name for name in CANONICAL_SOURCES if name]
    for name in stored:
        if name not in names:
            names.append(name)
    return names or ["Unspecified"]


def _product_names(db: Session) -> list[str]:
    from app.services.pricing import CANONICAL_PRODUCTS

    stored = [
        name for (name,) in (
            db.query(func.distinct(product_expr()))
            .select_from(Lead)
            .outerjoin(Product, Lead.product_id == Product.id)
            .filter(Lead.is_active.is_(True))
            .all()
        )
        if name
    ]
    names = list(CANONICAL_PRODUCTS)
    for name in stored:
        if name not in names and name != "Unmapped":
            names.append(name)
    for (name,) in db.query(Product.name).filter(Product.is_active.is_(True)).order_by(Product.name):
        if name not in names:
            names.append(name)
    if "Unmapped" not in names:
        names.append("Unmapped")
    return names


def _comparison_catalog(db: Session, kind: str, f: LeadFilters, found: list[str]) -> list[str]:
    if kind == "progress":
        names = _progress_names(db)
        chosen = [name for name in (*f.progress, *f.statuses) if name]
        if chosen:
            names = [name for name in names if name in chosen] or chosen
        return names
    if kind == "category":
        names = _category_names(db)
        if f.categories:
            names = [name for name in names if name in f.categories] or list(f.categories)
        return names
    if kind == "source":
        if f.source_ids or f.source_unspecified:
            return list(dict.fromkeys(found)) or _source_names(db)
        return _source_names(db)
    if kind == "cars":
        if f.cars:
            return sorted(set(f.cars), key=_cars_sort_key)
        names = [
            name for (name,) in (
                db.query(func.distinct(cars_expr())).filter(Lead.is_active.is_(True)).all()
            )
            if name
        ]
        return sorted(set(names) or {"Unspecified"}, key=_cars_sort_key)
    if f.product_ids or f.product_unmapped:
        names = list(dict.fromkeys(found))
        if f.product_unmapped and "Unmapped" not in names:
            names.append("Unmapped")
        if f.product_ids:
            for (name,) in db.query(Product.name).filter(Product.id.in_(f.product_ids)):
                if name not in names:
                    names.append(name)
        return names or ["Unmapped"]
    return _product_names(db)


def _lead_day():
    """Enquiry date. When that is blank, the day the lead was added in India."""
    added = cast(func.timezone("Asia/Kolkata", Lead.created_at), Date)
    return func.coalesce(Lead.enquiry_date, added)


def _dated_leads(db: Session, f: LeadFilters):
    """Same lead filters, but the year and month follow the enquiry date or the added day."""
    day = _lead_day()
    bare = replace(f, years=[], months=[], from_date=None, to_date=None)
    q = apply_filters(_base(db), bare)
    if f.years:
        q = q.filter(func.extract("year", day).in_(list(f.years)))
    chosen_months = sorted({m for m in f.months if 1 <= m <= 12})
    if chosen_months:
        q = q.filter(func.extract("month", day).in_(chosen_months))
    if f.from_date:
        q = q.filter(day >= f.from_date)
    if f.to_date:
        q = q.filter(day <= f.to_date)
    return q, day


def _shift_year(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last_day = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last_day))


def _previous_span(start: date, end: date) -> tuple[date, date]:
    length = (end - start).days
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=length), previous_end


RANGE_PRESETS = {
    "24h_prev": "Compare last 24 hours to previous period",
    "24h_wow": "Compare last 24 hours week over week",
    "7d_prev": "Compare last 7 days to previous period",
    "7d_yoy": "Compare last 7 days year over year",
    "28d_prev": "Compare last 28 days to previous period",
    "28d_yoy": "Compare last 28 days year over year",
    "3m_prev": "Compare last 3 months to previous period",
    "3m_yoy": "Compare last 3 months year over year",
    "6m_prev": "Compare last 6 months to previous period",
    "custom": "Custom",
}


def range_windows(preset: str, today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """Current window and the window it is compared with. Dates are inclusive."""
    if preset == "24h_prev":
        current = (today, today)
        previous = (today - timedelta(days=1), today - timedelta(days=1))
    elif preset == "24h_wow":
        current = (today, today)
        previous = (today - timedelta(days=7), today - timedelta(days=7))
    elif preset == "7d_prev":
        current = (today - timedelta(days=6), today)
        previous = _previous_span(*current)
    elif preset == "7d_yoy":
        current = (today - timedelta(days=6), today)
        previous = (_shift_year(current[0], -1), _shift_year(current[1], -1))
    elif preset == "28d_prev":
        current = (today - timedelta(days=27), today)
        previous = _previous_span(*current)
    elif preset == "28d_yoy":
        current = (today - timedelta(days=27), today)
        previous = (_shift_year(current[0], -1), _shift_year(current[1], -1))
    elif preset == "3m_prev":
        current = (_add_months(today, -3) + timedelta(days=1), today)
        previous = _previous_span(*current)
    elif preset == "3m_yoy":
        current = (_add_months(today, -3) + timedelta(days=1), today)
        previous = (_shift_year(current[0], -1), _shift_year(current[1], -1))
    elif preset == "6m_prev":
        current = (_add_months(today, -6) + timedelta(days=1), today)
        previous = _previous_span(*current)
    else:
        raise ValueError(preset)
    return current, previous


def _dimension_expr(kind: str):
    return {
        "progress": status_expr,
        "category": category_expr,
        "product": product_expr,
        "source": source_expr,
        "cars": cars_expr,
    }[kind]()


def build_range_comparison(
    db: Session,
    f: LeadFilters,
    compare_by: str,
    measure: str,
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
    item: str | None = None,
) -> dict:
    """This date range against the range it is compared with. One lead is counted once."""
    if compare_by not in COMPARE_OPTIONS:
        raise ValueError(compare_by)
    chosen = measure if measure in COMPARE_OPTIONS[compare_by]["measures"] else COMPARE_OPTIONS[compare_by]["default"]
    bare = replace(f, years=[], months=[], from_date=None, to_date=None)
    chosen_item = (item or "").strip()

    def daily(start: date, end: date) -> dict[date, int]:
        lead_day = _lead_day()
        q = apply_filters(_base(db), bare).filter(lead_day >= start, lead_day <= end)
        if chosen_item and compare_by in DIMENSION_COMPARE:
            q = q.filter(_dimension_expr(compare_by) == chosen_item)
        rows = (
            q.with_entities(lead_day.label("day"), *_measure_cells())
            .group_by(lead_day)
            .all()
        )
        found: dict[date, int] = {}
        for row in rows:
            if row.day is None:
                continue
            stamp = row.day if type(row.day) is date else row.day.date()
            found[stamp] = found.get(stamp, 0) + _picked(row, chosen)
        return found

    def days_between(start: date, end: date) -> list[date]:
        out = []
        cursor = start
        while cursor <= end:
            out.append(cursor)
            cursor += timedelta(days=1)
        return out

    current_found = daily(current_start, current_end)
    previous_found = daily(previous_start, previous_end)
    current_days = days_between(current_start, current_end)
    previous_days = days_between(previous_start, previous_end)
    series = []
    for index in range(max(len(current_days), len(previous_days))):
        current_day = current_days[index] if index < len(current_days) else None
        previous_day = previous_days[index] if index < len(previous_days) else None
        series.append({
            "day": index + 1,
            "current_date": current_day.isoformat() if current_day else None,
            "previous_date": previous_day.isoformat() if previous_day else None,
            "current": current_found.get(current_day, 0) if current_day else 0,
            "previous": previous_found.get(previous_day, 0) if previous_day else 0,
        })
    current_total = sum(current_found.values())
    previous_total = sum(previous_found.values())
    return {
        "compare_by": compare_by,
        "compare_label": COMPARE_OPTIONS[compare_by]["label"],
        "item": chosen_item or None,
        "measure": chosen,
        "measure_label": MEASURE_LABELS.get(chosen, "Count"),
        "money": chosen in MONEY_MEASURES,
        "current": {"from": current_start.isoformat(), "to": current_end.isoformat()},
        "previous": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
        "current_total": current_total,
        "previous_total": previous_total,
        "change": percent_change(current_total, previous_total),
        "series": series,
    }


def _measure_cells():
    return (
        func.count(Lead.id).label("leads"),
        func.coalesce(func.sum(Lead.lead_value), 0).label("lead_value"),
        func.count(Lead.quotation_value).label("quotations"),
        func.coalesce(func.sum(Lead.quotation_value), 0).label("quotation_value"),
    )


def _picked(row, measure: str) -> int:
    if measure == "lead_value":
        return _rupee0(row.lead_value)
    if measure == "quotations":
        return _int(row.quotations)
    if measure == "quotation_value":
        return _rupee0(row.quotation_value)
    return _int(row.leads)


def _comparison_chart(month_rows, years, details, month_found, kind) -> dict:
    """Lead measures use months. Category, product, source, and progress use one row per type."""
    del month_found
    if not kind:
        lines = [{"key": str(year), "name": str(year)} for year in years]
        points = []
        for row in month_rows:
            point = {"name": str(row["name"])[:3]}
            for year in years:
                point[str(year)] = int(row["values"].get(str(year), 0) or 0)
            points.append(point)
        return {"lines": lines, "points": points}
    lines = [{"key": str(year), "name": str(year)} for year in years]
    points = []
    for item in details:
        point = {"name": item["name"]}
        for year in years:
            point[str(year)] = int(item["values"].get(str(year), 0) or 0)
        points.append(point)
    return {"lines": lines, "points": points}


def build_comparison(db: Session, f: LeadFilters, compare_by: str, measure: str | None = None) -> dict:
    """Month-by-year matrix, plus a dimension breakdown when compare-by is not a value.

    Every figure is the current lead. History, assignments, and quotation revisions
    are not joined, so one lead stays one lead. Quotation NULL is missing, not zero.
    A lead with no enquiry date is counted on the day it was added.
    """
    spec = COMPARE_OPTIONS.get(compare_by)
    if spec is None:
        raise ValueError(compare_by)
    chosen = measure if measure in spec["measures"] else spec["default"]
    years = sorted(set(f.years))
    months = sorted({m for m in f.months if 1 <= m <= 12}) or list(range(1, 13))
    grid_q, day = _dated_leads(db, f)
    year_no = func.extract("year", day)
    month_no = func.extract("month", day)
    grid_rows = (
        grid_q.with_entities(year_no.label("year"), month_no.label("month"), *_measure_cells())
        .group_by(year_no, month_no)
        .all()
    )
    if not years:
        years = sorted({int(row.year) for row in grid_rows if row.year is not None})
    buckets: dict[tuple[int, int], int] = {}
    for row in grid_rows:
        if row.year is None or row.month is None:
            continue
        buckets[(int(row.year), int(row.month))] = _picked(row, chosen)
    year_keys = [str(year) for year in years]
    month_rows = []
    selected = {key: 0 for key in year_keys}
    for number in months:
        values = {key: buckets.get((int(key), number), 0) for key in year_keys}
        for key, value in values.items():
            selected[key] += value
        month_rows.append({"month": number, "name": MONTH_NAMES[number - 1], "values": values})
    kind = compare_by if compare_by in DIMENSION_COMPARE else None
    details: list[dict] = []
    month_found: dict[tuple[str, int, int], int] = {}
    if kind:
        expr = {
            "progress": status_expr,
            "category": category_expr,
            "product": product_expr,
            "source": source_expr,
            "cars": cars_expr,
        }[kind]()
        label = expr.label("name")
        grouped_q, grouped_day = _dated_leads(db, f)
        grouped_year = func.extract("year", grouped_day)
        grouped_month = func.extract("month", grouped_day)
        grouped = (
            grouped_q.with_entities(label, grouped_year.label("year"), grouped_month.label("month"), *_measure_cells())
            .group_by(label, grouped_year, grouped_month)
            .all()
        )
        found: dict[str, dict[str, int]] = {}
        for row in grouped:
            if not row.name or row.year is None:
                continue
            value = _picked(row, chosen)
            year_key = str(int(row.year))
            bucket = found.setdefault(str(row.name), {})
            bucket[year_key] = bucket.get(year_key, 0) + value
            if row.month is not None:
                month_found[(str(row.name), int(row.year), int(row.month))] = value
        catalog = _comparison_catalog(db, kind, f, list(found))
        for name in catalog:
            values = {key: found.get(name, {}).get(key, 0) for key in year_keys}
            details.append({"name": name, "values": values})
        if kind == "cars":
            details.sort(key=lambda item: _cars_sort_key(item["name"]))
    by_month = []
    if kind:
        for number in months:
            by_month.append({
                "month": number,
                "name": MONTH_NAMES[number - 1],
                "items": [
                    {
                        "name": item["name"],
                        "values": {
                            key: int(month_found.get((item["name"], int(key), number), 0) or 0)
                            for key in year_keys
                        },
                    }
                    for item in details
                ],
            })
    kpi_q, _kpi_day = _dated_leads(db, f)
    kpi = _pack_kpi(kpi_q.with_entities(*_kpi_columns()).one())
    return {
        "compare_by": compare_by,
        "compare_label": spec["label"],
        "measure": chosen,
        "measure_label": MEASURE_LABELS[chosen],
        "money": chosen in MONEY_MEASURES,
        "years": years,
        "months": month_rows,
        "period_label": _period_label(months),
        "selected_total": selected,
        "details": details,
        "by_month": by_month,
        "detail_label": COMPARE_OPTIONS[kind]["label"] if kind else None,
        "chart": _comparison_chart(month_rows, years, details, month_found, kind),
        "kpi": kpi,
        "rules": {
            "date_field": "enquiry_date, or the day the lead was added when the enquiry date is blank",
            "state": "current progress, category, product, cars, lead value, and quotation value",
            "quotation": "leads.quotation_value. NULL is missing and is not counted as a quotation. 0 is a saved zero.",
            "lead_value": "sum of leads.lead_value. NULL is left out of the total.",
            "counting": "each lead is counted once",
        },
    }


def build_period_comparison(
    db: Session,
    f: LeadFilters,
    compare_by: str,
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
) -> dict:
    """Daily lines for the selected window and the window it is compared with.

    Lead shows enquiry count and lead value. Quotation shows saved quotations
    and quotation value. NULL quotation is not a quotation. Each lead is once.
    """
    kind = {"lead_value": "lead", "quotation_value": "quotation"}.get(compare_by, compare_by)
    if kind not in {"lead", "quotation"}:
        raise ValueError(compare_by)
    count_key = "quotations" if kind == "quotation" else "leads"
    value_key = "quotation_value" if kind == "quotation" else "lead_value"

    def daily(start: date, end: date) -> tuple[dict[date, int], dict[date, int]]:
        rows = (
            apply_filters(_base(db), f, DateScope(start=start, end=end))
            .with_entities(Lead.enquiry_date.label("day"), *_measure_cells())
            .group_by(Lead.enquiry_date)
            .all()
        )
        counts: dict[date, int] = {}
        values: dict[date, int] = {}
        for row in rows:
            if row.day is None:
                continue
            counts[row.day] = _int(getattr(row, count_key))
            values[row.day] = _rupee0(getattr(row, value_key))
        return counts, values

    def days_between(start: date, end: date) -> list[date]:
        out = []
        cursor = start
        while cursor <= end:
            out.append(cursor)
            cursor += timedelta(days=1)
        return out

    current_counts, current_values = daily(current_start, current_end)
    previous_counts, previous_values = daily(previous_start, previous_end)
    current_days = days_between(current_start, current_end)
    previous_days = days_between(previous_start, previous_end)
    series = []
    for index in range(max(len(current_days), len(previous_days))):
        current_day = current_days[index] if index < len(current_days) else None
        previous_day = previous_days[index] if index < len(previous_days) else None
        series.append({
            "day": index + 1,
            "current_date": current_day.isoformat() if current_day else None,
            "previous_date": previous_day.isoformat() if previous_day else None,
            "count": current_counts.get(current_day, 0) if current_day else 0,
            "value": current_values.get(current_day, 0) if current_day else 0,
            "previous_count": previous_counts.get(previous_day, 0) if previous_day else 0,
            "previous_value": previous_values.get(previous_day, 0) if previous_day else 0,
        })
    totals = {
        "count": sum(current_counts.values()),
        "value": sum(current_values.values()),
        "previous_count": sum(previous_counts.values()),
        "previous_value": sum(previous_values.values()),
    }
    current_scope = DateScope(start=current_start, end=current_end)
    return {
        "compare_by": kind,
        "compare_label": "Quotation" if kind == "quotation" else "Lead",
        "count_label": "No. of Quotations" if kind == "quotation" else "No. of Leads",
        "value_label": "Quotation Value" if kind == "quotation" else "Lead Value",
        "current": {"from": current_start.isoformat(), "to": current_end.isoformat()},
        "previous": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
        "totals": totals,
        "count_change": percent_change(totals["count"], totals["previous_count"]),
        "value_change": percent_change(totals["value"], totals["previous_value"]),
        "series": series,
        "kpi": _query_kpi(db, f, current_scope),
        "rules": {
            "date_field": "enquiry_date",
            "quotation": "leads.quotation_value. NULL is missing and is not counted as a quotation. 0 is a saved zero.",
            "lead_value": "sum of leads.lead_value. NULL is left out of the total.",
            "counting": "each lead is counted once",
        },
    }


def year_month_matrix(db: Session, f: LeadFilters, years: list[int], compare_by: str) -> dict:
    """Month rows for every selected year. Both the count and the value are included."""
    kind = {"lead_value": "lead", "quotation_value": "quotation"}.get(compare_by, compare_by)
    count_key = "quotations" if kind == "quotation" else "leads"
    value_key = "quotation_value" if kind == "quotation" else "lead_value"
    chosen = sorted({int(year) for year in years})
    rows = (
        apply_filters(_base(db), f, DateScope(years=chosen))
        .filter(Lead.enquiry_date.isnot(None))
        .with_entities(
            func.extract("year", Lead.enquiry_date).label("year"),
            func.extract("month", Lead.enquiry_date).label("month"),
            *_measure_cells(),
        )
        .group_by(func.extract("year", Lead.enquiry_date), func.extract("month", Lead.enquiry_date))
        .all()
    )
    found = sorted({int(row.year) for row in rows if row.year is not None})
    use_years = chosen or found
    counts: dict[tuple[int, int], int] = {}
    values: dict[tuple[int, int], int] = {}
    for row in rows:
        if row.year is None or row.month is None:
            continue
        key = (int(row.year), int(row.month))
        counts[key] = _int(getattr(row, count_key))
        values[key] = _rupee0(getattr(row, value_key))
    months = []
    for number in range(1, 13):
        months.append({
            "month": number,
            "name": MONTH_NAMES[number - 1],
            "counts": {str(year): counts.get((year, number), 0) for year in use_years},
            "values": {str(year): values.get((year, number), 0) for year in use_years},
        })
    return {"years": use_years, "months": months}


SORTS = {
    "date": Lead.enquiry_date,
    "enquiry": Lead.enquiry_number,
    "customer": Lead.customer_name,
    "city": Lead.city,
    "cars": Lead.quantity_num,
    "product": Product.name,
    "source": LeadSource.name,
    "status": LeadStatus.name,
    "category": Lead.customer_review,
    "employee": User.name,
    "lead_value": Lead.lead_value,
    "quotation_value": Lead.quotation_value,
}


def query_rows(db: Session, f: LeadFilters, *, page: int, page_size: int, sort: str, direction: str) -> dict:
    q = apply_filters(_base(db), f)
    total = q.with_entities(func.count(Lead.id)).scalar() or 0
    column = SORTS.get(sort, Lead.enquiry_date)
    ordered = column.desc() if direction == "desc" else column.asc()
    # enquiry_date desc, then enquiry number, so pages stay stable.
    rows = (
        q.with_entities(
            Lead.id, Lead.enquiry_number, Lead.enquiry_date, Lead.customer_name, Lead.city,
            Lead.contact_number, Lead.email, Lead.quantity_raw, Lead.quantity_num,
            product_expr(), source_expr(), status_expr(), category_expr(),
            Lead.employee_remarks, employee_expr(), Lead.lead_value, Lead.quotation_value,
        )
        .order_by(ordered.nulls_last(), Lead.enquiry_number.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for row in rows:
        cars = (row.quantity_raw or "").strip()
        if not cars and row.quantity_num is not None:
            cars = str(int(row.quantity_num))
        items.append({
            "id": str(row.id),
            "enquiry_number": row.enquiry_number or "—",
            "enquiry_date": row.enquiry_date.isoformat() if row.enquiry_date else None,
            "customer_name": row.customer_name or "—",
            "city": row.city or "—",
            "contact": row.contact_number or "—",
            "email": row.email or "",
            "cars": cars or "—",
            "product": row[9] or "—",
            "source": row[10] or "—",
            "status": row[11] or "—",
            "progress": row[11] or "—",
            "category": row[12] or "Uncategorised",
            "remarks": (row.employee_remarks or "").strip() or "—",
            "employee": row[14] or "Unassigned",
            "lead_value": _rupee(row.lead_value),
            "quotation_value": _rupee(row.quotation_value),
        })
    pages = max(1, (int(total) + page_size - 1) // page_size) if total else 1
    return {"total": int(total), "page": page, "page_size": page_size, "pages": pages, "rows": items}


def iter_export_rows(db: Session, f: LeadFilters, limit: int = 50000):
    page = 1
    size = 500
    produced = 0
    while produced < limit:
        batch = query_rows(db, f, page=page, page_size=size, sort="date", direction="desc")
        if not batch["rows"]:
            break
        for row in batch["rows"]:
            yield row
            produced += 1
            if produced >= limit:
                break
        if page >= batch["pages"]:
            break
        page += 1


def available_years(db: Session) -> list[int]:
    found = [
        int(year) for (year,) in db.query(func.extract("year", Lead.enquiry_date))
        .filter(Lead.is_active.is_(True), Lead.enquiry_date.isnot(None))
        .distinct()
        .all()
        if year is not None
    ]
    today = date.today().year
    start = today - 15
    if found:
        start = min(start, min(found))
    return list(range(today, start - 1, -1))


def meta_payload(db: Session) -> dict:
    years = available_years(db)
    data_years = [
        int(year) for (year,) in db.query(func.extract("year", Lead.enquiry_date))
        .filter(Lead.is_active.is_(True), Lead.enquiry_date.isnot(None))
        .distinct().all()
        if year is not None
    ]
    statuses = [name for (name,) in db.query(LeadStatus.name).order_by(LeadStatus.sort_order, LeadStatus.name).all()]
    sources = [{"id": str(row.id), "name": row.name} for row in db.query(LeadSource).order_by(LeadSource.sort_order, LeadSource.name).all()]
    products = [{"id": str(row.id), "name": row.name} for row in db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.name).all()]
    from app.models import Role
    employees = [
        {"id": str(user.id), "name": user.name}
        for user in (
            db.query(User).join(Role, User.role_id == Role.id)
            .filter(User.is_active.is_(True), Role.name == "EMPLOYEE")
            .order_by(User.name).all()
        )
    ]
    city_name = city_expr().label("city")
    cities = [
        city for (city,) in (
            db.query(city_name)
            .filter(Lead.is_active.is_(True))
            .distinct()
            .order_by(city_name)
            .all()
        )
        if city
    ]
    stored_categories = [
        name for (name,) in db.query(func.distinct(category_expr()))
        .select_from(Lead)
        .filter(Lead.is_active.is_(True))
        .all()
        if name
    ]
    categories = list(KNOWN_CATEGORIES)
    for name in sorted(stored_categories):
        if name not in categories and name != "Uncategorised":
            categories.append(name)
    if "Uncategorised" not in categories:
        categories.append("Uncategorised")
    progress = []
    for name in statuses:
        if name == "New Lead" and "Assigned" not in progress:
            progress.append("Assigned")
        if name not in progress:
            progress.append(name)
    if "Assigned" not in progress:
        progress.insert(0, "Assigned")
    car_values = [
        name for (name,) in (
            db.query(cars_expr().label("cars")).filter(Lead.is_active.is_(True)).distinct().all()
        )
        if name
    ]
    car_values.sort(key=_cars_sort_key)
    return {
        "years": years,
        "data_years": sorted(set(data_years), reverse=True),
        "months": [{"value": i, "label": name} for i, name in enumerate(MONTH_NAMES, start=1)],
        "categories": categories,
        "statuses": statuses,
        "progress": progress,
        "sources": sources,
        "products": products,
        "employees": employees,
        "cities": cities,
        "cars": car_values,
        "value_buckets": list(VALUE_BUCKETS),
    }


# ---------------------------------------------------------------------------
# Filter analytics dashboard (Category / Product / Source / Progress)
# ---------------------------------------------------------------------------

FILTER_TYPES = ("category", "product", "source", "progress")
DASHBOARD_METRICS = {
    "leads": {"label": "No. of Leads", "money": False},
    "lead_value": {"label": "Lead Value", "money": True},
    "quotations": {"label": "No. of Quotations", "money": False},
    "quotation_value": {"label": "Quotation Value", "money": True},
}
GRANULARITIES = ("day", "week", "month", "year")


def _filter_label_expr(filter_type: str):
    try:
        return {
            "category": category_expr(),
            "product": product_expr(),
            "source": source_expr(),
            "progress": status_expr(),
        }[filter_type]
    except KeyError as exc:
        raise ValueError(filter_type) from exc


def filter_option_values(db: Session, filter_type: str) -> list[str]:
    """Distinct values currently present on active leads. Nothing is hard-coded."""
    label = _filter_label_expr(filter_type)
    rows = (
        _base(db)
        .filter(Lead.is_active.is_(True))
        .with_entities(label)
        .distinct()
        .all()
    )
    return sorted({str(name).strip() for (name,) in rows if name and str(name).strip()})


def _scoped_leads(db: Session, filter_type: str | None, filter_value: str | None):
    day = _lead_day()
    q = _base(db).filter(Lead.is_active.is_(True))
    if filter_type and filter_value:
        label = _filter_label_expr(filter_type)
        if filter_type == "progress" and filter_value == "Not Interested":
            q = q.filter(label.in_(["Not Interested", "Not Interested/Spam"]))
        else:
            q = q.filter(label == filter_value)
    return q, day


def _metric_agg(metric: str):
    if metric == "leads":
        return func.count(Lead.id)
    if metric == "lead_value":
        return func.coalesce(func.sum(Lead.lead_value), 0)
    if metric == "quotations":
        return func.count(Lead.quotation_value)
    if metric == "quotation_value":
        return func.coalesce(func.sum(Lead.quotation_value), 0)
    raise ValueError(metric)


def _kpi_four(q) -> dict:
    row = q.with_entities(
        func.count(Lead.id).label("leads"),
        func.coalesce(func.sum(Lead.lead_value), 0).label("lead_value"),
        func.count(Lead.quotation_value).label("quotations"),
        func.coalesce(func.sum(Lead.quotation_value), 0).label("quotation_value"),
    ).one()
    return {
        "leads": _int(row.leads),
        "lead_value": _rupee0(row.lead_value),
        "quotations": _int(row.quotations),
        "quotation_value": _rupee0(row.quotation_value),
    }


def _bucket_expr(day, granularity: str):
    if granularity == "day":
        return day
    if granularity == "week":
        return cast(func.date_trunc("week", day), Date)
    if granularity == "month":
        return cast(func.date_trunc("month", day), Date)
    if granularity == "year":
        return cast(func.extract("year", day), Integer)
    raise ValueError(granularity)


def _bucket_key(value, granularity: str) -> str:
    if value is None:
        return ""
    if granularity == "year":
        return str(int(value))
    if hasattr(value, "isoformat"):
        stamp = value if type(value) is date else value.date()
        if granularity == "day":
            return stamp.isoformat()
        if granularity == "week":
            return stamp.isoformat()
        if granularity == "month":
            return f"{stamp.year}-{stamp.month:02d}"
    return str(value)


def _bucket_label(value, granularity: str) -> str:
    if value is None:
        return "—"
    if granularity == "year":
        return str(int(value))
    if hasattr(value, "isoformat"):
        stamp = value if type(value) is date else value.date()
        if granularity == "day":
            return stamp.strftime("%d %b %Y")
        if granularity == "week":
            return f"Week of {stamp.strftime('%d %b %Y')}"
        if granularity == "month":
            return stamp.strftime("%b %Y")
    return str(value)


def _apply_time_scope(q, day, year: int | None, start: date | None, end: date | None):
    if year is not None:
        q = q.filter(func.extract("year", day) == year)
    if start is not None:
        q = q.filter(day >= start)
    if end is not None:
        q = q.filter(day <= end)
    return q


def build_filter_dashboard(
    db: Session,
    filter_type: str | None,
    filter_value: str | None,
    metric: str,
    granularity: str,
    year: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """KPIs plus a time series for one filter value and one metric."""
    if filter_type and filter_type not in FILTER_TYPES:
        raise ValueError("filter_type")
    if filter_type and not filter_value:
        raise ValueError("filter_value")
    if metric not in DASHBOARD_METRICS:
        raise ValueError("metric")
    if granularity not in GRANULARITIES:
        raise ValueError("granularity")
    if from_date and to_date and from_date > to_date:
        raise ValueError("date_range")

    q, day = _scoped_leads(db, filter_type, filter_value)
    q = _apply_time_scope(q, day, year, from_date, to_date)
    kpi = _kpi_four(q)

    bucket = _bucket_expr(day, granularity)
    metric_col = _metric_agg(metric).label("value")
    rows = (
        q.with_entities(bucket.label("bucket"), metric_col)
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    found = {
        _bucket_key(row.bucket, granularity): _rupee0(row.value) if DASHBOARD_METRICS[metric]["money"] else _int(row.value)
        for row in rows
        if row.bucket is not None
    }

    series: list[dict] = []
    if granularity == "month" and year is not None:
        for month in range(1, 13):
            key = f"{year}-{month:02d}"
            label = date(year, month, 1).strftime("%b %Y")
            series.append({"key": key, "label": label, "value": found.get(key, 0)})
    elif granularity == "year":
        years = sorted({int(k) for k in found})
        if year is not None and year not in years:
            years.append(year)
            years.sort()
        for item in years:
            key = str(item)
            series.append({"key": key, "label": key, "value": found.get(key, 0)})
    else:
        for row in rows:
            if row.bucket is None:
                continue
            key = _bucket_key(row.bucket, granularity)
            series.append({
                "key": key,
                "label": _bucket_label(row.bucket, granularity),
                "value": found.get(key, 0),
            })

    return {
        "filter_type": filter_type,
        "filter_value": filter_value,
        "metric": metric,
        "metric_label": DASHBOARD_METRICS[metric]["label"],
        "money": DASHBOARD_METRICS[metric]["money"],
        "granularity": granularity,
        "year": year,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "kpi": kpi,
        "series": series,
        "years": available_years(db),
        "data_years": sorted({
            int(y) for (y,) in db.query(func.extract("year", _lead_day()))
            .select_from(Lead)
            .filter(Lead.is_active.is_(True))
            .distinct().all()
            if y is not None
        }, reverse=True),
    }


def build_filter_period_compare(
    db: Session,
    filter_type: str | None,
    filter_value: str | None,
    metric: str,
    period_a: tuple[date, date],
    period_b: tuple[date, date],
    *,
    category: str | None = None,
    progress: str | None = None,
) -> dict:
    """Period A vs Period B for one filter value and metric.

    When both ranges have the same length, points are aligned day-by-day.
    Prefer category/progress (employee lead fields) when provided.
    """
    if filter_type and filter_type not in FILTER_TYPES:
        raise ValueError("filter_type")
    if metric not in DASHBOARD_METRICS:
        raise ValueError("metric")
    a_start, a_end = period_a
    b_start, b_end = period_b
    if a_start > a_end or b_start > b_end:
        raise ValueError("date_range")

    # Prefer explicit category/progress, else map filter_type into a single scope.
    use_type = filter_type
    use_value = filter_value
    if not use_type:
        if category:
            use_type, use_value = "category", category
        elif progress:
            use_type, use_value = "progress", progress

    money = DASHBOARD_METRICS[metric]["money"]

    def scoped_q():
        if use_type and use_value:
            return _scoped_leads(db, use_type, use_value)
        return _scoped_employee_leads(db)

    def daily(start: date, end: date) -> dict[date, int]:
        q, day = scoped_q()
        q = q.filter(day >= start, day <= end)
        rows = (
            q.with_entities(day.label("day"), _metric_agg(metric).label("value"))
            .group_by(day)
            .all()
        )
        out: dict[date, int] = {}
        for row in rows:
            if row.day is None:
                continue
            stamp = row.day if type(row.day) is date else row.day.date()
            out[stamp] = _rupee0(row.value) if money else _int(row.value)
        return out

    def days_between(start: date, end: date) -> list[date]:
        out = []
        cursor = start
        while cursor <= end:
            out.append(cursor)
            cursor += timedelta(days=1)
        return out

    a_found = daily(a_start, a_end)
    b_found = daily(b_start, b_end)
    a_days = days_between(a_start, a_end)
    b_days = days_between(b_start, b_end)
    a_total = sum(a_found.values())
    b_total = sum(b_found.values())
    equal = len(a_days) == len(b_days)

    series = []
    if equal:
        for index, (a_day, b_day) in enumerate(zip(a_days, b_days)):
            series.append({
                "index": index + 1,
                "period_a_date": a_day.isoformat(),
                "period_b_date": b_day.isoformat(),
                "period_a": a_found.get(a_day, 0),
                "period_b": b_found.get(b_day, 0),
                "label": a_day.strftime("%d %b"),
            })
    else:
        for index in range(max(len(a_days), len(b_days))):
            a_day = a_days[index] if index < len(a_days) else None
            b_day = b_days[index] if index < len(b_days) else None
            series.append({
                "index": index + 1,
                "period_a_date": a_day.isoformat() if a_day else None,
                "period_b_date": b_day.isoformat() if b_day else None,
                "period_a": a_found.get(a_day, 0) if a_day else 0,
                "period_b": b_found.get(b_day, 0) if b_day else 0,
                "label": str(index + 1),
            })

    def dim_breakdown(start: date, end: date, kind: str) -> list[dict]:
        q, day = scoped_q()
        q = q.filter(day >= start, day <= end)
        expr = category_expr() if kind == "category" else status_expr()
        rows = (
            q.with_entities(expr.label("name"), _metric_agg(metric).label("value"))
            .group_by(expr)
            .all()
        )
        found = {
            str(row.name): (_rupee0(row.value) if money else _int(row.value))
            for row in rows if row.name
        }
        order = _category_names(db) if kind == "category" else _progress_names(db)
        out = [{"name": name, "value": found.get(name, 0)} for name in order if found.get(name, 0)]
        for name, value in sorted(found.items()):
            if name not in {row["name"] for row in out}:
                out.append({"name": name, "value": value})
        return out

    return {
        "filter_type": use_type,
        "filter_value": use_value,
        "category": use_value if use_type == "category" else None,
        "progress": use_value if use_type == "progress" else None,
        "metric": metric,
        "metric_label": DASHBOARD_METRICS[metric]["label"],
        "money": money,
        "aligned": equal,
        "period_a": {
            "from": a_start.isoformat(),
            "to": a_end.isoformat(),
            "total": a_total,
            "by_progress": dim_breakdown(a_start, a_end, "progress"),
            "by_category": dim_breakdown(a_start, a_end, "category"),
        },
        "period_b": {
            "from": b_start.isoformat(),
            "to": b_end.isoformat(),
            "total": b_total,
            "by_progress": dim_breakdown(b_start, b_end, "progress"),
            "by_category": dim_breakdown(b_start, b_end, "category"),
        },
        "change": percent_change(a_total, b_total),
        "series": series,
    }


def _auto_granularity(start: date, end: date) -> str:
    days = (end - start).days + 1
    if days <= 45:
        return "day"
    if days <= 180:
        return "week"
    return "month"


def _scoped_employee_leads(
    db: Session,
    *,
    category: str | None = None,
    progress: str | None = None,
):
    """Leads filtered by the same category/progress employees set on the leads page."""
    day = _lead_day()
    q = _base(db).filter(Lead.is_active.is_(True))
    if category:
        q = q.filter(category_expr() == category)
    if progress:
        q = q.filter(status_expr() == progress)
    return q, day


def _breakdown_rows(q, expr, metric: str) -> list[dict]:
    money = DASHBOARD_METRICS[metric]["money"]
    rows = (
        q.with_entities(expr.label("name"), _metric_agg(metric).label("value"))
        .group_by(expr)
        .all()
    )
    found = {
        str(row.name): (_rupee0(row.value) if money else _int(row.value))
        for row in rows if row.name
    }
    total = sum(found.values())
    packed = []
    for name, value in found.items():
        packed.append({
            "name": name,
            "value": value,
            "pct": round(100.0 * value / total, 1) if total else None,
        })
    packed.sort(key=lambda row: (-row["value"], row["name"]))
    return packed


def build_overview(
    db: Session,
    *,
    from_date: date,
    to_date: date,
    metric: str = "leads",
    filter_type: str | None = None,
    filter_value: str | None = None,
    category: str | None = None,
    progress: str | None = None,
    granularity: str | None = None,
) -> dict:
    """GA-style overview: KPIs vs previous period, trend, dimension breakdowns.

    Scope with filter_type + filter_value (category / product / progress / source),
    or legacy category/progress params.
    """
    if metric not in DASHBOARD_METRICS:
        raise ValueError("metric")
    if from_date > to_date:
        raise ValueError("date_range")
    if filter_type and filter_type not in FILTER_TYPES:
        raise ValueError("filter_type")
    if filter_type and not filter_value:
        raise ValueError("filter_value")
    grain = granularity or _auto_granularity(from_date, to_date)
    if grain not in GRANULARITIES:
        raise ValueError("granularity")

    # Normalize legacy params into a single dimension filter.
    use_type = filter_type
    use_value = filter_value
    if not use_type:
        if category:
            use_type, use_value = "category", category
        elif progress:
            use_type, use_value = "progress", progress

    length = (to_date - from_date).days
    prev_end = from_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length)

    if use_type and use_value:
        q, day = _scoped_leads(db, use_type, use_value)
    else:
        q, day = _scoped_employee_leads(db)
    current_q = q.filter(day >= from_date, day <= to_date)
    previous_q = q.filter(day >= prev_start, day <= prev_end)

    kpi = _kpi_four(current_q)
    prev_kpi = _kpi_four(previous_q)
    kpi_change = {key: percent_change(kpi[key], prev_kpi[key]) for key in kpi}

    bucket = _bucket_expr(day, grain)
    money = DASHBOARD_METRICS[metric]["money"]
    rows = (
        current_q.with_entities(bucket.label("bucket"), _metric_agg(metric).label("value"))
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    series = []
    for row in rows:
        if row.bucket is None:
            continue
        series.append({
            "key": _bucket_key(row.bucket, grain),
            "label": _bucket_label(row.bucket, grain),
            "value": _rupee0(row.value) if money else _int(row.value),
        })

    by_progress = _breakdown_rows(current_q, status_expr(), metric)
    by_category = _breakdown_rows(current_q, category_expr(), metric)
    by_product = _breakdown_rows(current_q, product_expr(), metric)
    by_source = _breakdown_rows(current_q, source_expr(), metric)

    progress_order = {name: i for i, name in enumerate(_progress_names(db))}
    category_order = {name: i for i, name in enumerate(_category_names(db))}
    by_progress.sort(key=lambda row: (progress_order.get(row["name"], 999), -row["value"]))
    by_category.sort(key=lambda row: (category_order.get(row["name"], 999), -row["value"]))

    return {
        "metric": metric,
        "metric_label": DASHBOARD_METRICS[metric]["label"],
        "money": money,
        "granularity": grain,
        "filter_type": use_type,
        "filter_value": use_value,
        "category": use_value if use_type == "category" else None,
        "progress": use_value if use_type == "progress" else None,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "previous_from": prev_start.isoformat(),
        "previous_to": prev_end.isoformat(),
        "kpi": kpi,
        "kpi_previous": prev_kpi,
        "kpi_change": kpi_change,
        "series": series,
        "by_progress": by_progress,
        "by_category": by_category,
        "by_product": by_product,
        "by_source": by_source,
        "progress_options": filter_option_values(db, "progress"),
        "category_options": filter_option_values(db, "category"),
        "product_options": filter_option_values(db, "product"),
        "source_options": filter_option_values(db, "source"),
    }


# ---------------------------------------------------------------------------
# Selection compare (year / month / date / period A vs B)
# ---------------------------------------------------------------------------

COMPARE_MODES = ("year", "month", "date", "period")

# Fixed menus for the Analytics page (CRM field names).
# Category = customer_review; Progress = work status.
ANALYTICS_FILTER_MENUS = {
    "category": [
        "A+ (Immediate)",
        "A (3-6 months)",
        "B (1 year)",
        "C (Planning Stage)",
    ],
    "progress": [
        "In Followup",
        "Meeting",
        "Site Visit",
        "Not Interested",
        "Converted",
    ],
    "product": [
        "Two Post Stack Parking",
        "Four Post Stack Parking",
        "Pit Stack Parking",
        "Puzzle Parking",
        "Pit Puzzle Parking",
        "Tower Parking",
        "Shuttle Parking",
        "Car Elevator",
        "ASRS Parking",
    ],
    "source": [
        "SEO",
        "Facebook/Instagram",
        "Google Ads",
        "India Mart",
        "Direct Call",
        "Referral",
        "WhatsApp",
        "Email Campaign",
        "Email Enquiry",
        "Others",
        "Expo/Stall",
    ],
}

MONTH_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def analytics_meta(db: Session) -> dict:
    return {
        "metrics": [
            {"id": key, "label": spec["label"], "money": spec["money"]}
            for key, spec in DASHBOARD_METRICS.items()
        ],
        "dimensions": [
            {"id": "category", "label": "Category", "values": ANALYTICS_FILTER_MENUS["category"]},
            {"id": "product", "label": "Product", "values": ANALYTICS_FILTER_MENUS["product"]},
            {"id": "progress", "label": "Progress", "values": ANALYTICS_FILTER_MENUS["progress"]},
            {"id": "source", "label": "Source", "values": ANALYTICS_FILTER_MENUS["source"]},
        ],
        "compare_modes": [
            {"id": "year", "label": "Year wise"},
            {"id": "month", "label": "Month wise"},
            {"id": "date", "label": "Date wise"},
            {"id": "period", "label": "From–to vs From–to"},
        ],
        "years": available_years(db),
        "months": [{"id": i + 1, "label": MONTH_SHORT[i]} for i in range(12)],
    }


def _metric_total(q, metric: str) -> int:
    money = DASHBOARD_METRICS[metric]["money"]
    value = q.with_entities(_metric_agg(metric)).scalar()
    return _rupee0(value) if money else _int(value)


def build_selection_compare(
    db: Session,
    *,
    metric: str,
    filter_type: str | None = None,
    filter_value: str | None = None,
    mode: str,
    years: list[int] | None = None,
    year: int | None = None,
    months: list[int] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    period_a: tuple[date, date] | None = None,
    period_b: tuple[date, date] | None = None,
) -> dict:
    """Compare one metric (optionally scoped by dimension) under year/month/date/period modes."""
    if metric not in DASHBOARD_METRICS:
        raise ValueError("metric")
    use_type = (filter_type or "").strip() or None
    use_value = (filter_value or "").strip() or None
    if use_type:
        if use_type not in FILTER_TYPES:
            raise ValueError("filter_type")
        if not use_value:
            raise ValueError("filter_value")
    elif use_value:
        raise ValueError("filter_type")
    if mode not in COMPARE_MODES:
        raise ValueError("mode")

    money = DASHBOARD_METRICS[metric]["money"]
    q, day = _scoped_leads(db, use_type, use_value)
    dim_label = {
        "category": "Category",
        "product": "Product",
        "progress": "Progress",
        "source": "Source",
    }.get(use_type or "", "All leads")

    def pack_series(points: list[dict]) -> dict:
        total = sum(int(p.get("value") or 0) for p in points)
        return {
            "metric": metric,
            "metric_label": DASHBOARD_METRICS[metric]["label"],
            "money": money,
            "filter_type": use_type,
            "filter_value": use_value,
            "dimension_label": dim_label,
            "mode": mode,
            "series": points,
            "rows": points,
            "total": total,
        }

    if mode == "year":
        selected = sorted({int(y) for y in (years or []) if y})
        if len(selected) < 1:
            raise ValueError("years")
        if len(selected) > 8:
            raise ValueError("years_limit")
        bucket = cast(func.extract("year", day), Integer)
        rows = (
            q.filter(bucket.in_(selected))
            .with_entities(bucket.label("bucket"), _metric_agg(metric).label("value"))
            .group_by(bucket)
            .all()
        )
        found = {int(row.bucket): (_rupee0(row.value) if money else _int(row.value)) for row in rows if row.bucket is not None}
        points = [{"key": str(y), "label": str(y), "value": found.get(y, 0)} for y in selected]
        out = pack_series(points)
        out["years"] = selected
        out["x_title"] = "Year"
        return out

    if mode == "month":
        if year is None:
            raise ValueError("year")
        selected_months = sorted({int(m) for m in (months or []) if 1 <= int(m) <= 12})
        if len(selected_months) < 1:
            raise ValueError("months")
        month_bucket = cast(func.extract("month", day), Integer)
        year_bucket = cast(func.extract("year", day), Integer)
        rows = (
            q.filter(year_bucket == int(year), month_bucket.in_(selected_months))
            .with_entities(month_bucket.label("bucket"), _metric_agg(metric).label("value"))
            .group_by(month_bucket)
            .all()
        )
        found = {int(row.bucket): (_rupee0(row.value) if money else _int(row.value)) for row in rows if row.bucket is not None}
        points = [
            {"key": f"{year}-{m:02d}", "label": MONTH_SHORT[m - 1], "month": m, "value": found.get(m, 0)}
            for m in selected_months
        ]
        out = pack_series(points)
        out["year"] = int(year)
        out["months"] = selected_months
        out["x_title"] = f"Month ({year})"
        return out

    if mode == "date":
        if not from_date or not to_date:
            raise ValueError("date_range")
        if from_date > to_date:
            raise ValueError("date_range")
        if (to_date - from_date).days > 366:
            raise ValueError("date_span")
        rows = (
            q.filter(day >= from_date, day <= to_date)
            .with_entities(day.label("bucket"), _metric_agg(metric).label("value"))
            .group_by(day)
            .order_by(day)
            .all()
        )
        found: dict[date, int] = {}
        for row in rows:
            if row.bucket is None:
                continue
            stamp = row.bucket if type(row.bucket) is date else row.bucket.date()
            found[stamp] = _rupee0(row.value) if money else _int(row.value)
        points = []
        cursor = from_date
        while cursor <= to_date:
            points.append({
                "key": cursor.isoformat(),
                "label": cursor.strftime("%d %b"),
                "value": found.get(cursor, 0),
            })
            cursor += timedelta(days=1)
        out = pack_series(points)
        out["from_date"] = from_date.isoformat()
        out["to_date"] = to_date.isoformat()
        out["x_title"] = "Date"
        return out

    # period A vs period B — separate series so each side keeps its own dates
    if not period_a or not period_b:
        raise ValueError("period")
    a_start, a_end = period_a
    b_start, b_end = period_b
    if a_start > a_end or b_start > b_end:
        raise ValueError("date_range")
    if (a_end - a_start).days > 1100 or (b_end - b_start).days > 1100:
        raise ValueError("date_span")

    def daily_series(start: date, end: date) -> tuple[list[dict], int]:
        rows = (
            q.filter(day >= start, day <= end)
            .with_entities(day.label("bucket"), _metric_agg(metric).label("value"))
            .group_by(day)
            .all()
        )
        found: dict[date, int] = {}
        for row in rows:
            if row.bucket is None:
                continue
            stamp = row.bucket if type(row.bucket) is date else row.bucket.date()
            found[stamp] = _rupee0(row.value) if money else _int(row.value)
        points = []
        cursor = start
        total = 0
        while cursor <= end:
            value = found.get(cursor, 0)
            total += value
            points.append({
                "key": cursor.isoformat(),
                "label": cursor.strftime("%d %b"),
                "value": value,
            })
            cursor += timedelta(days=1)
        return points, total

    series_a, a_total = daily_series(a_start, a_end)
    series_b, b_total = daily_series(b_start, b_end)

    return {
        "metric": metric,
        "metric_label": DASHBOARD_METRICS[metric]["label"],
        "money": money,
        "filter_type": use_type,
        "filter_value": use_value,
        "dimension_label": dim_label,
        "mode": mode,
        "x_title": "Date",
        "period_a": {
            "from": a_start.isoformat(),
            "to": a_end.isoformat(),
            "total": a_total,
            "series": series_a,
        },
        "period_b": {
            "from": b_start.isoformat(),
            "to": b_end.isoformat(),
            "total": b_total,
            "series": series_b,
        },
        "change": percent_change(a_total, b_total),
        "series": [],
        "rows": [
            {"key": "period_a", "label": f"Period A ({a_start.isoformat()} – {a_end.isoformat()})", "value": a_total},
            {"key": "period_b", "label": f"Period B ({b_start.isoformat()} – {b_end.isoformat()})", "value": b_total},
        ],
        "total": a_total + b_total,
    }
