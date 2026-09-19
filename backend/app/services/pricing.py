"""Canonical product pricing and Lead Value calculation.

Lead Value = number_of_cars × price_per_car  (excl. GST)
  — except Two Post / Four Post / Pit Stack, where Lead Value is half:
    Lead Value = number_of_cars × price_per_car × 0.5

GST (18%) is stored separately as gst_amount (on the lead value).
All money amounts are stored and returned as whole rupees (no paise / decimals).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

GST_RATE = Decimal("0.18")
GST_PERCENT = Decimal("18")
RUPEE = Decimal("1")

# Exact product names → actual parking price per car (INR, excl. GST)
PRODUCT_PRICES: dict[str, int] = {
    "Two Post Stack Parking": 150_000,
    "Four Post Stack Parking": 250_000,
    "Pit Stack Parking": 250_000,
    "Puzzle Parking": 350_000,
    "Pit Puzzle Parking": 350_000,
    "Tower Parking": 450_000,
    "Shuttle Parking": 500_000,
    "Car Elevator": 2_000_000,
    "ASRS Parking": 500_000,
}

CANONICAL_PRODUCTS = list(PRODUCT_PRICES.keys())

# These use half of (price × cars) for Lead Value; Price/Car still shows full parking value.
HALF_LEAD_VALUE_PRODUCTS = frozenset({
    "Two Post Stack Parking",
    "Four Post Stack Parking",
    "Pit Stack Parking",
})

# Old seed / combined names → new canonical names (migration / alias remap)
PRODUCT_RENAMES: dict[str, str] = {
    "Four Post Parking / Pit Stack Parking": "Four Post Stack Parking",
    "Puzzle Parking / Pit Puzzle Parking": "Puzzle Parking",
    "Puzzle Parking System": "Puzzle Parking",
    "Tower Parking System": "Tower Parking",
    "Shuttle / Robotic Parking": "Shuttle Parking",
    "Pit / Fixed Stack Parking": "Pit Stack Parking",
    "MLCP / ASRS / Custom": "ASRS Parking",
}


def _rupee(v: Decimal) -> Decimal:
    """Round money to nearest whole rupee."""
    return v.quantize(RUPEE, rounding=ROUND_HALF_UP)


def _as_int(v: Decimal | None) -> int | None:
    if v is None:
        return None
    return int(_rupee(v))


def price_for_product(name: str | None) -> Decimal | None:
    if not name:
        return None
    # Accept legacy combined names during transition
    resolved = PRODUCT_RENAMES.get(name, name)
    raw = PRODUCT_PRICES.get(resolved)
    if raw is None:
        return None
    return Decimal(raw)


def uses_half_lead_value(product_name: str | None) -> bool:
    if not product_name:
        return False
    resolved = PRODUCT_RENAMES.get(product_name, product_name)
    return resolved in HALF_LEAD_VALUE_PRODUCTS


def calc_lead_value(
    number_of_cars: Any,
    price_per_car: Any,
    *,
    gst_rate: Decimal = GST_RATE,
    product_name: str | None = None,
) -> dict[str, Any]:
    """Authoritative Lead Value math (excl. GST). Returns None amounts when inputs invalid."""
    try:
        cars = Decimal(str(number_of_cars)) if number_of_cars is not None and str(number_of_cars).strip() != "" else None
    except Exception:
        cars = None
    try:
        price = Decimal(str(price_per_car)) if price_per_car is not None and str(price_per_car).strip() != "" else None
    except Exception:
        price = None

    out: dict[str, Any] = {
        "number_of_cars": None,
        "price_per_car": None,
        "gst_percent": float(GST_PERCENT),
        "base_value": None,
        "gst_amount": None,
        "lead_value": None,
        "half_rate": uses_half_lead_value(product_name),
    }
    if cars is None or price is None:
        return out
    if cars <= 0 or price < 0:
        out["number_of_cars"] = int(cars) if cars == cars.to_integral_value() else float(cars)
        out["price_per_car"] = _as_int(price) if price >= 0 else None
        return out

    cars_i = int(cars) if cars == cars.to_integral_value() else int(_rupee(cars))
    price_i = _as_int(price)
    full = _rupee(Decimal(cars_i) * Decimal(price_i))
    lead = _rupee(full / 2) if uses_half_lead_value(product_name) else full
    gst = _rupee(lead * gst_rate)
    out.update({
        "number_of_cars": cars_i,
        "price_per_car": price_i,
        "base_value": int(full),
        "gst_amount": int(gst),
        "lead_value": int(lead),
    })
    return out


def apply_pricing_to_lead(lead, product_name: str | None = None, product=None) -> None:
    """Mutate lead fields from product price + quantity_num. Clears value if incomplete."""
    name = product_name
    price = None
    if product is not None:
        name = getattr(product, "name", name)
        raw_price = getattr(product, "price_per_car", None)
        if raw_price is not None:
            price = Decimal(str(raw_price))
    if price is None:
        price = price_for_product(name)

    cars = lead.quantity_num
    result = calc_lead_value(cars, price, product_name=name)
    lead.price_per_car = result["price_per_car"]
    lead.gst_amount = result["gst_amount"]
    lead.lead_value = result["lead_value"]
    if result["number_of_cars"] is not None and cars is None:
        lead.quantity_num = result["number_of_cars"]


def round_money(value: Any) -> int | None:
    """Round any money-like input to a whole rupee integer (or None)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return _as_int(Decimal(str(value)))
    except Exception:
        return None
