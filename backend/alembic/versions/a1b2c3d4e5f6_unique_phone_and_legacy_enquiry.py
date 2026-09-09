"""unique phone and legacy enquiry

Revision ID: a1b2c3d4e5f6
Revises: 25d378c08ca0
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "25d378c08ca0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial uniques: allow blanks/nulls, block real duplicates
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_legacy_enquiry_no "
        "ON leads (legacy_enquiry_no) WHERE legacy_enquiry_no IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_contact_number_norm "
        "ON leads (contact_number_norm) WHERE contact_number_norm <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_leads_contact_number_norm")
    op.execute("DROP INDEX IF EXISTS uq_leads_legacy_enquiry_no")
