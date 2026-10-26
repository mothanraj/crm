"""Add indexes for employee lead lists at scale."""
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_emp_active_updated "
            "ON leads (primary_employee_id, is_active, updated_at DESC, id DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_active_updated "
            "ON leads (is_active, updated_at DESC, id DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_leads_emp_active_updated")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_leads_active_updated")
