"""lead product_raw (preserve exact Excel product text)

Revision ID: d4e5f6g7h8i9
Revises: b7c8d9e0f1a2
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS product_raw TEXT DEFAULT '' NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS product_raw")
