"""store category on each work progress activity"""
from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS customer_review TEXT DEFAULT '' NOT NULL")
    op.execute("""
        UPDATE lead_activities AS activity
        SET customer_review = lead.customer_review
        FROM leads AS lead
        WHERE activity.lead_id = lead.id
          AND activity.activity_type = 'Work Progress'
          AND activity.customer_review = ''
          AND lead.customer_review <> ''
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE lead_activities DROP COLUMN IF EXISTS customer_review")
