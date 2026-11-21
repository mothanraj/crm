"""PDF text sanitizing: CRM free-text must never break the renderer."""
from app.services.report_pdf import _pdf_text


def test_emoji_and_non_latin1_are_replaced():
    assert _pdf_text("Mananthavadyijfghg\U0001f31b.. ok") == "Mananthavadyijfghg?.. ok"
    assert _pdf_text("home for chic\u0137en") == "home for chic?en"


def test_plain_and_latin1_text_is_kept():
    assert _pdf_text("Marg\u00e3o") == "Marg\u00e3o"
    assert _pdf_text("Ravi <Sharma> & Co") == "Ravi <Sharma> & Co"


def test_newlines_and_missing_values():
    assert _pdf_text("1. Followup\n2. Meeting") == "1. Followup\n2. Meeting"
    assert _pdf_text(None) == "\u2014"
    assert _pdf_text("") == "\u2014"


def test_pathological_cell_is_capped():
    assert _pdf_text("x" * 5000).endswith("... (truncated)")
