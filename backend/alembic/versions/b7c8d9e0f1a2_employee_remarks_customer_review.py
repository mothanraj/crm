"""employee remarks and customer review

Revision ID: b7c8d9e0f1a2
Revises: c3d4e5f6g7h8
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS employee_remarks TEXT DEFAULT '' NOT NULL")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS customer_review TEXT DEFAULT '' NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS customer_review")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS employee_remarks")
