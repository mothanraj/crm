"""lead assignment email idempotency flag

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS assignment_email_sent_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS assignment_email_sent_at")
