"""Lead Value Report exports must mirror the webpage: KPI tiles + its three blocks.

Page blocks: Total Lead Value / Total Leads / Total Cars / Average Lead Value,
Lead Value by Product (chart → table here, Leads + Lead Value columns),
Lead Value by Source (chart → table), Lead Value by Week|Day (chart → table).
No product Sources column, no TOTAL rows. The product table lists every
canonical product the webpage chart plots, including zero-value rows.
"""

import base64
import re
import zlib
from datetime import date
from io import BytesIO

import openpyxl

from app.api.dashboard import _lead_value_xlsx
from app.services.report_pdf import build_lead_value_pdf

PAYLOAD = {
    "mode": "month",
    "from_date": "2026-11-01",
    "to_date": "2026-11-30",
    "total_lead_value": 1_500_000,
    "total_leads": 42,
    "total_cars": 120,
    "average_lead_value": 35_714,
    "by_product": [
        {"product": "Puzzle Parking", "lead_value": 1_000_000, "leads": 20, "sources": "Google Ads"},
        {"product": "Tower Parking", "lead_value": 500_000, "leads": 12, "sources": "Meta"},
        {"product": "ASRS Parking", "lead_value": 0, "leads": 0, "sources": "—"},
    ],
    "by_source": [
        {"source": "Google Ads", "lead_value": 900_000, "leads": 25},
        {"source": "Others", "lead_value": 600_000, "leads": 17},
    ],
    "by_period": [
        {"period": "2026-11-02", "label": "02 Nov – 08 Nov 2026", "lead_value": 700_000, "leads": 19},
        {"period": "2026-11-09", "label": "09 Nov – 15 Nov 2026", "lead_value": 800_000, "leads": 23},
    ],
}


def _flat(rows):
    return [str(cell) for row in rows for cell in row if cell not in (None, "")]


def _excel_rows(payload, start, end, resolved):
    buf = _lead_value_xlsx(payload, start, end, resolved)
    wb = openpyxl.load_workbook(BytesIO(buf.getvalue()))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    return ws, rows, _flat(rows)


def _pdf_text(content: bytes) -> str:
    """Decompress reportlab content streams (plain, ASCII85+Flate, or ASCII85)."""
    blob = b""
    for match in re.finditer(rb"(?<!end)stream\r?\n(.*?)endstream", content, re.S):
        raw = match.group(1).strip()
        for decode in (
            lambda r: zlib.decompress(r),
            lambda r: zlib.decompress(base64.a85decode(r, adobe=True)),
            lambda r: base64.a85decode(r, adobe=True),
        ):
            try:
                blob += decode(raw)
                break
            except Exception:
                continue
    text = blob.decode("latin-1")
    # Unescape PDF string operators so plain-text assertions are readable.
    return text.replace("\\(", "(").replace("\\)", ")")


def test_excel_matches_the_page_blocks():
    _, rows, flat = _excel_rows(PAYLOAD, date(2026, 11, 1), date(2026, 11, 30), "month")
    assert "ESTAR ENGINEERS PVT LTD" in flat
    assert "LEAD VALUE REPORT" in flat
    assert "2026-11-01 → 2026-11-30  ·  Mode: month" in flat
    # KPI strip — labels then values
    assert ("Total Lead Value", "Total Leads", "Total Cars", "Average Lead Value") in rows
    kpi_at = rows.index(("Total Lead Value", "Total Leads", "Total Cars", "Average Lead Value"))
    assert rows[kpi_at + 1] == (1_500_000.0, 42, 120, 35_714.0)
    # Product block — Leads + Lead Value columns, zero rows the webpage chart plots
    assert "Lead Value by Product" in flat
    assert ("Product", "Leads", "Lead Value (₹)", None) in rows
    assert ("Puzzle Parking", 20, 1_000_000.0, None) in rows
    assert ("Tower Parking", 12, 500_000.0, None) in rows
    assert ("ASRS Parking", 0, 0.0, None) in rows
    # Source block — same table as the page
    assert "Lead Value by Source" in flat
    assert ("Source", "Leads", "Lead Value (₹)", None) in rows
    assert ("Google Ads", 25, 900_000.0, None) in rows
    # Period block — week-bucket labels, Day/Week title by mode
    assert "Lead Value by Week" in flat
    assert ("Period", "Leads", "Lead Value (₹)", None) in rows
    assert ("02 Nov – 08 Nov 2026", 19, 700_000.0, None) in rows
    # Nothing beyond the page: no Sources column, no TOTAL rows
    assert "TOTAL" not in flat
    assert "Sources" not in flat


def test_excel_keeps_the_period_heading_when_page_shows_empty_state():
    _, rows, flat = _excel_rows({**PAYLOAD, "by_period": []}, None, None, "custom")
    assert "Lead Value by Week" in flat
    assert "No dated leads in this range." in flat
    # No table header under the heading — the page swaps the table for the note.
    assert ("Period", "Leads", "Lead Value (₹)", None) not in rows


def test_excel_titles_the_period_block_by_day_for_week_mode():
    _, _, flat = _excel_rows(PAYLOAD, date(2026, 11, 2), date(2026, 11, 8), "week")
    assert "Lead Value by Day" in flat
    assert "Lead Value by Week" not in flat


def test_pdf_shows_the_same_blocks_and_nothing_extra():
    pdf = build_lead_value_pdf(PAYLOAD)
    assert pdf[:5] == b"%PDF-"
    text = _pdf_text(pdf)
    assert "Total Lead Value" in text
    assert "Lead Value by Product" in text
    assert "Lead Value by Source" in text
    assert "Lead Value by Week" in text
    assert "Google Ads" in text
    # Webpage table headers (with the ₹ column suffix in the page; the PDF
    # renders it as a readable currency marker) and Indian digit grouping.
    assert "Lead Value (Rs.)" in text
    assert "9,00,000" in text  # 900,000 grouped the en-IN way, not 900,000
    # Product table, per-product sources column and TOTAL rows are not on the page.
    assert "Lead Value by Period" not in text
    assert "Sources" not in text
    assert "TOTAL" not in text


def test_pdf_keeps_the_period_heading_when_there_are_no_dated_leads():
    text = _pdf_text(build_lead_value_pdf({**PAYLOAD, "by_period": []}))
    assert "Lead Value by Week" in text
    assert "No dated leads in this range." in text
    assert "Lead Value by Product" in text
