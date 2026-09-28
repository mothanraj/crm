"""Normalisation maps derived from docs/excel-analysis.md."""
import re
from datetime import date

SOURCE_ALIASES = {
    "meta": "Facebook/Instagram", "im": "India Mart", "direct call": "Direct Call",
    "directcall": "Direct Call", "refferal": "Referral", "referral": "Referral",
    "seo": "SEO", "others": "Others", "expo/stall": "Expo/Stall",
    "email campaign": "Email Campaign", "email enquiry": "Email Enquiry",
    "facebook/instagram": "Facebook/Instagram", "google ads": "Google Ads",
    "india mart": "India Mart", "whatsapp": "WhatsApp",
    # Slash-spacing / case variants seen in real uploads (e.g. "facebook/ instagram")
    "facebook/ instagram": "Facebook/Instagram",
    "facebook /instagram": "Facebook/Instagram",
    "facebook / instagram": "Facebook/Instagram",
    "facebook": "Facebook/Instagram",
    "instagram": "Facebook/Instagram",
    "fb/instagram": "Facebook/Instagram",
    "facebook/instagram ": "Facebook/Instagram",
    "fb": "Facebook/Instagram",
    "ig": "Facebook/Instagram",
    "fb/ig": "Facebook/Instagram",
    "meta ads": "Facebook/Instagram",
    "facebook ads": "Facebook/Instagram",
    "instagram ads": "Facebook/Instagram",
    "directcall ": "Direct Call",
    "directcall/": "Direct Call",
    "indiamart": "India Mart",
    "india mart ": "India Mart",
    "expo/stall ": "Expo/Stall",
    "expo stall": "Expo/Stall",
    "expo": "Expo/Stall",
    "google": "Google Ads",
    "email campaign ": "Email Campaign",
    "email enquiry ": "Email Enquiry",
}


def canonical_source(raw: str) -> str:
    """Map any Excel source variant to a canonical master name.

    Handles slash-spacing ("facebook/ instagram"), case, and common
    shorthands (meta/fb/ig/im/directcall/refferal/expo).
    """
    text = (raw or "").strip()
    if not text:
        return "Others"
    k = norm_key(text)
    if k in SOURCE_ALIASES:
        return SOURCE_ALIASES[k]
    # Normalize spaces around "/" ("facebook/ instagram" -> "facebook/instagram")
    k2 = re.sub(r"\s*/\s*", "/", k)
    if k2 in SOURCE_ALIASES:
        return SOURCE_ALIASES[k2]
    # Contains-match for social variants
    if "facebook" in k2 or "instagram" in k2 or k2 in ("meta", "meta ads", "fb", "ig", "fb/ig"):
        return "Facebook/Instagram"
    if "indiamart" in k2 or k2 == "im":
        return "India Mart"
    if "direct" in k2 and "call" in k2:
        return "Direct Call"
    if "referral" in k2 or "refferal" in k2:
        return "Referral"
    if "whatsapp" in k2 or k2 == "wa":
        return "WhatsApp"
    if "email" in k2 and "campaign" in k2:
        return "Email Campaign"
    if "email" in k2 and ("enquiry" in k2 or "enquiry" in k):
        return "Email Enquiry"
    if "seo" in k2:
        return "SEO"
    if "expo" in k2 or "stall" in k2:
        return "Expo/Stall"
    if "google" in k2:
        return "Google Ads"
    return "Others"

STATUS_ALIASES = {
    "not interested/spam": "Not Interested/Spam",
    "not interested": "Not Interested",
    "rnr / not reachable": "RNR / Not reachable",
    "site visit": "Site Visit",
    "quotation sent": "Quotation sent",
    "quotation": "Quotation sent",
}

EMPLOYEE_ALIASES = {"ram kumar": "Ram", "sundarm": "Sundaram"}

PRODUCT_ALIASES = {
    # Two Post
    "two post stack parking": "Two Post Stack Parking",
    "two post stack parking system": "Two Post Stack Parking",
    "two_post_stack_parking": "Two Post Stack Parking",
    "two post stack parking.": "Two Post Stack Parking",
    "1+1": "Two Post Stack Parking",
    "1+1 car parking": "Two Post Stack Parking",
    "1+1 car parking system": "Two Post Stack Parking",
    "two level stack": "Two Post Stack Parking",
    "stack": "Two Post Stack Parking",
    "stack parking": "Two Post Stack Parking",
    "stack parking ": "Two Post Stack Parking",
    # Four Post (separate from Pit Stack)
    "four post stack parking": "Four Post Stack Parking",
    "four post parking": "Four Post Stack Parking",
    "four post": "Four Post Stack Parking",
    "four post parking / pit stack parking": "Four Post Stack Parking",
    # Pit Stack (separate)
    "pit stack parking": "Pit Stack Parking",
    "pit / fixed stack parking": "Pit Stack Parking",
    "pit stack": "Pit Stack Parking",
    "pit stack parking system": "Pit Stack Parking",
    "three level stack parking": "Pit Stack Parking",
    # Puzzle (separate from Pit Puzzle)
    "puzzle parking": "Puzzle Parking",
    "puzzle parking system": "Puzzle Parking",
    "puzzle_parking_system": "Puzzle Parking",
    "puzzle": "Puzzle Parking",
    "puzzle parking / pit puzzle parking": "Puzzle Parking",
    # Pit Puzzle (separate)
    "pit puzzle parking": "Pit Puzzle Parking",
    "pit puzzle": "Pit Puzzle Parking",
    # Tower
    "tower parking": "Tower Parking",
    "tower parking system": "Tower Parking",
    "tower_parking_system": "Tower Parking",
    "tower": "Tower Parking",
    # Shuttle
    "shuttle parking": "Shuttle Parking",
    "shuttle": "Shuttle Parking",
    "shuttle parking system": "Shuttle Parking",
    "shuttle / robotic parking": "Shuttle Parking",
    "shuttle/robotic_parking_": "Shuttle Parking",
    "robotic shuttle": "Shuttle Parking",
    "robotic / shuttle parking": "Shuttle Parking",
    "ss car parking (238 cars)": "Shuttle Parking",
    # Car Elevator
    "car elevator": "Car Elevator",
    "car elevation": "Car Elevator",
    "car lift": "Car Elevator",
    "car lift parking": "Car Elevator",
    # ASRS
    "asrs parking": "ASRS Parking",
    "asrs": "ASRS Parking",
    "mlcp / asrs / custom": "ASRS Parking",
    "mlcp": "ASRS Parking",
}

