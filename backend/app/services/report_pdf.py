"""Branded, paginated lead report downloads."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
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
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, alignment=1)
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
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Category is the number of customers. Progress is each time that step was logged.",
        meta,
    ))
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()


def _label_for_axis(text: str, max_len: int = 18) -> str:
    label = " ".join(str(text or "").split())
    if len(label) <= max_len:
        return label
    return label[: max_len - 1].rstrip() + "…"


def _vertical_bar_chart(
    labels: list[str],
    values: list[float],
    chart_width: float,
    title: str,
    bar_color=None,
) -> Drawing | None:
    """Category names on X, counts on Y — roomy bottom labels so text never hits bars."""
    if not labels or not values:
        return None
    peak = max(float(v or 0) for v in values)
    if peak <= 0:
        return None
    fill = bar_color or colors.HexColor("#65A30D")
    n = len(labels)
    # Extra bottom band for angled category names; taller plot so bars stay clear of labels.
    left_pad = 48.0
    right_pad = 18.0
    top_pad = 28.0
    label_band = 78.0 if n > 4 else 64.0
    plot_h = 210.0
    plot_w = max(240.0, chart_width - left_pad - right_pad)
    drawing_h = top_pad + plot_h + label_band + 8
    drawing = Drawing(chart_width, drawing_h)

    chart = VerticalBarChart()
    chart.x = left_pad
    chart.y = label_band
    chart.height = plot_h
    chart.width = plot_w
    chart.data = [list(values)]
    chart.strokeColor = colors.white
    chart.barWidth = min(28, max(10, plot_w / max(n * 1.8, 1)))
    chart.groupSpacing = max(8, plot_w / max(n * 3.2, 1))
    chart.barSpacing = 2
    chart.bars[0].fillColor = fill
    chart.bars[0].strokeColor = fill

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = peak * 1.18
    chart.valueAxis.valueSteps = None
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.strokeColor = colors.HexColor("#94a3b8")
    chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    chart.valueAxis.gridStrokeWidth = 0.5

    chart.categoryAxis.categoryNames = [_label_for_axis(name) for name in labels]
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.angle = 35
    chart.categoryAxis.labels.dx = -2
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.labels.fontSize = 7 if n > 8 else 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.strokeColor = colors.HexColor("#94a3b8")

    drawing.add(chart)
    drawing.add(String(left_pad, drawing_h - 14, title, fontSize=10, fillColor=NAVY))
    return drawing


def build_report_pdf(payload: dict, report_type: str) -> bytes:
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
    headers = [label, "Total Leads", "In Followup", "Meeting", "Site Visit", "Quotation sent", "Converted", "Not Interested"]
    rows = [[Paragraph(value, header) for value in headers]]
    for row in payload["rows"]:
        rows.append([
            Paragraph(escape(str(row[field])), cell),
            *[Paragraph(str(row.get(key, 0)), cell) for key in KEYS],
        ])
    if not payload["rows"]:
        rows.append([Paragraph("No leads found", cell), *[Paragraph("0", cell) for _ in KEYS]])
    rows.append([Paragraph("TOTAL", header), *[Paragraph(str(payload["totals"].get(key, 0)), cell) for key in KEYS]])
    col_w = (width - 72) / 8
    table = Table(rows, colWidths=[col_w] * 8, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style())
    story.append(table)

    # Chart on its own page so table text never collides with axis labels / bars.
    chart_labels = [str(row.get(field) or "") for row in payload.get("rows") or []]
    chart_values = [float(row.get("total") or 0) for row in payload.get("rows") or []]
    # Drop all-zero rows from the chart only (table still shows full set).
    paired = [(lab, val) for lab, val in zip(chart_labels, chart_values) if val > 0]
    if paired:
        story.append(PageBreak())
        story.append(Paragraph(chart_title, heading))
        story.append(Paragraph("X-axis: names · Y-axis: lead count", meta))
        story.append(Spacer(1, 8))
        chart = _vertical_bar_chart(
            [lab for lab, _ in paired],
            [val for _, val in paired],
            width - 72,
            chart_title,
            bar_color=bar_color,
        )
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
        "Month", "Total Leads", "In Followup", "Meeting", "Site Visit",
        "Quotation sent", "Not Interested", "Lead Sources", "Products",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    totals = {
        "leads": 0, "in_followup": 0, "meeting": 0, "site_visit": 0,
        "quotation_sent": 0, "not_interested": 0,
    }
    for row in payload.get("rows") or []:
        for key in totals:
            totals[key] += int(row.get(key) or 0)
        rows.append([
            Paragraph(escape(str(row.get("month") or "—")), cell),
            Paragraph(str(row.get("leads") or 0), cell),
            Paragraph(str(row.get("in_followup") or 0), cell),
            Paragraph(str(row.get("meeting") or 0), cell),
            Paragraph(str(row.get("site_visit") or 0), cell),
            Paragraph(str(row.get("quotation_sent") or 0), cell),
            Paragraph(str(row.get("not_interested") or 0), cell),
            Paragraph(escape(str(row.get("sources") or "—")), cell),
            Paragraph(escape(str(row.get("products") or "—")), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No months found", cell), *[Paragraph("—", cell) for _ in range(8)]])
    rows.append([
        Paragraph("TOTAL", header),
        Paragraph(str(totals["leads"]), cell),
        Paragraph(str(totals["in_followup"]), cell),
        Paragraph(str(totals["meeting"]), cell),
        Paragraph(str(totals["site_visit"]), cell),
        Paragraph(str(totals["quotation_sent"]), cell),
        Paragraph(str(totals["not_interested"]), cell),
        Paragraph("", cell),
        Paragraph("", cell),
    ])

    usable = width - 56
    weights = [0.08, 0.08, 0.09, 0.08, 0.08, 0.10, 0.10, 0.20, 0.19]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(INDIGO))
    story.append(table)

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
        "S.No", "Date", "Enquiry No", "Customer Name", "State", "Parking Type",
        "Units/Cars", "Order Value (Excl GST)", "GST", "Grand Total",
    ]
    rows = [[Paragraph(h, header) for h in headers]]
    for i, row in enumerate(payload.get("rows") or [], start=1):
        rows.append([
            Paragraph(str(i), cell),
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
        rows.append([Paragraph("No quotations found", cell), *[Paragraph("—", cell) for _ in range(9)]])
    totals = payload.get("totals") or {}
    rows.append([
        Paragraph("", cell), Paragraph("", cell), Paragraph("", cell),
        Paragraph("", cell), Paragraph("", cell),
        Paragraph("TOTAL", header),
        Paragraph("", cell),
        Paragraph(_inr(totals.get("order_value_excl_gst")), cell),
        Paragraph(_inr(totals.get("gst")), cell),
        Paragraph(_inr(totals.get("grand_total")), cell),
    ])

    usable = width - 56
    weights = [0.05, 0.09, 0.10, 0.14, 0.09, 0.14, 0.08, 0.12, 0.09, 0.10]
    col_w = [usable * w for w in weights]
    table = Table(rows, colWidths=col_w, repeatRows=1, hAlign="CENTER")
    table.setStyle(_centered_table_style(AMBER))
    story.append(table)

    doc.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
