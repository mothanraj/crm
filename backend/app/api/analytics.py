"""Filter analytics dashboard API.

Aggregations run in PostgreSQL. The UI picks one filter type (category,
product, source, or progress), one value from the database, one metric, and
a time grain. Period A vs Period B is a separate comparison endpoint.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import User
from app.services.analytics import (
    DASHBOARD_METRICS,
    FILTER_TYPES,
    GRANULARITIES,
    build_filter_dashboard,
    build_filter_period_compare,
    build_overview,
    filter_option_values,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _require(u: User) -> None:
    if not u.role or u.role.name != "ADMIN":
        raise HTTPException(403, "Analytics is available to admins")


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field}") from exc


@router.get("/overview")
def analytics_overview(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    from_date: str | None = None,
    to_date: str | None = None,
    metric: str = "leads",
    filter_type: str | None = None,
    filter_value: str | None = None,
    category: str | None = None,
    progress: str | None = None,
    granularity: str | None = None,
):
    """GA-style overview: metric + optional dimension filter + trend grain."""
    _require(u)
    if metric not in DASHBOARD_METRICS:
        raise HTTPException(400, "Choose a metric")
    if filter_type:
        if filter_type not in FILTER_TYPES:
            raise HTTPException(400, "Filter type must be category, product, source, or progress")
        if not (filter_value or "").strip():
            raise HTTPException(400, "Choose a filter value")
    start = _parse_date(from_date, "from date")
    end = _parse_date(to_date, "to date")
    if not start or not end:
        raise HTTPException(400, "Choose a from date and a to date")
    if start > end:
        raise HTTPException(400, "From date must be on or before to date")
    if (end - start).days > 1100:
        raise HTTPException(400, "Choose a range of 3 years or less")
    if granularity and granularity not in GRANULARITIES:
        raise HTTPException(400, "Choose day, week, month, or year")
    try:
        return build_overview(
            db,
            from_date=start,
            to_date=end,
            metric=metric,
            filter_type=(filter_type or "").strip() or None,
            filter_value=(filter_value or "").strip() or None,
            category=(category or "").strip() or None,
            progress=(progress or "").strip() or None,
            granularity=granularity,
        )
    except ValueError as exc:
        raise HTTPException(400, "Invalid analytics request") from exc


@router.get("/filter-options")
def analytics_filter_options(
    filter_type: str = Query(..., alias="type"),
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
):
    _require(u)
    if filter_type not in FILTER_TYPES:
        raise HTTPException(400, "Filter type must be category, product, source, or progress")
    return {
        "type": filter_type,
        "values": filter_option_values(db, filter_type),
        "metrics": [
            {"id": key, "label": spec["label"], "money": spec["money"]}
            for key, spec in DASHBOARD_METRICS.items()
        ],
        "granularities": list(GRANULARITIES),
    }


@router.get("/dashboard")
def analytics_dashboard(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filter_type: str | None = None,
    filter_value: str | None = None,
    metric: str = "leads",
    granularity: str = "month",
    year: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    _require(u)
    if filter_type:
        if filter_type not in FILTER_TYPES:
            raise HTTPException(400, "Filter type must be category, product, source, or progress")
        if not (filter_value or "").strip():
            raise HTTPException(400, "Choose a filter value")
    if metric not in DASHBOARD_METRICS:
        raise HTTPException(400, "Choose a metric")
    if granularity not in GRANULARITIES:
        raise HTTPException(400, "Choose day, week, month, or year")
    start = _parse_date(from_date, "from date")
    end = _parse_date(to_date, "to date")
    if (start and not end) or (end and not start):
        raise HTTPException(400, "Provide both from and to dates, or neither")
    if start and end and start > end:
        raise HTTPException(400, "From date must be on or before to date")
    try:
        return build_filter_dashboard(
            db,
            filter_type,
            (filter_value or "").strip() or None,
            metric,
            granularity,
            year,
            start,
            end,
        )
    except ValueError as exc:
        raise HTTPException(400, "Invalid analytics request") from exc


@router.get("/period-compare")
def analytics_period_compare(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    filter_type: str | None = None,
    filter_value: str | None = None,
    category: str | None = None,
    progress: str | None = None,
    metric: str = "leads",
    a_from: str | None = None,
    a_to: str | None = None,
    b_from: str | None = None,
    b_to: str | None = None,
):
    _require(u)
    if filter_type:
        if filter_type not in FILTER_TYPES:
            raise HTTPException(400, "Filter type must be category, product, source, or progress")
        if not (filter_value or "").strip() and not ((category or "").strip() or (progress or "").strip()):
            raise HTTPException(400, "Choose a filter value")
    if metric not in DASHBOARD_METRICS:
        raise HTTPException(400, "Choose a metric")
    start_a = _parse_date(a_from, "period A from")
    end_a = _parse_date(a_to, "period A to")
    start_b = _parse_date(b_from, "period B from")
    end_b = _parse_date(b_to, "period B to")
    if not all([start_a, end_a, start_b, end_b]):
        raise HTTPException(400, "Period comparison needs from and to dates on both periods")
    if start_a > end_a or start_b > end_b:
        raise HTTPException(400, "A period starts after it ends")
    if (end_a - start_a).days > 1100 or (end_b - start_b).days > 1100:
        raise HTTPException(400, "Choose a range of 3 years or less")
    try:
        return build_filter_period_compare(
            db,
            (filter_type or "").strip() or None,
            (filter_value or "").strip() or None,
            metric,
            (start_a, end_a),
            (start_b, end_b),
            category=(category or "").strip() or None,
            progress=(progress or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(400, "Invalid period comparison") from exc
