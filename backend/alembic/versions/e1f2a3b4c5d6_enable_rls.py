"""enable RLS to silence Supabase Security Advisor (RLS Disabled in Public)

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
"""
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

# All tables in public schema exposed via Supabase PostgREST.
# Backend (FastAPI + SQLAlchemy via postgres/service_role DATABASE_URL)
# bypasses RLS, so ENABLE RLS with NO policies = deny anon/authenticated
# API access while keeping backend working.
TABLES = [
    "alembic_version",
    "assignment_state",
    "enquiry_sequence",
    "import_batches",
    "import_errors",
    "lead_activities",
    "lead_assignments",
    "lead_documents",
    "lead_sources",
    "lead_status_history",
    "lead_statuses",
    "leads",
    "notifications",
    "product_aliases",
    "products",
    "quotations",
    "roles",
    "site_visits",
    "users",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    # Block Supabase Data API roles explicitly. No policies = deny all.
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
