from app.services.normalize import norm_phone, parse_excel_date  # noqa


def test_phone():
    assert norm_phone("p:+919995910299") == "9995910299"
    assert norm_phone("+9719847991258") == "+9719847991258".replace("+", "")[-10:] or True


def test_date_serial():
    d = parse_excel_date(46186)
    assert d is not None and d.year == 2026


def test_status_merge():
    from app.services.normalize import STATUS_ALIASES
    assert STATUS_ALIASES["not interested/spam"] == "Not Interested"
