"""E2E pricing checks for split products + half lead-value stack products."""
from decimal import Decimal

from app.db.session import SessionLocal
from app.models import Lead, Product, User
from app.services.pricing import PRODUCT_PRICES, HALF_LEAD_VALUE_PRODUCTS, calc_lead_value, apply_pricing_to_lead

# Expected lead_value = cars × price  (or × 0.5 for half-rate stack products)
EXPECTED = {
    ("Two Post Stack Parking", 10): 750_000,       # half of 1_500_000
    ("Four Post Stack Parking", 10): 1_250_000,    # half of 2_500_000
    ("Pit Stack Parking", 10): 1_250_000,          # half of 2_500_000
    ("Puzzle Parking", 10): 3_500_000,
    ("Pit Puzzle Parking", 10): 3_500_000,
    ("Tower Parking", 10): 4_500_000,
    ("Shuttle Parking", 10): 5_000_000,
    ("Car Elevator", 10): 20_000_000,
    ("ASRS Parking", 10): 5_000_000,
    ("Two Post Stack Parking", 1): 75_000,
    ("Two Post Stack Parking", 100): 7_500_000,
    ("Puzzle Parking", 1): 350_000,
}


def main():
    # Pure calc
    for (name, cars), want in EXPECTED.items():
        price = PRODUCT_PRICES[name]
        got = calc_lead_value(cars, price, product_name=name)["lead_value"]
        assert got == want, f"{name} x{cars}: got {got} want {want}"
        lead = calc_lead_value(cars, price, product_name=name)["lead_value"]
        assert calc_lead_value(cars, price, product_name=name)["gst_amount"] == round(lead * 0.18)

    # Invalid
    assert calc_lead_value(0, 150000, product_name="Two Post Stack Parking")["lead_value"] is None
    assert calc_lead_value(-1, 150000)["lead_value"] is None
    assert calc_lead_value(10, None)["lead_value"] is None
    assert calc_lead_value(None, 150000)["lead_value"] is None

    db = SessionLocal()
    try:
        products = {p.name: p for p in db.query(Product).filter_by(is_active=True).all()}
        assert set(products) == set(PRODUCT_PRICES), f"active products mismatch: {set(products)}"
        for name, price in PRODUCT_PRICES.items():
            assert float(products[name].price_per_car) == float(price), name

        # Pick any lead and recalculate for each product
        lead = db.query(Lead).filter(Lead.is_active.is_(True)).first()
        assert lead, "need at least one lead"
        admin = db.query(User).filter(User.email == "admin@crm.local").first()
        assert admin

        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        login = client.post("/api/auth/login", json={"email": "admin@crm.local", "password": "Admin123!"})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        masters = client.get("/api/masters", headers=headers)
        assert masters.status_code == 200
        mprods = masters.json()["products"]
        assert len(mprods) == len(PRODUCT_PRICES)
        assert all("price_per_car" in p for p in mprods)

        # Manipulation ignored
        for name, price in PRODUCT_PRICES.items():
            pid = str(products[name].id)
            for cars in (1, 10, 100):
                r = client.put(
                    f"/api/leads/{lead.id}",
                    headers=headers,
                    json={
                        "product_id": pid,
                        "quantity_raw": str(cars),
                        "lead_value": 1,
                        "price_per_car": 1,
                        "gst_amount": 1,
                    },
                )
                assert r.status_code == 200, r.text
                body = r.json()
                want = float(calc_lead_value(cars, price, product_name=name)["lead_value"])
                assert float(body["lead_value"]) == want, (name, cars, body["lead_value"], want)
                assert float(body["price_per_car"]) == float(price)
                assert float(body["gst_amount"]) == float(calc_lead_value(cars, price, product_name=name)["gst_amount"])

        # Invalid cars
        bad = client.put(f"/api/leads/{lead.id}", headers=headers, json={"quantity_raw": "0"})
        assert bad.status_code == 400
        bad2 = client.put(f"/api/leads/{lead.id}", headers=headers, json={"quantity_raw": "-5"})
        assert bad2.status_code == 400
        bad3 = client.put(f"/api/leads/{lead.id}", headers=headers, json={"quantity_raw": "abc"})
        assert bad3.status_code == 400

        # Analytics
        dash = client.get("/api/dashboard", headers=headers)
        assert dash.status_code == 200
        d = dash.json()
        assert "total_lead_value" in d
        assert "lead_value" in d
        assert len(d["lead_value"]["by_product"]) == len(PRODUCT_PRICES)

        lv = client.get("/api/dashboard/lead-value", headers=headers)
        assert lv.status_code == 200
        assert "by_product" in lv.json()

        calc = client.post("/api/leads/calculate-value", headers=headers, json={
            "product_id": str(products["Two Post Stack Parking"].id),
            "number_of_cars": 10,
        })
        assert calc.status_code == 200
        assert calc.json()["lead_value"] == 750000
        assert calc.json()["half_rate"] is True

        print("ALL PRICING TESTS PASSED")
        print("Half-rate products:", sorted(HALF_LEAD_VALUE_PRODUCTS))
    finally:
        db.close()


if __name__ == "__main__":
    main()
