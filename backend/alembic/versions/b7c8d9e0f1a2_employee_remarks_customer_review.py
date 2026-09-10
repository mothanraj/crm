"""employee remarks and customer review

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("employee_remarks", sa.Text(), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("customer_review", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("leads", "customer_review")
    op.drop_column("leads", "employee_remarks")
