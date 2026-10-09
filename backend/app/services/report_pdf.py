"""Branded, paginated lead report downloads."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Circle, Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


LOGO = Path(__file__).resolve().parents[1] / "assets" / "company-logo.jpg"
NAVY = colors.HexColor("#1e3a5f")
GREEN = colors.HexColor("#3F6212")
KEYS = ("total", "in_followup", "meeting", "site_visit", "quote_sent", "converted", "not_interested")
CHART_COLORS = [
    colors.HexColor("#1971C2"),
    colors.HexColor("#65A30D"),
    colors.HexColor("#7c3aed"),
    colors.HexColor("#E8890C"),
    colors.HexColor("#0e7490"),
    colors.HexColor("#c0392b"),
    colors.HexColor("#0369a1"),
    colors.HexColor("#3F6212"),
]


def _brand_logo() -> ImageReader:
    """Load the E-Star logo, trimming white margins so it fits the PDF header."""
    if not LOGO.exists():
        raise FileNotFoundError(f"Company logo missing: {LOGO}")
    try:
        from PIL import Image

        im = Image.open(LOGO).convert("RGB")
        pixels = im.load()
        w, h = im.size
        minx, miny, maxx, maxy = w, h, 0, 0
        found = False
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                if r < 245 or g < 245 or b < 245:
                    found = True
                    if x < minx:
                        minx = x
                    if y < miny:
                        miny = y
                    if x > maxx:
                        maxx = x
                    if y > maxy:
                        maxy = y
        if found:
            pad = 8
            im = im.crop((
                max(0, minx - pad),
                max(0, miny - pad),
                min(w, maxx + 1 + pad),
                min(h, maxy + 1 + pad),
            ))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return ImageReader(str(LOGO))


def _inr(n) -> str:
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    # Whole rupees only — no paise / .00
    s = f"{v:,}"
    return f"Rs. {s}"


def _centered_table_style(header_color=NAVY) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#edf4fa")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dce6ef")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, header_color),
    ])


def _page_header_fn(logo, logo_iw, logo_ih, title: str, generated: str, width, height, doc):
    def page_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, height - 85, width, 85, fill=1, stroke=0)
        max_w, max_h = 300, 58
        scale = min(max_w / float(logo_iw), max_h / float(logo_ih))
        draw_w, draw_h = logo_iw * scale, logo_ih * scale
        canvas.drawImage(
            logo, 36, height - 14 - draw_h, width=draw_w, height=draw_h,
            mask="auto", preserveAspectRatio=True, anchor="c",
        )
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawRightString(width - 36, height - 42, title.upper())
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - 36, height - 64, f"Generated: {generated}")
        canvas.setStrokeColor(NAVY)
        canvas.line(36, height - 94, width - 36, height - 94)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(36, 24, title)
        canvas.drawRightString(width - 36, 24, f"Page {doc.page}")
        canvas.restoreState()
    return page_header


def _comparison_line_chart(
    months: list[dict],
    years: list[str],
    by_month: dict,
    focus: dict | None,
    chart_width: float,
) -> Drawing | None:
    """Month × year line chart, sized to match the table width below it."""
    if not months or not years:
        return None
    series = []
    labels = []
    peak = 0.0
    for year in years:
        points = []
        for month in months:
            if focus:
                match = by_month.get(month.get("month")) or {}
                found = next(
                    (row for row in (match.get("items") or []) if row.get("name") == focus.get("name")),
                    {},
                )
                values = found.get("values") or {}
            else:
                values = month.get("values") or {}
            try:
                value = float(values.get(year, 0) or 0)
            except (TypeError, ValueError):
                value = 0.0
            points.append(value)
            if value > peak:
                peak = value
        series.append(points)
        labels.append(year)

    # Leave room for Y labels on the left and a centered legend under the plot.
    left_pad = 54
    right_pad = 18
    top_pad = 22
    legend_h = 28
    plot_h = 168
    drawing_h = top_pad + plot_h + legend_h + 18
    plot_w = max(220.0, chart_width - left_pad - right_pad)

    drawing = Drawing(chart_width, drawing_h)
    chart = HorizontalLineChart()
    chart.x = left_pad
    chart.y = legend_h + 10
    chart.height = plot_h
    chart.width = plot_w
    chart.data = series
    chart.joinedLines = 1
    chart.categoryAxis.categoryNames = [str(month.get("name") or "")[:3] for month in months]
    chart.categoryAxis.labels.boxAnchor = "n"
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.labels.angle = 0
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.strokeColor = colors.HexColor("#94a3b8")
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = peak * 1.15 if peak > 0 else 1
    chart.valueAxis.valueSteps = None
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.strokeColor = colors.HexColor("#94a3b8")
    chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    chart.valueAxis.gridStrokeWidth = 0.5
    chart.lines.strokeWidth = 2.2
    for index, _year in enumerate(years):
        chart.lines[index].strokeColor = CHART_COLORS[index % len(CHART_COLORS)]
    drawing.add(chart)

    legend = Legend()
    legend.alignment = "right"
    legend.fontName = "Helvetica"
    legend.fontSize = 8
    legend.dx = 8
    legend.dy = 8
    legend.dxTextSpace = 4
    legend.deltax = min(90, max(60, plot_w / max(len(labels), 1)))
    legend.deltay = 12
    legend.columnMaximum = max(1, (len(labels) + 1) // 2) if len(labels) > 4 else len(labels)
    legend.colorNamePairs = [
        (CHART_COLORS[index % len(CHART_COLORS)], str(labels[index]))
        for index in range(len(labels))
    ]
    # Center the legend under the plot area.
    legend_width = legend.deltax * min(len(labels), legend.columnMaximum)
    legend.x = left_pad + max(0, (plot_w - legend_width) / 2)
    legend.y = 8
    drawing.add(legend)
    drawing.add(String(left_pad, drawing_h - 12, "Monthly comparison", fontSize=9, fillColor=NAVY))
    return drawing


def build_comparison_pdf(payload: dict, item: str | None = None) -> bytes:
    """Year-by-month comparison PDF.

    Chart and data table are always on separate pages.
    For Progress / Category / Product / Source:
    - one chosen type → chart page then table page for that type
    - no type chosen → every type gets its own chart page and table page
    For lead / quotation measures → one chart page, then one table page.
    """
    title = "Lead Comparison"
    years = [str(year) for year in (payload.get("years") or [])]
    page = landscape(A4)
    width, height = page
    margin = 40
    usable = width - (margin * 2)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=page, leftMargin=margin, rightMargin=margin,
        topMargin=118, bottomMargin=36, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5, alignment=1)
    left = ParagraphStyle("left", parent=cell, alignment=0)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY,
        spaceAfter=2, alignment=1,
    )
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"), spaceAfter=1,
    )
    section = ParagraphStyle(
        "section", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY,
        spaceBefore=4, spaceAfter=8, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    money = bool(payload.get("money"))
    label = str(payload.get("compare_label") or "Comparison")
    year_text = " vs ".join(years) if years else "All years"
    months = payload.get("months") or []
    by_month = {row.get("month"): row for row in (payload.get("by_month") or [])}
    details = payload.get("details") or []
    chosen = (item or "").strip()

    def fmt(value) -> str:
        if money:
            return _inr(value)
        try:
            return f"{int(value or 0):,}"
        except (TypeError, ValueError):
            return "0"

    def month_table(focus: dict | None):
        head = [Paragraph("Month", header)] + [Paragraph(escape(year), header) for year in years]
        body = [head]
        for month in months:
            if focus:
                match = by_month.get(month.get("month")) or {}
                found = next(
                    (row for row in (match.get("items") or []) if row.get("name") == focus.get("name")),
                    {},
                )
                values = found.get("values") or {}
            else:
                values = month.get("values") or {}
            body.append([
                Paragraph(escape(str(month.get("name") or "")), left),
                *[Paragraph(fmt(values.get(year, 0)), cell) for year in years],
            ])
        totals = (focus or {}).get("values") if focus else (payload.get("selected_total") or {})
        body.append([
            Paragraph("Total", left),
            *[Paragraph(fmt((totals or {}).get(year, 0)), cell) for year in years],
        ])
        name_w = min(120, usable * 0.18)
        rest = (usable - name_w) / max(len(years), 1)
        table = Table(body, colWidths=[name_w, *([rest] * len(years))], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#edf4fa")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dce6ef")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        return table

    def append_section(story: list, focus: dict | None, subject: str, *, first: bool) -> None:
        if not first:
            story.append(PageBreak())
        story.extend([
            Paragraph(title, heading),
            Paragraph(escape(subject), meta),
            Paragraph(escape(year_text), meta),
            Spacer(1, 6),
            Paragraph("Chart", section),
        ])
        chart = _comparison_line_chart(months, years, by_month, focus, usable)
        if chart is not None:
            story.append(chart)
        else:
            story.append(Paragraph("No chart data for this selection.", meta))
        story.append(PageBreak())
        story.extend([
            Paragraph(title, heading),
            Paragraph(escape(subject), meta),
            Paragraph(escape(year_text), meta),
            Spacer(1, 6),
            Paragraph("Monthly data", section),
            month_table(focus),
        ])

    story: list = []
    if details:
        if chosen:
            focuses = [row for row in details if row.get("name") == chosen]
            if not focuses:
                focuses = details
        else:
            focuses = details
        for index, focus in enumerate(focuses):
            name = str(focus.get("name") or "—")
            append_section(story, focus, f"{label} · {name}", first=index == 0)
    else:
        append_section(story, None, label, first=True)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_employee_period_pdf(payload: dict) -> bytes:
    """One employee's progress and category counts for a month or a week."""
    title = "Employee Work Report"
    buffer = BytesIO()
    width, height = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=36, rightMargin=36,
        topMargin=122, bottomMargin=42, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=10, leading=13, alignment=1)
    left = ParagraphStyle("left", parent=cell, alignment=0)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=14, textColor=NAVY,
        spaceAfter=6, alignment=1,
    )
    subhead = ParagraphStyle(
        "subhead", fontName="Helvetica-Bold", fontSize=12, textColor=NAVY,
        spaceBefore=14, spaceAfter=8, alignment=0,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=10, leading=14, alignment=1, textColor=colors.HexColor("#334155"))

    def pretty(iso: str) -> str:
        try:
            return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return str(iso or "—")

    mode = "Weekly" if payload.get("mode") == "week" else "Monthly"
    story = [
        Paragraph(title, heading),
        Paragraph(escape(str(payload.get("employee") or "Employee")), meta),
        Paragraph(
            escape(f"{mode}  ·  {pretty(payload.get('from'))} to {pretty(payload.get('to'))}"),
            meta,
        ),
        Spacer(1, 8),
    ]

    def count_table(section: str, rows: list) -> None:
        story.append(Paragraph(section, subhead))
        body = [[Paragraph(h, header) for h in ("Name", "Count")]]
        for row in rows or []:
            body.append([
                Paragraph(escape(str(row.get("label") or "—")), left),
                Paragraph(str(int(row.get("count") or 0)), cell),
            ])
        if len(body) == 1:
            body.append([Paragraph("No data", left), Paragraph("0", cell)])
        table = Table(body, colWidths=[(width - 72) * 0.72, (width - 72) * 0.28], hAlign="CENTER")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#edf4fa")]),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)

    count_table("Category", payload.get("category") or [])
    count_table("Progress", payload.get("progress") or [])

    def money(v) -> str:
        try:
            n = int(round(float(v or 0)))
        except (TypeError, ValueError):
            n = 0
        return f"Rs. {n:,}"

    story.append(Paragraph("Values", subhead))
    value_body = [[Paragraph(h, header) for h in ("Metric", "Amount")]]
    progress_counts = {str(row.get("label") or ""): int(row.get("count") or 0) for row in (payload.get("progress") or [])}
    quotation_sent = progress_counts.get("Quotation sent", 0)
    converted = progress_counts.get("Converted", 0)
    conversion_ratio = f"{(converted / quotation_sent * 100):.1f}%" if quotation_sent else "0.0%"
    for label, key in (
        ("Total lead value", "total_lead_value"),
        ("Total quotation value", "total_quotation_value"),
        ("Total converted value", "converted_quotation_value"),
    ):
        value_body.append([
            Paragraph(escape(label), left),
            Paragraph(money(payload.get(key)), cell),
        ])
    value_body.append([
        Paragraph("Conversion ratio", left),
        Paragraph(conversion_ratio, cell),
    ])
    value_table = Table(value_body, colWidths=[(width - 72) * 0.72, (width - 72) * 0.28], hAlign="CENTER")
    value_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#edf4fa")]),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(value_table)
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def _label_for_axis(text: str, max_len: int = 18) -> str:
    label = " ".join(str(text or "").split())
    if len(label) <= max_len:
        return label
    return label[: max_len - 1].rstrip() + "…"


