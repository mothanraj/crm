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
    ("Assigned", False, False, 2),
    ("In Followup", False, False, 3),
    ("A - Prospect", False, False, 4),
    ("A+ - Immediate", False, False, 5),
    ("RNR / Not reachable", False, False, 6),
    ("Site Visit", False, False, 7),
    ("Quotation sent", False, False, 8),
    ("Channel Partner", False, False, 9),
    ("Approval Client", False, False, 10),
    ("Investor", False, False, 11),
    ("Not Interested", False, True, 12),
    ("Not Interested/Spam", False, True, 13),
    ("Converted", True, False, 14),
    ("Duplicate", True, True, 15),
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
