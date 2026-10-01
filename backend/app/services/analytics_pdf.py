"""Single-page Analytics compare PDF with logo, clear charts, and neat spacing."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.report_pdf import _brand_logo, _page_header_fn

NAVY = colors.HexColor("#1e3a5f")
BLUE = colors.HexColor("#1971C2")
GREEN = colors.HexColor("#65A30D")
MUTED = colors.HexColor("#475569")
GRID = colors.HexColor("#e2e8f0")
BORDER = colors.HexColor("#cbd5e1")


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


def _line_chart(series: list[dict], *, title: str, color, width: float, height: float) -> Drawing:
    drawing = _chart_frame(width, height, title)
    if not series:
        drawing.add(String(width / 2, height / 2, "No data", textAnchor="middle", fontSize=10, fillColor=MUTED))
        return drawing

    rotate = len(series) > 6
    left = 58
    bottom = 48 if rotate else 36
    top = 30
    right = 18

    chart = HorizontalLineChart()
    chart.x = left
    chart.y = bottom
    chart.width = width - left - right
    chart.height = height - bottom - top
    chart.data = [[float(row.get("value") or 0) for row in series]]
    chart.categoryAxis.categoryNames = _x_labels(series)
    _style_axes(chart, rotate_x=rotate)
    chart.lines[0].strokeColor = color
    chart.lines[0].strokeWidth = 2.4
    chart.lines[0].symbol = None
    drawing.add(chart)
    return drawing


def _bar_chart(series: list[dict], *, title: str, color, width: float, height: float) -> Drawing:
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
    chart.data = [[float(row.get("value") or 0) for row in series]]
    chart.categoryAxis.categoryNames = _x_labels(series)
    _style_axes(chart, rotate_x=rotate)
    chart.bars[0].fillColor = color
    chart.bars[0].strokeColor = color
    chart.barWidth = max(8, min(22, (chart.width / max(len(series), 1)) * 0.55))
    chart.groupSpacing = 10
    chart.barSpacing = 2
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

    if period_mode:
        series_a = _downsample(list((payload.get("period_a") or {}).get("series") or []))
        series_b = _downsample(list((payload.get("period_b") or {}).get("series") or []))
        a_from = (payload.get("period_a") or {}).get("from")
        a_to = (payload.get("period_a") or {}).get("to")
        b_from = (payload.get("period_b") or {}).get("from")
        b_to = (payload.get("period_b") or {}).get("to")
        a_total = _fmt((payload.get("period_a") or {}).get("total"), money)
        b_total = _fmt((payload.get("period_b") or {}).get("total"), money)
        left = _line_chart(
            series_a,
            title=f"Period A  |  {a_from} – {a_to}  |  {a_total}",
            color=BLUE,
            width=chart_w,
            height=chart_h,
        )
        right = _line_chart(
            series_b,
            title=f"Period B  |  {b_from} – {b_to}  |  {b_total}",
            color=GREEN,
            width=chart_w,
            height=chart_h,
        )
        charts = Table(
            [[left, right]],
            colWidths=[chart_w + gap / 2, chart_w + gap / 2],
        )
    else:
        series = _downsample(list(payload.get("series") or []))
        line = _line_chart(series, title="Trend (line)", color=BLUE, width=chart_w, height=chart_h)
        bar = _bar_chart(series, title="Comparison (bar)", color=BLUE, width=chart_w, height=chart_h)
        charts = Table([[line, bar]], colWidths=[chart_w + gap / 2, chart_w + gap / 2])

    charts.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    rows = [["Label", metric_label]]
    if period_mode:
        rows = [["Period", "Total"]]
        for row in payload.get("rows") or []:
            rows.append([str(row.get("label") or ""), _fmt(row.get("value"), money)])
        change = payload.get("change")
        rows.append(["Change (A vs B)", "—" if change is None else f"{change:+.1f}%"])
    else:
        for row in payload.get("rows") or payload.get("series") or []:
            rows.append([str(row.get("label") or ""), _fmt(row.get("value"), money)])
        rows.append(["Total", _fmt(payload.get("total"), money)])

    # Keep comparison table compact on one page
    if len(rows) > 10:
        head, body, tail = rows[0], rows[1:-1], rows[-1:]
        step = max(1, len(body) // 8)
        body = body[::step][:8]
        rows = [head, *body, *tail]

    table = Table(rows, colWidths=[page_w * 0.58, page_w * 0.42])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eef5")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    note = Paragraph(
        "Y-axis uses compact units (k / L / Cr) when values are large so labels stay visible.",
        styles["note"],
    )

    story = [
        subtitle,
        charts,
        Spacer(1, 8),
        Paragraph("Comparison data", styles["h"]),
        table,
        note,
    ]
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buf.getvalue()
