"""Persist Excel import preview rows on the batch (Render-safe).

Revision ID: e5f6a7b8c9d0
Revises: c9d0e1f2a3b4
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS preview_rows JSONB")
    op.execute("ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS assigned_count INTEGER DEFAULT 0")
    op.execute("ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS pending_count INTEGER DEFAULT 0")
    op.execute("ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS error_message TEXT DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE import_batches DROP COLUMN IF EXISTS error_message")
    op.execute("ALTER TABLE import_batches DROP COLUMN IF EXISTS pending_count")
    op.execute("ALTER TABLE import_batches DROP COLUMN IF EXISTS assigned_count")
    op.execute("ALTER TABLE import_batches DROP COLUMN IF EXISTS preview_rows")
