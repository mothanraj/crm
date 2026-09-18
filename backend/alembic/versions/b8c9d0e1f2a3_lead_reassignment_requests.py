"""Employee → admin lead reassignment requests.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_reassignment_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lead_id UUID NOT NULL REFERENCES leads(id),
            requested_by UUID NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PENDING',
            reviewed_by UUID REFERENCES users(id),
            review_note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            reviewed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_reassignment_requests_lead_id "
        "ON lead_reassignment_requests (lead_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_reassignment_requests_requested_by "
        "ON lead_reassignment_requests (requested_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_reassignment_requests_status "
        "ON lead_reassignment_requests (status)"
    )
    # Match existing Supabase hardening: RLS on, no policies for anon/authenticated.
    op.execute("ALTER TABLE public.lead_reassignment_requests ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.lead_reassignment_requests FROM anon, authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_reassignment_requests")