def _axis_label(text: str, max_len: int = 18) -> str:
    """ASCII-safe short axis label (Helvetica/WinAnsi cannot draw …)."""
    label = " ".join(str(text or "").split())
    if len(label) <= max_len:
        return label
    return label[: max_len - 3].rstrip() + "..."


def _share_caption(prefix: str, pairs: list[tuple[str, float]]) -> str:
    """'Share of …: A 33% · B 17% …' line for under-chart captions."""
    tot = sum(float(v or 0) for _, v in pairs)
    if tot <= 0:
        return ""
    parts = [f"{lab} {float(v) / tot * 100:.0f}%" for lab, v in pairs if float(v or 0) > 0]
    return f"{prefix}: " + " · ".join(parts)


def _vertical_bar_chart(
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    chart_width: float,
    title: str,
    value_format: str = "%d",
    show_values: bool = True,
) -> Drawing | None:
    """Grouped vertical bars mirroring the webpage charts — one colour per
    series, counts on bars, centred legend on top, angled names below.

    series: list of (legend name, values per label, hex colour).
    All-zero rows are dropped from the chart only (tables keep full set).
    """
    series = [(nm, [float(v or 0) for v in vals], col) for nm, vals, col in series]
    keep = [i for i in range(len(labels)) if any(vals[i] > 0 for _, vals, _ in series)]
    if not keep:
        return None
    labels = [str(labels[i] or "") for i in keep]
    series = [(nm, [vals[i] for i in keep], col) for nm, vals, col in series]
    peak = max(v for _, vals, _ in series for v in vals)
    if peak <= 0:
        return None
    n = len(labels)
    ns = len(series)
    chart_w = min(float(chart_width), 750.0)
    # Legend rows (9pt names), greedily wrapped and centred.
    leg_fs = 9
    items_w = [10.0 + 4.0 + stringWidth(nm, "Helvetica", leg_fs) for nm, _, _ in series]
    leg_rows: list[list[int]] = []
    cur: list[int] = []
    cur_w = 0.0
    for i, w in enumerate(items_w):
        add = w + (18.0 if cur else 0.0)
        if cur and cur_w + add > chart_w - 20.0:
            leg_rows.append(cur)
            cur = [i]
            cur_w = w
        else:
            cur.append(i)
            cur_w += add
    if cur:
        leg_rows.append(cur)
    leg_h = len(leg_rows) * 15.0 + 6.0
    left_pad, right_pad, top_pad = 52.0, 16.0, 26.0
    label_band = 84.0 if n > 4 else 66.0
    plot_h = 190.0
    plot_w = max(240.0, chart_w - left_pad - right_pad)
    drawing_h = top_pad + leg_h + 6.0 + plot_h + label_band + 8.0
    drawing = Drawing(chart_w, drawing_h)
    drawing.hAlign = "CENTER"

    chart = VerticalBarChart()
    chart.x = left_pad
    chart.y = label_band
    chart.height = plot_h
    chart.width = plot_w
    chart.data = [list(vals) for _, vals, _ in series]
    chart.strokeColor = colors.white
    bw = min(14.0, max(3.0, plot_w / max(n * (ns + 1.5), 1)))
    chart.barWidth = bw
    chart.groupSpacing = bw * 1.5
    chart.barSpacing = 1.5
    for i, (_, _, col) in enumerate(series):
        chart.bars[i].fillColor = colors.HexColor(col)
        chart.bars[i].strokeColor = colors.HexColor(col)

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = peak * 1.28
    chart.valueAxis.valueSteps = None
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.strokeColor = colors.HexColor("#94a3b8")
    chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    chart.valueAxis.gridStrokeWidth = 0.5

    chart.categoryAxis.categoryNames = [_axis_label(name) for name in labels]
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.angle = 35
    chart.categoryAxis.labels.dx = -2
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.labels.fontSize = 7 if n > 8 else 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.strokeColor = colors.HexColor("#94a3b8")

    if show_values:
        chart.barLabels.nudge = 8
        chart.barLabelFormat = value_format
        chart.barLabels.fontName = "Helvetica-Bold"
        chart.barLabels.fontSize = 6 if (ns > 1 or n > 6) else 8
        chart.barLabels.fillColor = NAVY

    drawing.add(chart)
    # Centred legend rows above the plot.
    leg_top = label_band + plot_h + 6.0 + leg_h
    for r, row in enumerate(leg_rows):
        row_w = sum(items_w[i] for i in row) + 18.0 * (len(row) - 1)
        x = (chart_w - row_w) / 2
        y = leg_top - 8.0 - r * 15.0
        for i in row:
            nm, _, col = series[i]
            sw = Rect(x, y - 1, 10, 10)
            sw.fillColor = colors.HexColor(col)
            sw.strokeColor = colors.HexColor(col)
            sw.strokeWidth = 0
            drawing.add(sw)
            drawing.add(String(x + 14, y, nm, fontSize=leg_fs, fillColor=colors.HexColor("#334155")))
            x += items_w[i] + 18.0
    drawing.add(String(chart_w / 2, drawing_h - 14, escape(title), fontSize=10, fillColor=NAVY, textAnchor="middle"))
    return drawing


