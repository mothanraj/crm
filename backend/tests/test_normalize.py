from app.services.normalize import canonical_source, is_valid_phone, norm_phone, parse_excel_date  # noqa


def test_phone():
    assert norm_phone("p:+919995910299") == "9995910299"
    assert norm_phone("+919876543210") == "9876543210"
    assert is_valid_phone("9876543210")
    assert is_valid_phone("+91 9876543210")
    assert not is_valid_phone("+44 7911 123456")
    assert not is_valid_phone("+1 202 555 0123")
    assert not is_valid_phone("+971 50 123 4567")
    assert not is_valid_phone("4428123456")
    assert not is_valid_phone("12345")


def test_date_serial():
    d = parse_excel_date(46186)
    assert d is not None and d.year == 2026


def test_status_merge():
    from app.services.normalize import STATUS_ALIASES
    assert STATUS_ALIASES["not interested/spam"] == "Not Interested/Spam"


def test_canonical_source_variants():
    assert canonical_source("facebook/ instagram") == "Facebook/Instagram"
    assert canonical_source("Meta") == "Facebook/Instagram"
    assert canonical_source("refferal") == "Referral"
    assert canonical_source("") == "Others"


def test_car_count_rules():
    from app.services.normalize import normalize_car_count

    assert normalize_car_count("", "Two Post Stack Parking") == (2, None)
    assert normalize_car_count("4", "Tower Parking") == (4, None)
    assert normalize_car_count("3", "Tower Parking")[0] is None
    assert normalize_car_count("1", "Puzzle Parking")[0] is None
    assert normalize_car_count("3", "Puzzle Parking") == (3, None)
    assert normalize_car_count("5", "Pit Puzzle Parking") == (5, None)
    assert normalize_car_count("7", "car elevation") == (7, None)
    assert normalize_car_count("9", "Shuttle Parking") == (9, None)
    assert normalize_car_count("11", "ASRS Parking") == (11, None)
    assert normalize_car_count("3", "Two Post Stack Parking")[1]
