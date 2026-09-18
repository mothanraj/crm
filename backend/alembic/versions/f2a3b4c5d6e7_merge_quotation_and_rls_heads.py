"""Merge alembic heads: quotation_value + enable_rls.

Revision ID: f2a3b4c5d6e7
Revises: e0f1a2b3c4d5, e1f2a3b4c5d6
"""
from alembic import op  # noqa: F401

revision = "f2a3b4c5d6e7"
down_revision = ("e0f1a2b3c4d5", "e1f2a3b4c5d6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
