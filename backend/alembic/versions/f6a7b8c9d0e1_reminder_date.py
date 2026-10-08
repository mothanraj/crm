"""Work-progress reminder date on leads and history."""
from alembic import op
import sqlalchemy as sa
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

def upgrade():
    for table in ("leads", "lead_activities"):
        op.add_column(table, sa.Column("reminder_date", sa.Date(), nullable=True))

def downgrade():
    for table in ("lead_activities", "leads"):
        op.drop_column(table, "reminder_date")
