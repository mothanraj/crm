"""lead email flags (Brevo reminder + digest idempotency)

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS overdue_digest_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS overdue_digest_at")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS reminder_sent_at")
