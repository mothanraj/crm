"""Add drawing received and drawing sent work statuses."""
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c3d4e5f6a7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO lead_statuses (id, name, is_terminal, is_lost, sort_order)
        SELECT gen_random_uuid(), 'Drawing received', false, false, 8
        WHERE NOT EXISTS (SELECT 1 FROM lead_statuses WHERE name = 'Drawing received')
    """)
    op.execute("""
        INSERT INTO lead_statuses (id, name, is_terminal, is_lost, sort_order)
        SELECT gen_random_uuid(), 'Drawing sent', false, false, 9
        WHERE NOT EXISTS (SELECT 1 FROM lead_statuses WHERE name = 'Drawing sent')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM lead_statuses WHERE name IN ('Drawing received', 'Drawing sent')")
