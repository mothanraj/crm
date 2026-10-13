"""Per-tile notes on daily remarks (optional tile tag)."""
from alembic import op
import sqlalchemy as sa
revision = "c3d4e5f6a7b9"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("daily_remarks", sa.Column("tile_key", sa.Text(), nullable=True))
    op.create_index("ix_daily_remarks_employee_day_tile", "daily_remarks", ["employee_id", "day", "tile_key"])

def downgrade():
    op.drop_index("ix_daily_remarks_employee_day_tile", table_name="daily_remarks")
    op.drop_column("daily_remarks", "tile_key")
