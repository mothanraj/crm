"""Store quotation values on leads and work history."""
from alembic import op
import sqlalchemy as sa
revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

def upgrade():
    for table in ("leads", "lead_activities"):
        op.add_column(table, sa.Column("quotation_value", sa.Numeric(16, 2), nullable=True))

def downgrade():
    for table in ("lead_activities", "leads"):
        op.drop_column(table, "quotation_value")
