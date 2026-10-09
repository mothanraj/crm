"""Single-page Analytics compare PDF with logo, clear charts, and neat spacing."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

from app.services.report_pdf import _brand_logo, _page_header_fn

NAVY = colors.HexColor("#1e3a5f")
BLUE = colors.HexColor("#1971C2")
GREEN = colors.HexColor("#65A30D")
MUTED = colors.HexColor("#475569")
GRID = colors.HexColor("#e2e8f0")
BORDER = colors.HexColor("#cbd5e1")

# Same hues as the web page so the PDF chart matches (frontend analytics.tsx).
SERIES_PALETTE = [
    "#1971C2", "#65A30D", "#E8890C", "#7C3AED", "#0e7490",
    "#DC2626", "#DB2777", "#0891B2", "#CA8A04",
]
PRODUCT_PDF_COLORS = {
    "Two Post Stack Parking": "#1971C2",
    "Four Post Stack Parking": "#0e7490",
    "Pit Stack Parking": "#65A30D",
    "Puzzle Parking": "#7C3AED",
    "Pit Puzzle Parking": "#DB2777",
    "Tower Parking": "#E8890C",
    "Shuttle Parking": "#0891B2",
    "Car Elevator": "#CA8A04",
    "ASRS Parking": "#DC2626",
}
CATEGORY_PDF_COLORS = {
    "A+ (Immediate)": "#D946EF",
    "A (3-6 months)": "#EC4899",
    "B (6-9 months)": "#6366F1",
    "C (Planning Stage)": "#64748B",
}


def group_color(key: str, index: int, group_by: str | None):
    """Web-parity color for one group series (category/product punya fixed hues)."""
    label = str(key or "")
    if group_by == "category" and label in CATEGORY_PDF_COLORS:
        return colors.HexColor(CATEGORY_PDF_COLORS[label])
    if group_by == "product" and label in PRODUCT_PDF_COLORS:
        return colors.HexColor(PRODUCT_PDF_COLORS[label])
    return colors.HexColor(SERIES_PALETTE[index % len(SERIES_PALETTE)])


def group_legend_paragraph(group_keys: list[str], group_by: str | None) -> Paragraph:
    """Centered color-key strip mirroring the web chart legend."""
    parts = []
    for i, key in enumerate(group_keys):
        c = group_color(key, i, group_by)
        try:
            hexcode = "%02x%02x%02x" % (
                int(c.red * 255), int(c.green * 255), int(c.blue * 255),
            )
        except Exception:
            hexcode = "1971C2"
        parts.append(f'<font color="#{hexcode}">■</font> {escape(str(key))}')
    style = ParagraphStyle(
        "legend", fontName="Helvetica", fontSize=8, leading=11,
        textColor=MUTED, alignment=1, spaceBefore=4, spaceAfter=2,
    )
    return Paragraph("&nbsp;&nbsp;&nbsp;".join(parts), style)


def _inr(n) -> str:
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    return f"Rs. {v:,}"


def _num(n) -> str:
    try:
        return f"{int(round(float(n or 0))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt(value, money: bool) -> str:
    return _inr(value) if money else _num(value)


def _axis_num(value) -> str:
    """Compact Y-axis labels so large rupee amounts stay readable."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 10_000_000:
        return f"{sign}{v / 10_000_000:.1f}Cr"
    if v >= 100_000:
        return f"{sign}{v / 100_000:.1f}L"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.0f}k"
    return f"{sign}{int(round(v))}"


