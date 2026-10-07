"""Per-reminder done flags (strike instead of clear)."""
from alembic import op
import sqlalchemy as sa
revision = "f7a8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

def upgrade():
    for table in ("leads", "lead_activities"):
        op.add_column(table, sa.Column("reminder_done", sa.Boolean(), nullable=False, server_default="false"))

def downgrade():
    for table in ("lead_activities", "leads"):
        op.drop_column(table, "reminder_done")
