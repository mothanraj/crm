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
}

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
    "two post stack parking": "Two Post Stack Parking",
    "two post stack parking system": "Two Post Stack Parking",
    "two_post_stack_parking": "Two Post Stack Parking",
    "two post stack parking.": "Two Post Stack Parking",
    "1+1": "Two Post Stack Parking", "two level stack": "Two Post Stack Parking",
    "stack": "Two Post Stack Parking", "stack parking": "Two Post Stack Parking",
    "stack parking ": "Two Post Stack Parking",
    "puzzle parking system": "Puzzle Parking System",
    "puzzle_parking_system": "Puzzle Parking System", "puzzle": "Puzzle Parking System",
    "pit puzzle parking": "Pit / Fixed Stack Parking", "pit stack": "Pit / Fixed Stack Parking",
    "pit stack parking system": "Pit / Fixed Stack Parking",
    "three level stack parking": "Pit / Fixed Stack Parking",
    "tower parking system": "Tower Parking System",
    "tower_parking_system": "Tower Parking System", "tower": "Tower Parking System",
    "shuttle": "Shuttle / Robotic Parking", "shuttle/robotic_parking_": "Shuttle / Robotic Parking",
    "robotic shuttle": "Shuttle / Robotic Parking", "robotic / shuttle parking": "Shuttle / Robotic Parking",
    "ss car parking (238 cars)": "Shuttle / Robotic Parking",
    "car lift": "Pit / Fixed Stack Parking",
}

CANONICAL_PRODUCTS = [
    "Two Post Stack Parking", "Puzzle Parking System", "Tower Parking System",
    "Shuttle / Robotic Parking", "Pit / Fixed Stack Parking", "MLCP / ASRS / Custom",
]
CANONICAL_SOURCES = [
    "Facebook/Instagram", "Google Ads", "India Mart", "Direct Call", "Referral",
    "WhatsApp", "Email Campaign", "Email Enquiry", "SEO", "Others", "Expo/Stall",
]
# Work-progress values used by employees after speaking to the customer (Excel "Staus" column + pipeline extras).
CANONICAL_STATUSES = [
    ("New Lead", False, False, 1),
    ("In Followup", False, False, 2),
    ("A - Prospect", False, False, 3),
    ("A+ - Immediate", False, False, 4),
    ("RNR / Not reachable", False, False, 5),
    ("Site Visit", False, False, 6),
    ("Quotation sent", False, False, 7),
    ("Channel Partner", False, False, 8),
    ("Approval Client", False, False, 9),
    ("Investor", False, False, 10),
    ("Not Interested", False, True, 11),
    ("Not Interested/Spam", False, True, 12),
    ("Converted", True, False, 13),
    ("Duplicate", True, True, 14),
]
def norm_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if len(d) > 10 and d.startswith("91"):
        d = d[-10:]
    return d


def is_valid_email(raw: str) -> bool:
    s = (raw or "").strip()
    return bool(re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", s))


def is_valid_phone(raw: str) -> bool:
    """Indian mobile: 10 digits starting 6–9; optional +91/0 prefix."""
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
    m = re.search(r"\d+", str(raw).replace(",", ""))
    return float(m.group()) if m else None
