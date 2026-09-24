"""Indexes used by lead analytics date, city, and progress filters."""
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_active_enquiry_date ON leads (is_active, enquiry_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_city ON leads (city)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_activities_progress ON lead_activities (lead_id, activity_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lead_activities_progress")
    op.execute("DROP INDEX IF EXISTS ix_leads_city")
    op.execute("DROP INDEX IF EXISTS ix_leads_active_enquiry_date")
