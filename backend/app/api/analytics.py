"""Analytics compare API — metric and/or dimension + year/month/date/period modes."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.session import get_db
from app.models import User
from app.services.analytics import (
    ANALYTICS_FILTER_MENUS,
    COMPARE_MODES,
    DASHBOARD_METRICS,
    FILTER_TYPES,
    analytics_meta,
    build_selection_compare,
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


def _parse_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError as exc:
            raise HTTPException(400, "Invalid number list") from exc
    return out


def _run_compare(
    db: Session,
    *,
    metric: str,
    filter_type: str | None,
    filter_value: str | None,
    mode: str,
    years: str | None,
    year: int | None,
    months: str | None,
    from_date: str | None,
    to_date: str | None,
    a_from: str | None,
    a_to: str | None,
    b_from: str | None,
    b_to: str | None,
) -> dict:
    if metric not in DASHBOARD_METRICS:
        raise HTTPException(400, "Choose a metric")
    use_type = (filter_type or "").strip() or None
    value = (filter_value or "").strip() or None
    if use_type:
        if use_type not in FILTER_TYPES:
            raise HTTPException(400, "Filter type must be category, product, progress, or source")
        if not value:
            raise HTTPException(400, "Choose a filter value")
        allowed = ANALYTICS_FILTER_MENUS.get(use_type) or []
        if allowed and value not in allowed:
            raise HTTPException(400, "Choose a valid filter value")
    elif value:
        raise HTTPException(400, "Choose a filter type with the value")
    if mode not in COMPARE_MODES:
        raise HTTPException(400, "Choose year, month, date, or period compare mode")

    try:
        if mode == "year":
            return build_selection_compare(
                db,
                metric=metric,
                filter_type=use_type,
                filter_value=value,
                mode=mode,
                years=_parse_int_list(years),
            )
        if mode == "month":
            if year is None:
                raise HTTPException(400, "Choose one year for month-wise compare")
            return build_selection_compare(
                db,
                metric=metric,
                filter_type=use_type,
                filter_value=value,
                mode=mode,
                year=year,
                months=_parse_int_list(months),
            )
        if mode == "date":
            start = _parse_date(from_date, "from date")
            end = _parse_date(to_date, "to date")
            if not start or not end:
                raise HTTPException(400, "Choose from date and to date")
            return build_selection_compare(
                db,
                metric=metric,
                filter_type=use_type,
                filter_value=value,
                mode=mode,
                from_date=start,
                to_date=end,
            )
        start_a = _parse_date(a_from, "period A from")
        end_a = _parse_date(a_to, "period A to")
        start_b = _parse_date(b_from, "period B from")
        end_b = _parse_date(b_to, "period B to")
        if not all([start_a, end_a, start_b, end_b]):
            raise HTTPException(400, "Period comparison needs from and to on both periods")
        return build_selection_compare(
            db,
            metric=metric,
            filter_type=use_type,
            filter_value=value,
            mode=mode,
            period_a=(start_a, end_a),
            period_b=(start_b, end_b),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        code = str(exc)
        messages = {
            "years": "Select at least one year",
            "years_limit": "Select up to 8 years",
            "year": "Choose one year",
            "months": "Select at least one month",
            "date_range": "Check the date range",
            "date_span": "Date range is too wide",
            "period": "Choose both periods",
            "filter_type": "Choose a filter type",
            "filter_value": "Choose a filter value",
        }
        raise HTTPException(400, messages.get(code, "Invalid analytics compare request")) from exc


@router.get("/meta")
def analytics_meta_endpoint(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
):
    _require(u)
    return analytics_meta(db)


@router.get("/compare")
def analytics_compare(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    metric: str = "leads",
    filter_type: str | None = Query(None, alias="type"),
    filter_value: str | None = Query(None, alias="value"),
    mode: str = "year",
    years: str | None = None,
    year: int | None = None,
    months: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    a_from: str | None = None,
    a_to: str | None = None,
    b_from: str | None = None,
    b_to: str | None = None,
):
    _require(u)
    return _run_compare(
        db,
        metric=metric,
        filter_type=filter_type,
        filter_value=filter_value,
        mode=mode,
        years=years,
        year=year,
        months=months,
        from_date=from_date,
        to_date=to_date,
        a_from=a_from,
        a_to=a_to,
        b_from=b_from,
        b_to=b_to,
    )


@router.get("/compare/pdf")
def analytics_compare_pdf(
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
    metric: str = "leads",
    filter_type: str | None = Query(None, alias="type"),
    filter_value: str | None = Query(None, alias="value"),
    mode: str = "year",
    years: str | None = None,
    year: int | None = None,
    months: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    a_from: str | None = None,
    a_to: str | None = None,
    b_from: str | None = None,
    b_to: str | None = None,
):
    _require(u)
    payload = _run_compare(
        db,
        metric=metric,
        filter_type=filter_type,
        filter_value=filter_value,
        mode=mode,
        years=years,
        year=year,
        months=months,
        from_date=from_date,
        to_date=to_date,
        a_from=a_from,
        a_to=a_to,
        b_from=b_from,
        b_to=b_to,
    )
    from app.services.analytics_pdf import build_analytics_compare_pdf

    content = build_analytics_compare_pdf(payload)
    label = (filter_value or metric or "all").replace(" ", "-")[:40]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)
    filename = f"analytics-{safe}-{mode}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
