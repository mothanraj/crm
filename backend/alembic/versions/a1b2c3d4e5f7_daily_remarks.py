"""Employee daily remarks diary (employee-only)."""
from alembic import op
import sqlalchemy as sa
revision = "a1b2c3d4e5f7"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "daily_remarks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_daily_remarks_employee_day", "daily_remarks", ["employee_id", "day"])

def downgrade():
    op.drop_index("ix_daily_remarks_employee_day", table_name="daily_remarks")
    op.drop_table("daily_remarks")
