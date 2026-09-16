-- Fix Supabase Security Advisor: RLS Disabled in Public (19 errors)
-- Run in Supabase Dashboard > SQL Editor.
-- Safe for this project: FastAPI uses Direct postgres/service_role URL
-- which bypasses RLS. ENABLE RLS with NO policies = deny anon/authenticated
-- REST API access while backend keeps working. Do NOT add USING(true) policies.

-- 0. Check what is still exposed (expect 0 rows after fix)
-- SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=false;

ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assignment_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.enquiry_sequence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.import_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_statuses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.quotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

-- 1. Verify: Advisors > Security Advisor > Rerun linter -> 0 errors
-- 2. Negative test: GET https://<ref>.supabase.co/rest/v1/leads with anon key -> 401/403
