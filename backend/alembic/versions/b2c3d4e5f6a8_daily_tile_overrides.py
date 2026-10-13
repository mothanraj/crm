"""Employee daily tile count overrides (employee-only)."""
from alembic import op
import sqlalchemy as sa
revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "daily_tile_overrides",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("tile_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_daily_tile_overrides_employee_day", "daily_tile_overrides", ["employee_id", "day"])
    op.create_unique_constraint("uq_daily_tile_overrides_employee_day_tile", "daily_tile_overrides", ["employee_id", "day", "tile_key"])

def downgrade():
    op.drop_constraint("uq_daily_tile_overrides_employee_day_tile", "daily_tile_overrides", type_="unique")
    op.drop_index("ix_daily_tile_overrides_employee_day", table_name="daily_tile_overrides")
    op.drop_table("daily_tile_overrides")
