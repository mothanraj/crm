"""Add product prices + lead value fields; remaster 7 parking products.

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
"""
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

PRODUCT_PRICES = {
    "Two Post Stack Parking": 150000,
    "Four Post Parking / Pit Stack Parking": 250000,
    "Puzzle Parking / Pit Puzzle Parking": 350000,
    "Tower Parking": 450000,
    "Shuttle Parking": 500000,
    "Car Elevator": 2000000,
    "ASRS Parking": 500000,
}

# Old product name → new product name
RENAMES = {
    "Puzzle Parking System": "Puzzle Parking / Pit Puzzle Parking",
    "Tower Parking System": "Tower Parking",
    "Shuttle / Robotic Parking": "Shuttle Parking",
    "Pit / Fixed Stack Parking": "Four Post Parking / Pit Stack Parking",
    "MLCP / ASRS / Custom": "ASRS Parking",
}


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_per_car NUMERIC(16,2) DEFAULT 0")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS price_per_car NUMERIC(16,2)")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS gst_amount NUMERIC(16,2)")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_value NUMERIC(16,2)")

    # Ensure all 7 canonical products exist
    for name, price in PRODUCT_PRICES.items():
        op.execute(
            f"""
            INSERT INTO products (id, name, description, price_per_car, is_active)
            SELECT gen_random_uuid(), '{name.replace("'", "''")}', '', {price}, true
            WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = '{name.replace("'", "''")}')
            """
        )
        op.execute(
            f"""
            UPDATE products
            SET price_per_car = {price}, is_active = true
            WHERE name = '{name.replace("'", "''")}'
            """
        )

    # Remap leads from old product names → new products
    for old, new in RENAMES.items():
        op.execute(
            f"""
            UPDATE leads
            SET product_id = (SELECT id FROM products WHERE name = '{new.replace("'", "''")}' LIMIT 1)
            WHERE product_id = (SELECT id FROM products WHERE name = '{old.replace("'", "''")}' LIMIT 1)
            """
        )
        op.execute(
            f"""
            UPDATE product_aliases
            SET product_id = (SELECT id FROM products WHERE name = '{new.replace("'", "''")}' LIMIT 1)
            WHERE product_id = (SELECT id FROM products WHERE name = '{old.replace("'", "''")}' LIMIT 1)
            """
        )
        # Deactivate old product rows (keep row for history / FK safety if any remain)
        op.execute(
            f"""
            UPDATE products SET is_active = false
            WHERE name = '{old.replace("'", "''")}'
            """
        )

    # Deactivate any other non-canonical active products
    names_sql = ", ".join("'" + n.replace("'", "''") + "'" for n in PRODUCT_PRICES)
    op.execute(
        f"""
        UPDATE products SET is_active = false
        WHERE name NOT IN ({names_sql})
        """
    )

    # Backfill lead_value = quantity_num × product.price_per_car × 1.18
    op.execute(
        """
        UPDATE leads l
        SET
          price_per_car = p.price_per_car,
          gst_amount = ROUND((COALESCE(l.quantity_num, 0) * COALESCE(p.price_per_car, 0) * 0.18)::numeric, 2),
          lead_value = ROUND((COALESCE(l.quantity_num, 0) * COALESCE(p.price_per_car, 0) * 1.18)::numeric, 2)
        FROM products p
        WHERE l.product_id = p.id
          AND l.quantity_num IS NOT NULL
          AND l.quantity_num > 0
          AND p.price_per_car IS NOT NULL
          AND p.price_per_car > 0
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS lead_value")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS gst_amount")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS price_per_car")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS price_per_car")