# Re-export from pricing so product master stays a single source of truth.
from app.services.pricing import CANONICAL_PRODUCTS, PRODUCT_PRICES  # noqa: E402
CANONICAL_SOURCES = [
    "Facebook/Instagram", "Google Ads", "India Mart", "Direct Call", "Referral",
    "WhatsApp", "Email Campaign", "Email Enquiry", "SEO", "Others", "Expo/Stall",
]
# Work-progress values used by employees after speaking to the customer (Excel "Staus" column + pipeline extras).
CANONICAL_STATUSES = [
    ("New Lead", False, False, 1),
    ("Assigned", False, False, 2),
    ("In Followup", False, False, 3),
    ("A - Prospect", False, False, 4),
    ("A+ - Immediate", False, False, 5),
    ("RNR / Not reachable", False, False, 6),
    ("Site Visit", False, False, 7),
    ("Meeting", False, False, 8),
    ("Quotation sent", False, False, 9),
    ("Channel Partner", False, False, 10),
    ("Approval Client", False, False, 11),
    ("Investor", False, False, 12),
    ("Not Interested", False, True, 13),
    ("Not Interested/Spam", False, True, 14),
    ("Converted", True, False, 15),
    ("Duplicate", True, True, 16),
]
def norm_phone(raw: str) -> str:
    """Digits only. +91 and a leading 0 are removed only for an Indian mobile.

    Numbers such as +971… also begin with 91, so they are kept in full.
    """
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 12 and d.startswith("91") and d[2] in "6789":
        d = d[2:]
    elif len(d) == 11 and d.startswith("0") and d[1] in "6789":
        d = d[1:]
    return d


def is_valid_email(raw: str) -> bool:
    s = (raw or "").strip()
    return bool(re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", s))


def is_valid_phone(raw: str) -> bool:
    """Indian mobile only: 10 digits starting with 6, 7, 8, or 9. +91 is removed first."""
    d = norm_phone(raw)
    return bool(re.fullmatch(r"[6-9]\d{9}", d))


def format_phone(raw: str) -> str:
    d = norm_phone(raw)
    return d if is_valid_phone(raw) else (raw or "").strip()


def norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_excel_date(v):
    """Accept Excel serials (int/float) + common text formats. Returns date|None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        from datetime import datetime as dt
        base = date(1899, 12, 30)
        try:
            from datetime import timedelta
            return base + timedelta(days=int(v))
        except Exception:
            return None
    s = str(v).strip()
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%y", "%d-%m-%y", "%Y-%m-%d",
                "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d.%m.%Y "):
        try:
            from datetime import datetime as dt
            return dt.strptime(s, fmt).date()
        except Exception:
            continue
    m = re.match(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_quantity(raw: str):
    if not raw:
        return None
    s = str(raw).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


# These products may use an odd car count. Every other product must be even.
# The smallest count is 2. A blank value is stored as 2.
ODD_CAR_PRODUCTS = frozenset({
    "Puzzle Parking",
    "Pit Puzzle Parking",
    "Car Elevator",
    "Shuttle Parking",
    "ASRS Parking",
})


def canonical_product_name(name: str | None) -> str:
    key = norm_key(name or "")
    if not key:
        return ""
    return PRODUCT_ALIASES.get(key, str(name or "").strip())


def allows_odd_cars(product_name: str | None) -> bool:
    return canonical_product_name(product_name) in ODD_CAR_PRODUCTS


def normalize_car_count(raw, product_name: str | None = None) -> tuple[int | None, str | None]:
    """Return (count, error). Blank becomes 2. Counts start at 2.

    Odd counts are allowed only for Puzzle, Pit Puzzle, Car Elevator,
    Shuttle, and ASRS. Every other product must be an even number.
    """
    text = str(raw or "").strip()
    if not text:
        return 2, None
    parsed = parse_quantity(text)
    if parsed is None or parsed != int(parsed):
        return None, "Number of cars must be a whole number starting at 2"
    cars = int(parsed)
    if cars < 2:
        return None, "Number of cars starts at 2"
    if cars % 2 == 1 and not allows_odd_cars(product_name):
        return None, (
            "Number of cars must be even for Two Post Stack Parking, Four Post Stack Parking, "
            "Pit Stack Parking, and Tower Parking. Odd numbers are only for Puzzle Parking, "
            "Pit Puzzle Parking, Car Elevator, Shuttle Parking, and ASRS Parking"
        )
    return cars, None