def _donut_chart(
    labels: list[str],
    values: list[float],
    chart_width: float,
    title: str,
) -> Drawing | None:
    """Donut (pie with hole) beside its legend — mirrors the UI donut.

    Horizontal layout (pie left, wordings right) so the drawing stays short
    enough to share its page with the section heading — never orphaned onto
    a blank page. Percent labels are drawn inside slices; full names with
    counts go in the legend beside the pie.
    """
    pairs = [(str(lab or ""), float(val or 0)) for lab, val in zip(labels, values)]
    pairs = [(lab, val) for lab, val in pairs if val > 0]
    if not pairs:
        return None
    total = sum(val for _, val in pairs)
    if total <= 0:
        return None
    n = len(pairs)
    # Fit inside the printable frame (~757 x ~419 on landscape A4 with the
    # report header/margins): cap the drawing width; side-by-side layout
    # keeps the height small so the flowable never raises LayoutError.
    chart_w = min(float(chart_width), 750.0)

    def _legend_raw(raw: str, max_len: int = 30) -> str:
        label = " ".join(str(raw or "").split())
        if len(label) > max_len:
            label = label[: max_len - 3].rstrip() + "..."
        return label
    texts = [f"{_legend_raw(lab)} ({int(val)})" for lab, val in pairs]
    # Bound the legend height: extra entries collapse into a "+N more" line.
    max_rows = 14
    shown = list(zip(pairs, texts))
    extra = 0
    if len(shown) > max_rows:
        extra = len(shown) - max_rows
        shown = shown[:max_rows]
    row_h = 18.0
    legend_h = len(shown) * row_h + (row_h if extra else 0.0)
    pie_size = 230.0
    content_h = max(pie_size, legend_h)
    pad_top, pad_bottom = 14.0, 14.0
    drawing_h = content_h + pad_top + pad_bottom
    drawing = Drawing(chart_w, drawing_h)
    drawing.hAlign = "CENTER"
    # Pie on the left; shifted with the legend below so the group centres.
    pie = Pie()
    pie.width = pie_size
    pie.height = pie_size
    pie.x = 0.0
    pie.y = pad_bottom + (content_h - pie_size) / 2
    pie.data = [val for _, val in pairs]
    pie.labels = [f"{(val / total * 100):.0f}%" for _, val in pairs]
    pie.slices.strokeWidth = 1.5
    pie.slices.strokeColor = colors.white
    pie.slices.fontSize = 12
    pie.slices.fontName = "Helvetica-Bold"
    pie.slices.fontColor = colors.white
    # Labels sit in the visible ring band (hole edge is at 0.52 of the
    # radius; the white hole circle is drawn on top, so the default
    # centre-placed labels would be hidden underneath it).
    pie.slices.labelRadius = 0.75
    pie.sideLabels = False
    pie.slices.popout = 0
    for i, (_lab, _val) in enumerate(pairs):
        pie.slices[i].fillColor = CHART_COLORS[i % len(CHART_COLORS)]
    drawing.add(pie)
    # Donut hole: white circle over the pie centre.
    cx = pie.x + pie_size / 2
    cy = pie.y + pie_size / 2
    hole = Circle(cx, cy, pie_size * 0.26)
    hole.fillColor = colors.white
    hole.strokeColor = colors.white
    hole.strokeWidth = 0
    drawing.add(hole)
    # Legend column on the right, vertically centred against the pie.
    # All text is XML-escaped and ASCII-safe (Helvetica/WinAnsi cannot
    # draw glyphs like ■ or …); swatches are drawn Rects, not glyphs.
    # Centre the pie+legend group on the page: measure the widest legend
    # line and shift both so the group midpoint sits on the drawing centre.
    max_text_w = max(
        (stringWidth(t, "Helvetica", 11) for _, t in shown), default=0.0,
    )
    if extra:
        max_text_w = max(max_text_w, stringWidth(f"+{extra} more", "Helvetica", 11))
    legend_block_w = 11.0 + 5.0 + max_text_w
    content_w = pie_size + 30.0 + legend_block_w
    shift = (chart_w - content_w) / 2 - pie.x
    pie.x += shift
    hole.cx += shift
    legend_x = pie.x + pie_size + 30.0
    legend_top = pad_bottom + (content_h - legend_h) / 2 + legend_h
    for i, ((lab, val), text) in enumerate(zip(pairs, texts)):
        if i >= max_rows:
            break
        y = legend_top - 8.0 - i * row_h
        swatch = Rect(legend_x, y - 1, 11, 11)
        swatch.fillColor = CHART_COLORS[i % len(CHART_COLORS)]
        swatch.strokeColor = CHART_COLORS[i % len(CHART_COLORS)]
        swatch.strokeWidth = 0
        drawing.add(swatch)
        drawing.add(String(
            legend_x + 16, y + 1,
            escape(text),
            fontSize=11, fillColor=colors.HexColor("#334155"),
        ))
    if extra:
        y = legend_top - 8.0 - len(shown) * row_h
        drawing.add(String(
            legend_x, y + 1,
            escape(f"+{extra} more"),
            fontSize=11, fillColor=colors.HexColor("#334155"),
        ))
    return drawing


