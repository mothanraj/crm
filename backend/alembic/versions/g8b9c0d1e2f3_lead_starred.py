"""Allow users to mark leads as important."""
from alembic import op
import sqlalchemy as sa

revision = "g8b9c0d1e2f3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("leads", sa.Column("is_starred", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_leads_is_starred", "leads", ["is_starred"])

def downgrade():
    op.drop_index("ix_leads_is_starred", table_name="leads")
    op.drop_column("leads", "is_starred")
