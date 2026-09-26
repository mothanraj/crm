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

from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Integer, String, and_, case, cast, exists, func, or_
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
    "lead_value": {
        "label": "Lead Value",
        "measures": ("leads", "lead_value"),
        "default": "leads",
    },
    "quotation_value": {
        "label": "Quotation Value",
        "measures": ("quotations", "quotation_value"),
        "default": "quotations",
    },
    "progress": {"label": "Progress", "measures": ("leads",), "default": "leads"},
    "category": {"label": "Category", "measures": ("leads",), "default": "leads"},
    "product": {"label": "Product", "measures": ("leads",), "default": "leads"},
    "cars": {"label": "Cars", "measures": ("leads",), "default": "leads"},
}

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


def _progress_names(db: Session) -> list[str]:
    names = [name for (name,) in db.query(LeadStatus.name).order_by(LeadStatus.sort_order, LeadStatus.name).all()]
    if "Assigned" not in names:
        if "New Lead" in names:
            names.insert(names.index("New Lead"), "Assigned")
        else:
            names.insert(0, "Assigned")
    return names


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


def _product_names(db: Session) -> list[str]:
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
    for (name,) in db.query(Product.name).filter(Product.is_active.is_(True)).order_by(Product.name):
        if name not in stored:
            stored.append(name)
    return stored or ["Unmapped"]


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


def build_comparison(db: Session, f: LeadFilters, compare_by: str, measure: str | None = None) -> dict:
    """Month-by-year matrix, plus a dimension breakdown when compare-by is not a value.

    Every figure is the current lead. History, assignments, and quotation revisions
    are not joined, so one lead stays one lead. Quotation NULL is missing, not zero.
    """
    spec = COMPARE_OPTIONS.get(compare_by)
    if spec is None:
        raise ValueError(compare_by)
    chosen = measure if measure in spec["measures"] else spec["default"]
    years = sorted(set(f.years))
    months = sorted({m for m in f.months if 1 <= m <= 12}) or list(range(1, 13))
    year_no = func.extract("year", Lead.enquiry_date)
    month_no = func.extract("month", Lead.enquiry_date)
    grid_rows = (
        apply_filters(_base(db), f)
        .filter(Lead.enquiry_date.isnot(None))
        .with_entities(year_no.label("year"), month_no.label("month"), *_measure_cells())
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
    kind = None if compare_by in {"lead_value", "quotation_value"} else compare_by
    details: list[dict] = []
    if kind:
        expr = {"progress": status_expr, "category": category_expr, "product": product_expr, "cars": cars_expr}[kind]()
        label = expr.label("name")
        grouped = (
            apply_filters(_base(db), f)
            .filter(Lead.enquiry_date.isnot(None))
            .with_entities(label, year_no.label("year"), *_measure_cells())
            .group_by(label, year_no)
            .all()
        )
        found: dict[str, dict[str, int]] = {}
        for row in grouped:
            if not row.name or row.year is None:
                continue
            found.setdefault(str(row.name), {})[str(int(row.year))] = _picked(row, chosen)
        catalog = _comparison_catalog(db, kind, f, list(found))
        for name in catalog:
            values = {key: found.get(name, {}).get(key, 0) for key in year_keys}
            details.append({"name": name, "values": values})
        if kind == "product":
            details.sort(key=lambda item: (-sum(item["values"].values()), item["name"].lower()))
        elif kind == "cars":
            details.sort(key=lambda item: _cars_sort_key(item["name"]))
    kpi = _query_kpi(db, f)
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
        "detail_label": COMPARE_OPTIONS[kind]["label"] if kind else None,
        "kpi": kpi,
        "rules": {
            "date_field": "enquiry_date",
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
            .filter(User.is_active.is_(True), Role.name.in_(("EMPLOYEE", "MANAGER")))
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