def _downsample(series: list[dict], limit: int = 14) -> list[dict]:
    if len(series) <= limit:
        return series
    step = max(1, (len(series) - 1) // (limit - 1))
    out = [series[i] for i in range(0, len(series), step)]
    if out[-1] is not series[-1]:
        out.append(series[-1])
    return out[:limit]


def _x_labels(series: list[dict]) -> list[str]:
    labels = []
    for row in series:
        text = str(row.get("label") or "")
        # Keep year/month short; trim long date text
        if len(text) > 8:
            text = text[:8]
        labels.append(text)
    return labels


def _style_axes(chart, *, rotate_x: bool) -> None:
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = BORDER
    chart.categoryAxis.tickStrokeColor = BORDER
    if rotate_x:
        chart.categoryAxis.labels.angle = 35
        chart.categoryAxis.labels.boxAnchor = "ne"
        chart.categoryAxis.labels.dx = -1
        chart.categoryAxis.labels.dy = -2
    else:
        chart.categoryAxis.labels.angle = 0
        chart.categoryAxis.labels.boxAnchor = "n"
        chart.categoryAxis.labels.dy = -4

    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = BORDER
    chart.valueAxis.tickStrokeColor = BORDER
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.gridStrokeWidth = 0.6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = _axis_num
    chart.valueAxis.forceZero = True


def _chart_frame(width: float, height: float, title: str) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(Rect(
        0, 0, width, height,
        fillColor=colors.white,
        strokeColor=BORDER,
        strokeWidth=0.8,
    ))
    drawing.add(String(14, height - 16, title, fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY))
    drawing.add(Line(10, height - 22, width - 10, height - 22, strokeColor=GRID, strokeWidth=0.7))
    return drawing


def _bar_chart(
    series: list[dict],
    *,
    title: str,
    color,
    width: float,
    height: float,
    group_keys: list[str] | None = None,
    group_by: str | None = None,
    money: bool = False,
) -> Drawing:
    drawing = _chart_frame(width, height, title)
    if not series:
        drawing.add(String(width / 2, height / 2, "No data", textAnchor="middle", fontSize=10, fillColor=MUTED))
        return drawing

    rotate = len(series) > 6
    left = 58
    bottom = 48 if rotate else 36
    top = 30
    right = 18

    chart = VerticalBarChart()
    chart.x = left
    chart.y = bottom
    chart.width = width - left - right
    chart.height = height - bottom - top
    groups = [str(k) for k in (group_keys or []) if k]
    if groups:
        # Grouped columns: one series per group key, like the web chart.
        chart.data = [[float(row.get(g) or 0) for row in series] for g in groups]
        for i, g in enumerate(groups):
            chart.bars[i].fillColor = group_color(g, i, group_by)
            chart.bars[i].strokeColor = group_color(g, i, group_by)
        chart.barWidth = max(4, min(12, (chart.width / max(len(series) * len(groups), 1)) * 0.7))
        chart.groupSpacing = 8
        chart.barSpacing = 1.5
    else:
        chart.data = [[float(row.get("value") or 0) for row in series]]
        chart.bars[0].fillColor = color
        chart.bars[0].strokeColor = color
        chart.barWidth = max(8, min(22, (chart.width / max(len(series), 1)) * 0.55))
        chart.groupSpacing = 10
        chart.barSpacing = 2
    chart.categoryAxis.categoryNames = _x_labels(series)
    _style_axes(chart, rotate_x=rotate)
    # Number labels above each bar (raw values, like the web chart).
    data_max = max((v for row in chart.data for v in row), default=0)
    if data_max:
        chart.valueAxis.valueMax = data_max * 1.2
        chart.barLabelFormat = (
            lambda v, _m=money: _fmt(v, _m) if v else ""
        )
        chart.barLabels.nudge = 10
        chart.barLabels.fontSize = 7
    drawing.add(chart)
    return drawing


def build_analytics_compare_pdf(payload: dict) -> bytes:
    page = landscape(A4)
    width, height = page
    margin = 36
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=112,
        bottomMargin=28,
        title="Analytics comparison",
        author="ESTAR Engineers Pvt Ltd",
    )
    page_w = width - (margin * 2)
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(
        logo, logo_iw, logo_ih, "Analytics", generated, width, height, doc,
    )

    styles = {
        "meta": ParagraphStyle(
            "meta", fontName="Helvetica", fontSize=10, leading=13,
            textColor=colors.HexColor("#334155"), alignment=1, spaceAfter=8,
        ),
        "h": ParagraphStyle(
            "h", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY,
            spaceBefore=8, spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "note", fontName="Helvetica", fontSize=8, textColor=MUTED, alignment=1, spaceBefore=4,
        ),
    }

    money = bool(payload.get("money"))
    period_mode = payload.get("mode") == "period"
    mode_label = {
        "year": "Year wise",
        "month": "Month wise",
        "date": "Date wise",
        "period": "From–to vs From–to",
    }.get(payload.get("mode"), payload.get("mode") or "")

    if payload.get("group_by"):
        scope_text = payload.get("dimension_label") or (
            "Category group wise" if payload.get("group_by") == "category" else "Product group wise"
        )
    else:
        scope = payload.get("filter_value")
        scope_text = f"{payload.get('dimension_label')}: {scope}" if scope else "All leads"
    metric_label = payload.get("metric_label") or "Value"

    subtitle = Paragraph(
        escape(f"{metric_label}  ·  {scope_text}  ·  {mode_label}"),
        styles["meta"],
    )

    gap = 8 * mm
    chart_w = (page_w - gap) / 2
    # Tall enough for axis labels; one chart row so logo + table stay on one page.
    chart_h = 100 * mm

    group_by = (payload.get("group_by") or "").strip() or None
    group_keys = [str(k) for k in (payload.get("group_keys") or []) if k]

    if period_mode:
        series_a = _downsample(list((payload.get("period_a") or {}).get("series") or []))
        series_b = _downsample(list((payload.get("period_b") or {}).get("series") or []))
        a_from = (payload.get("period_a") or {}).get("from")
        a_to = (payload.get("period_a") or {}).get("to")
        b_from = (payload.get("period_b") or {}).get("from")
        b_to = (payload.get("period_b") or {}).get("to")
        a_total = _fmt((payload.get("period_a") or {}).get("total"), money)
        b_total = _fmt((payload.get("period_b") or {}).get("total"), money)
        left = _bar_chart(
            series_a,
            title=f"Period A  |  {a_from} – {a_to}  |  {a_total}",
            color=BLUE,
            width=chart_w,
            height=chart_h,
            group_keys=group_keys,
            group_by=group_by,
            money=money,
        )
        right = _bar_chart(
            series_b,
            title=f"Period B  |  {b_from} – {b_to}  |  {b_total}",
            color=GREEN,
            width=chart_w,
            height=chart_h,
            group_keys=group_keys,
            group_by=group_by,
            money=money,
        )
        charts = Table(
            [[left, right]],
            colWidths=[chart_w + gap / 2, chart_w + gap / 2],
        )
    else:
        series = _downsample(list(payload.get("series") or []))
        bar = _bar_chart(
            series,
            title="Grouped Column Chart",
            color=BLUE,
            width=page_w,
            height=chart_h,
            group_keys=group_keys,
            group_by=group_by,
            money=money,
        )
        charts = Table([[bar]], colWidths=[page_w])

    legend = group_legend_paragraph(group_keys, group_by) if group_keys else None

    charts.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    if period_mode and group_keys:
        rows = [["Group", "Period A", "Period B"]]
        map_a = {str(r.get("key")): r.get("value") for r in ((payload.get("period_a") or {}).get("series") or [])}
        map_b = {str(r.get("key")): r.get("value") for r in ((payload.get("period_b") or {}).get("series") or [])}
        for key in group_keys:
            rows.append([key, _fmt(map_a.get(key), money), _fmt(map_b.get(key), money)])
        change = payload.get("change")
        rows.append([
            "TOTAL / Change",
            _fmt((payload.get("period_a") or {}).get("total"), money),
            ("—" if change is None else f"{change:+.1f}%") + f"  ({_fmt((payload.get('period_b') or {}).get('total'), money)})",
        ])
    elif period_mode:
        rows = [["Period", "Total"]]
        for row in payload.get("rows") or []:
            rows.append([str(row.get("label") or ""), _fmt(row.get("value"), money)])
        change = payload.get("change")
        rows.append(["Change (A vs B)", "—" if change is None else f"{change:+.1f}%"])
    elif group_keys:
        short = [((k[:14] + "…") if len(k) > 15 else k) for k in group_keys]
        rows = [["Label", *short, "Total"]]
        for row in payload.get("rows") or payload.get("series") or []:
            rows.append([
                str(row.get("label") or ""),
                *[_fmt(row.get(k), money) for k in group_keys],
                _fmt(row.get("value"), money),
            ])
        col_totals = []
        body_rows = payload.get("rows") or payload.get("series") or []
        for k in group_keys:
            col_totals.append(_fmt(sum(int(r.get(k) or 0) for r in body_rows), money))
        rows.append(["Total", *col_totals, _fmt(payload.get("total"), money)])
    else:
        rows = [["Label", metric_label]]
        for row in payload.get("rows") or payload.get("series") or []:
            rows.append([str(row.get("label") or ""), _fmt(row.get("value"), money)])
        rows.append(["Total", _fmt(payload.get("total"), money)])

    # Keep comparison table compact on one page
    if len(rows) > 12 and not group_keys:
        head, body, tail = rows[0], rows[1:-1], rows[-1:]
        step = max(1, len(body) // 8)
        body = body[::step][:8]
        rows = [head, *body, *tail]

    col_count = max(2, len(rows[0]))
    first_w = page_w * (0.28 if col_count > 3 else 0.58)
    rest_w = (page_w - first_w) / max(1, col_count - 1)
    table = Table(rows, colWidths=[first_w] + [rest_w] * (col_count - 1))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eef5")),
        ("FONTSIZE", (0, 0), (-1, -1), 7 if col_count > 4 else 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 if col_count > 4 else 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 if col_count > 4 else 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    table.hAlign = "CENTER"

    note = Paragraph(
        "Y-axis uses compact units (k / L / Cr) when values are large so labels stay visible.",
        styles["note"],
    )

    # Page 1: chart only. Page 2: comparison table only.
    story = [
        subtitle,
        charts,
    ]
    if legend is not None:
        story.append(legend)
    story += [
        note,
        PageBreak(),
        Paragraph("Comparison data", styles["h"]),
        table,
    ]
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buf.getvalue()