def build_dashboard_history_pdf(payload: dict) -> bytes:
    """KPI tiles + source/product/category tables and charts for Dashboard History."""
    title = "Dashboard History Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=36,
        rightMargin=36, topMargin=122, bottomMargin=42,
        title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5, alignment=1)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.HexColor("#0f766e"), spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12,
        alignment=1, textColor=colors.HexColor("#334155"),
    )
    kpi_val = ParagraphStyle(
        "kpi_val", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=1, textColor=NAVY,
    )
    kpi_lbl = ParagraphStyle(
        "kpi_lbl", fontName="Helvetica", fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#475569"),
    )

    t = payload.get("tiles") or {}
    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('effective_from') or 'All'} → {payload.get('effective_to') or 'All'}"
        f"  ·  Mode: {payload.get('mode') or 'custom'}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 8))

    count_items = [
        ("Total Leads", str(t.get("total_leads") or 0)),
        ("Pending", str(t.get("pending") or 0)),
        ("In Followup", str(t.get("in_followup") or 0)),
        ("Meeting", str(t.get("meeting") or 0)),
        ("Site Visit", str(t.get("site_visit") or 0)),
        ("Quotation Sent", str(t.get("quote_sent") or 0)),
        ("Converted", str(t.get("converted") or 0)),
        ("Not Interested", str(t.get("not_interested") or 0)),
        ("No. of Cars", str(t.get("total_cars") or 0)),
    ]
    count_table = Table(
        [
            [Paragraph(lbl, kpi_lbl) for lbl, _ in count_items],
            [Paragraph(val, kpi_val) for _, val in count_items],
        ],
        colWidths=[(width - 72) / 9] * 9,
        hAlign="CENTER",
    )
    count_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#0f766e")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#99f6e4")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(count_table)
    story.append(Spacer(1, 10))

    value_items = [
        ("Total Lead Value", _inr(t.get("total_lead_value"))),
        ("Total Quotation Value", _inr(t.get("total_quotation_value"))),
        ("Total Converted Value", _inr(t.get("converted_lead_value"))),
    ]
    value_table = Table(
        [
            [Paragraph(lbl, kpi_lbl) for lbl, _ in value_items],
            [Paragraph(val, kpi_val) for _, val in value_items],
        ],
        colWidths=[(width - 72) / 3] * 3,
        hAlign="CENTER",
    )
    value_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf3")),
        ("BOX", (0, 0), (-1, -1), 0.6, GREEN),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbf7d0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(value_table)

    sections = [
        ("by_source", "source", "Leads by Source", colors.HexColor("#1e3a5f")),
        ("by_product", "product", "Leads by Product", colors.HexColor("#0f766e")),
        ("by_category", "category", "Leads by Category", colors.HexColor("#0e7490")),
    ]
    usable = width - 72
    for section_key, field, section_title, bar_color in sections:
        block = payload.get(section_key) or {}
        rows_data = block.get("rows") or []
        totals = block.get("totals") or {}

        story.append(PageBreak())
        story.append(Paragraph(section_title, heading))
        headers = [
            section_title.split("(")[0].replace("Leads by ", "").strip() or field.title(),
            "Total Leads", "Total Lead Value", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Converted", "Not Interested",
        ]
        # Cleaner label headers
        label_headers = {
            "source": "Source",
            "product": "Product",
            "category": "Category",
        }
        headers[0] = label_headers.get(field, field.title())
        table_rows = [[Paragraph(h, header) for h in headers]]
        for row in rows_data:
            table_rows.append([
                Paragraph(escape(str(row.get(field) or "—")), cell),
                Paragraph(str(row.get("total", 0)), cell),
                Paragraph(_inr(row.get("lead_value")), cell),
                *[Paragraph(str(row.get(key, 0)), cell) for key in KEYS[1:]],
            ])
        if not rows_data:
            table_rows.append([Paragraph("No data", cell), *[Paragraph("0", cell) for _ in range(len(KEYS) + 1)]])
        table_rows.append([
            Paragraph("TOTAL", header),
            Paragraph(str(totals.get("total", 0)), cell),
            Paragraph(_inr(totals.get("lead_value")), cell),
            *[Paragraph(str(totals.get(key, 0)), cell) for key in KEYS[1:]],
        ])
        col_w = usable / 9
        table = Table(table_rows, colWidths=[col_w] * 9, repeatRows=1, hAlign="CENTER")
        table.setStyle(_centered_table_style(bar_color))
        table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

        paired = [
            (str(row.get(field) or ""), float(row.get("total") or 0))
            for row in rows_data
            if float(row.get("total") or 0) > 0
        ]
        story.append(PageBreak())
        story.append(Paragraph(f"{section_title} — Chart", heading))
        story.append(Paragraph("Share of total leads", meta))
        story.append(Spacer(1, 8))
        if paired:
            chart = _donut_chart(
                [lab for lab, _ in paired],
                [val for _, val in paired],
                usable,
                section_title,
            )
            if chart is not None:
                story.append(chart)
            else:
                story.append(Paragraph("No chart data for this selection.", meta))
        else:
            story.append(Paragraph("No chart data for this selection.", meta))

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_report_pdf(payload: dict, report_type: str) -> bytes:
    if report_type == "dashboard_history":
        return build_dashboard_history_pdf(payload)
    if report_type == "lead_value":
        return build_lead_value_pdf(payload)
    if report_type == "quotation":
        return build_quotation_pdf(payload)
    if report_type == "monthly":
        return build_monthly_pdf(payload)
    if report_type == "detailed":
        return build_detailed_leads_pdf(payload)
    if report_type not in ("source", "product", "category"):
        raise ValueError("Invalid report type")
    if report_type == "product":
        title, label, field = "Product-wise Report", "Product", "product"
        chart_title = "Product-wise leads"
        bar_color = colors.HexColor("#0f766e")
    elif report_type == "category":
        title, label, field = "Category-wise Report", "Category", "category"
        chart_title = "Category-wise leads"
        bar_color = colors.HexColor("#0e7490")
    else:
        title, label, field = "Lead Source Report", "Lead Source", "source"
        chart_title = "Leads by source"
        bar_color = colors.HexColor("#1e3a5f")
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(width, height), leftMargin=36,
                            rightMargin=36, topMargin=122, bottomMargin=42,
                            title=title, author="ESTAR Engineers Pvt Ltd")
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=13,
                             textColor=NAVY, spaceAfter=10, keepWithNext=True, alignment=1)
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=12,
                          alignment=1, textColor=colors.HexColor("#334155"))
    story = []
    story.append(Paragraph(title, heading))
    headers = [label, "Total Leads", "Total Lead Value", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Converted", "Not Interested"]
    rows = [[Paragraph(value, header) for value in headers]]
    for row in payload["rows"]:
        rows.append([
            Paragraph(escape(str(row[field])), cell),
            Paragraph(str(row.get("total", 0)), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
            *[Paragraph(str(row.get(key, 0)), cell) for key in KEYS[1:]],
        ])
    if not payload["rows"]:
        rows.append([Paragraph("No leads found", cell), *[Paragraph("0", cell) for _ in range(len(KEYS) + 1)]])
    rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(payload["totals"].get("total", 0)), cell),
        Paragraph(_inr(payload["totals"].get("lead_value")), cell),
        *[Paragraph(str(payload["totals"].get(key, 0)), cell) for key in KEYS[1:]],
    ])
    usable = width - 72
    # Give the descriptive columns room to breathe while keeping the compact
    # status counts narrow enough for the complete table to remain on page one.
    weights = [0.16, 0.09, 0.14, 0.102, 0.102, 0.102, 0.10, 0.10, 0.10]
    table = Table(rows, colWidths=[usable * weight for weight in weights], repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(bar_color))
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    # Chart on its own page: the same chart type as the webpage —
    # grouped bars for source, single bars for product/category.
    if report_type == "source":
        bar_defs = [
            ("Total Leads", "total", "#1e3a5f"),
            ("In Followup", "in_followup", "#E8890C"),
            ("Meeting", "meeting", "#38BDF8"),
            ("Site Visit", "site_visit", "#0D9488"),
            ("Quotation sent", "quote_sent", "#FACC15"),
            ("Converted", "converted", "#16A34A"),
            ("Not Interested", "not_interested", "#DC2626"),
        ]
    else:
        bar_defs = [("Leads", "total", "#65A30D")]
    chart_labels = [str(row.get(field) or "") for row in payload.get("rows") or []]
    bar_series = [
        (nm, [float(row.get(key) or 0) for row in payload.get("rows") or []], col)
        for nm, key, col in bar_defs
    ]
    share = _share_caption(
        "Share of total leads",
        [(str(row.get(field) or ""), float(row.get("total") or 0)) for row in payload.get("rows") or []],
    )
    if any(v > 0 for _, vals, _ in bar_series for v in vals):
        story.append(PageBreak())
        story.append(Paragraph(chart_title, heading))
        if share:
            story.append(Paragraph(escape(share), meta))
        else:
            story.append(Paragraph("Counts per stage", meta))
        story.append(Spacer(1, 8))
        chart = _vertical_bar_chart(chart_labels, bar_series, width - 72, chart_title)
        if chart is not None:
            story.append(chart)
        else:
            story.append(Paragraph("No chart data for this selection.", meta))

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_lead_value_pdf(payload: dict) -> bytes:
    title = "Lead Value Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(width, height), leftMargin=36,
                            rightMargin=36, topMargin=122, bottomMargin=42,
                            title=title, author="ESTAR Engineers Pvt Ltd")
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=13,
                             textColor=GREEN, spaceAfter=8, keepWithNext=True, alignment=1)
    subhead = ParagraphStyle("subhead", fontName="Helvetica-Bold", fontSize=11,
                             textColor=NAVY, spaceBefore=12, spaceAfter=8, alignment=1)
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1, textColor=colors.HexColor("#334155"))

    story = []
    story.append(Paragraph(title, heading))
    rng = f"{payload.get('from_date') or 'All'} → {payload.get('to_date') or 'All'}  ·  Mode: {payload.get('mode') or 'custom'}"
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    # KPI strip
    kpi_headers = ["Total Lead Value", "Total Leads", "Total Cars", "Average Lead Value"]
    kpi_vals = [
        _inr(payload.get("total_lead_value")),
        str(payload.get("total_leads") or 0),
        str(int(float(payload.get("total_cars") or 0))),
        _inr(payload.get("average_lead_value")),
    ]
    kpi = Table(
        [[Paragraph(h, header) for h in kpi_headers], [Paragraph(v, cell) for v in kpi_vals]],
        colWidths=[(width - 72) / 4] * 4,
        hAlign="CENTER",
    )
    kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ecfdf3")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(kpi)

    # By product
    story.append(Paragraph("Lead Value by Product", subhead))
    prod_rows = [[Paragraph(h, header) for h in ("Product", "Sources", "Leads", "Lead Value")]]
    for row in payload.get("by_product") or []:
        prod_rows.append([
            Paragraph(escape(str(row.get("product") or "—")), cell),
            Paragraph(escape(str(row.get("sources") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
        ])
    if len(prod_rows) == 1:
        prod_rows.append([
            Paragraph("No data", cell), Paragraph("—", cell),
            Paragraph("0", cell), Paragraph(_inr(0), cell),
        ])
    prod_rows.append([
        Paragraph("TOTAL", header),
        Paragraph("", cell),
        Paragraph(str(payload.get("total_leads") or 0), cell),
        Paragraph(_inr(payload.get("total_lead_value")), cell),
    ])
    usable = width - 72
    prod_table = Table(
        prod_rows,
        colWidths=[usable * 0.32, usable * 0.36, usable * 0.14, usable * 0.18],
        repeatRows=1,
        hAlign="CENTER",
    )
    prod_table.setStyle(_centered_table_style(GREEN))
    story.append(prod_table)

    # By source
    story.append(Paragraph("Lead Value by Source", subhead))
    src_rows = [[Paragraph(h, header) for h in ("Source", "Leads", "Lead Value")]]
    for row in payload.get("by_source") or []:
        src_rows.append([
            Paragraph(escape(str(row.get("source") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
        ])
    if len(src_rows) == 1:
        src_rows.append([Paragraph("No data", cell), Paragraph("0", cell), Paragraph(_inr(0), cell)])
    source_total_leads = sum(int(r.get("leads") or 0) for r in (payload.get("by_source") or []))
    source_total_value = sum(float(r.get("lead_value") or 0) for r in (payload.get("by_source") or []))
    src_rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(source_total_leads), cell),
        Paragraph(_inr(source_total_value), cell),
    ])
    pw = usable / 3
    src_table = Table(src_rows, colWidths=[pw * 1.4, pw * 0.6, pw], repeatRows=1, hAlign="CENTER")
    src_table.setStyle(_centered_table_style(GREEN))
    story.append(src_table)

    # By period
    story.append(Paragraph("Lead Value by Period", subhead))
    per_rows = [[Paragraph(h, header) for h in ("Period", "Leads", "Lead Value")]]
    for row in payload.get("by_period") or []:
        per_rows.append([
            Paragraph(escape(str(row.get("label") or row.get("period") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
        ])
    if len(per_rows) == 1:
        per_rows.append([Paragraph("No dated leads", cell), Paragraph("0", cell), Paragraph(_inr(0), cell)])
    period_total_leads = sum(int(r.get("leads") or 0) for r in (payload.get("by_period") or []))
    period_total_value = sum(float(r.get("lead_value") or 0) for r in (payload.get("by_period") or []))
    per_rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(period_total_leads), cell),
        Paragraph(_inr(period_total_value), cell),
    ])
    per_table = Table(per_rows, colWidths=[pw * 1.4, pw * 0.6, pw], repeatRows=1, hAlign="CENTER")
    per_table.setStyle(_centered_table_style(GREEN))
    story.append(per_table)

    # Same ₹ bar charts as the webpage (values plotted in lakhs).
    value_charts = [
        ("Lead Value by Product — Chart", [(str(r.get("product") or ""), r.get("lead_value")) for r in payload.get("by_product") or []]),
        ("Lead Value by Source — Chart", [(str(r.get("source") or ""), r.get("lead_value")) for r in payload.get("by_source") or []]),
        ("Lead Value by Period — Chart", [(str(r.get("label") or r.get("period") or ""), r.get("lead_value")) for r in payload.get("by_period") or []]),
    ]
    for chart_heading, raw_pairs in value_charts:
        pairs = [(lab, float(v or 0)) for lab, v in raw_pairs if float(v or 0) > 0]
        if not pairs:
            continue
        story.append(PageBreak())
        story.append(Paragraph(chart_heading, heading))
        share = _share_caption("Share of total value", pairs)
        if share:
            story.append(Paragraph(escape(share), meta))
        else:
            story.append(Paragraph("Values in ₹ lakh", meta))
        story.append(Spacer(1, 8))
        chart = _vertical_bar_chart(
            [lab for lab, _ in pairs],
            [("Lead Value (₹ lakh)", [v / 1e5 for _, v in pairs], "#3F6212")],
            usable,
            f"{chart_heading} (₹ lakh)",
            value_format="%.1f",
        )
        if chart is not None:
            story.append(chart)
        else:
            story.append(Paragraph("No chart data for this selection.", meta))

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


AMBER = colors.HexColor("#b45309")
INDIGO = colors.HexColor("#4338ca")
SLATE = colors.HexColor("#0f172a")


def build_detailed_leads_pdf(payload: dict) -> bytes:
    title = "Detailed Lead Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=14, rightMargin=14,
        topMargin=122, bottomMargin=36, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=6, leading=7.5, alignment=1)
    cell_left = ParagraphStyle("cell_left", fontName="Helvetica", fontSize=6, leading=7.5, alignment=0)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=SLATE, spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"),
    )

    def lines(text) -> str:
        raw = str(text if text not in (None, "") else "—")
        return "<br/>".join(escape(part) for part in raw.split("\n"))

    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('from_month') or payload.get('effective_from') or 'All'}"
        f" → {payload.get('to_month') or payload.get('effective_to') or 'All'}"
        f"  ·  Leads: {payload.get('count', len(payload.get('rows') or []))}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 8))

    headers = [
        "Enquiry", "Date", "Customer", "City", "Contact", "Cars", "Product", "Source",
        "Status", "Progress", "Category", "Remarks", "Employee", "Lead Value", "Quotation",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    for row in payload.get("rows") or []:
        rows.append([
            Paragraph(escape(str(row.get("enquiry_number") or "—")), cell),
            Paragraph(escape(str(row.get("enquiry_date") or "—")), cell),
            Paragraph(escape(str(row.get("customer_name") or "—")), cell_left),
            Paragraph(escape(str(row.get("city") or "—")), cell),
            Paragraph(escape(str(row.get("contact_number") or "—")), cell),
            Paragraph(escape(str(row.get("cars") or "—")), cell),
            Paragraph(escape(str(row.get("product") or "—")), cell_left),
            Paragraph(escape(str(row.get("source") or "—")), cell),
            Paragraph(escape(str(row.get("status") or "—")), cell),
            Paragraph(lines(row.get("progress")), cell_left),
            Paragraph(lines(row.get("category")), cell_left),
            Paragraph(lines(row.get("remarks")), cell_left),
            Paragraph(escape(str(row.get("employee") or "—")), cell),
            Paragraph(_inr(row.get("lead_value")) if row.get("lead_value") not in (None, "—", "") else "—", cell),
            Paragraph(_inr(row.get("quotation_value")) if row.get("quotation_value") not in (None, "—", "") else "—", cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No leads found", cell), *[Paragraph("—", cell) for _ in range(14)]])

    usable = width - 28
    weights = [0.07, 0.06, 0.08, 0.05, 0.06, 0.04, 0.07, 0.06, 0.06, 0.08, 0.08, 0.10, 0.06, 0.06, 0.07]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    style = _centered_table_style(SLATE)
    style.add("FONTSIZE", (0, 1), (-1, -1), 6)
    style.add("TOPPADDING", (0, 0), (-1, -1), 4)
    style.add("BOTTOMPADDING", (0, 0), (-1, -1), 4)
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.white)
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica")
    style.add("VALIGN", (0, 0), (-1, -1), "TOP")
    table.setStyle(style)
    story.append(table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_monthly_pdf(payload: dict) -> bytes:
    title = "Monthly Lead Volume"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=28, rightMargin=28,
        topMargin=122, bottomMargin=42, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, alignment=1)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=INDIGO, spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"),
    )

    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('from_month') or 'All'} → {payload.get('to_month') or 'All'}"
        f"  ·  Months: {len(payload.get('rows') or [])}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    headers = [
        "Month", "Total Leads", "Total Lead Value", "In Followup", "Meeting", "Site Visit",
        "Quotation sent", "Not Interested", "Lead Sources", "Products",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    totals = {
        "leads": 0, "lead_value": 0, "in_followup": 0, "meeting": 0, "site_visit": 0,
        "quotation_sent": 0, "not_interested": 0,
    }
    for row in payload.get("rows") or []:
        for key in totals:
            totals[key] += int(row.get(key) or 0)
        rows.append([
            Paragraph(escape(str(row.get("month") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(_inr(row.get("lead_value")), cell),
            Paragraph(str(row.get("in_followup") or 0), cell),
            Paragraph(str(row.get("meeting") or 0), cell),
            Paragraph(str(row.get("site_visit") or 0), cell),
            Paragraph(str(row.get("quotation_sent") or 0), cell),
            Paragraph(str(row.get("not_interested") or 0), cell),
            Paragraph(escape(str(row.get("sources") or "—")), cell),
            Paragraph(escape(str(row.get("products") or "—")), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No months found", cell), *[Paragraph("—", cell) for _ in range(9)]])
    rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(totals["leads"]), cell),
        Paragraph(_inr(totals["lead_value"]), cell),
        Paragraph(str(totals["in_followup"]), cell),
        Paragraph(str(totals["meeting"]), cell),
        Paragraph(str(totals["site_visit"]), cell),
        Paragraph(str(totals["quotation_sent"]), cell),
        Paragraph(str(totals["not_interested"]), cell),
        Paragraph("", cell),
        Paragraph("", cell),
    ])

    usable = width - 56
    weights = [0.07, 0.08, 0.11, 0.08, 0.08, 0.08, 0.10, 0.10, 0.16, 0.14]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(INDIGO))
    story.append(table)

    # Same grouped bar chart as the webpage (Total + progress per month).
    month_defs = [
        ("Total Leads", "leads", "#1e3a5f"),
        ("In Followup", "in_followup", "#E8890C"),
        ("Meeting", "meeting", "#38BDF8"),
        ("Site Visit", "site_visit", "#0D9488"),
        ("Quotation sent", "quotation_sent", "#FACC15"),
        ("Not Interested", "not_interested", "#DC2626"),
    ]
    month_labels = [str(row.get("month") or "") for row in payload.get("rows") or []]
    month_series = [
        (nm, [float(row.get(key) or 0) for row in payload.get("rows") or []], col)
        for nm, key, col in month_defs
    ]
    month_share = _share_caption(
        "Share of total leads",
        [(str(row.get("month") or ""), float(row.get("leads") or 0)) for row in payload.get("rows") or []],
    )
    if any(v > 0 for _, vals, _ in month_series for v in vals):
        story.append(PageBreak())
        story.append(Paragraph("Monthly lead volume — Chart", heading))
        if month_share:
            story.append(Paragraph(escape(month_share), meta))
        else:
            story.append(Paragraph("Counts per stage", meta))
        story.append(Spacer(1, 8))
        chart = _vertical_bar_chart(month_labels, month_series, width - 56, "Monthly lead volume")
        if chart is not None:
            story.append(chart)
        else:
            story.append(Paragraph("No chart data for this selection.", meta))

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def build_quotation_pdf(payload: dict) -> bytes:
    title = "Quotation Report"
    buffer = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=(width, height), leftMargin=28, rightMargin=28,
        topMargin=122, bottomMargin=42, title=title, author="ESTAR Engineers Pvt Ltd",
    )
    generated = datetime.now().strftime("%d %b %Y")
    logo = _brand_logo()
    logo_iw, logo_ih = logo.getSize()
    page_header = _page_header_fn(logo, logo_iw, logo_ih, title, generated, width, height, doc)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, alignment=1)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=13,
        textColor=AMBER, spaceAfter=8, keepWithNext=True, alignment=1,
    )
    header = ParagraphStyle("header", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=9, leading=12, alignment=1,
        textColor=colors.HexColor("#334155"),
    )

    story = []
    story.append(Paragraph(title, heading))
    rng = (
        f"{payload.get('effective_from') or 'All'} → {payload.get('effective_to') or 'All'}"
        f"  ·  Mode: {payload.get('mode') or 'custom'}"
        f"  ·  Rows: {payload.get('totals', {}).get('count', len(payload.get('rows') or []))}"
    )
    story.append(Paragraph(escape(rng), meta))
    story.append(Spacer(1, 10))

    headers = [
        "S.No", "REF", "Date", "Enquiry No", "Customer Name", "State", "Parking Type",
        "Units/Cars", "Order Value (Excl GST)", "GST", "Grand Total",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    for row in payload.get("rows") or []:
        rows.append([
            Paragraph(str(row.get("sno") or ""), cell),
            Paragraph(escape(str(row.get("ref") or "—")), cell),
            Paragraph(escape(str(row.get("date") or "—")), cell),
            Paragraph(escape(str(row.get("enquiry_number") or "—")), cell),
            Paragraph(escape(str(row.get("customer_name") or "—")), cell),
            Paragraph(escape(str(row.get("state") or "—")), cell),
            Paragraph(escape(str(row.get("parking_type") or "—")), cell),
            Paragraph("—" if row.get("units") is None else str(row.get("units")), cell),
            Paragraph(_inr(row.get("order_value_excl_gst")), cell),
            Paragraph(_inr(row.get("gst")), cell),
            Paragraph(_inr(row.get("grand_total")), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No quotations found", cell), *[Paragraph("—", cell) for _ in range(10)]])
    totals = payload.get("totals") or {}
    rows.append([
        Paragraph("", cell), Paragraph("", cell), Paragraph("", cell),
        Paragraph("", cell), Paragraph("", cell), Paragraph("", cell),
        Paragraph("TOTAL", header),
        Paragraph("", cell),
        Paragraph(_inr(totals.get("order_value_excl_gst")), cell),
        Paragraph(_inr(totals.get("gst")), cell),
        Paragraph(_inr(totals.get("grand_total")), cell),
    ])

    usable = width - 56
    # Slightly tighter REF; more room for Grand Total
    weights = [0.04, 0.15, 0.07, 0.11, 0.10, 0.07, 0.10, 0.06, 0.10, 0.07, 0.13]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(AMBER))
    story.append(table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
