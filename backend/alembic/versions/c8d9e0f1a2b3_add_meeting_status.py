"""add Meeting work status"""
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO lead_statuses (id, name, is_terminal, is_lost, sort_order)
        SELECT gen_random_uuid(), 'Meeting', false, false, 7
        WHERE NOT EXISTS (SELECT 1 FROM lead_statuses WHERE name = 'Meeting')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM lead_statuses WHERE name = 'Meeting'")
