-- APEX connector dashboard: make the query obey source-table RLS.
-- Native negative test (2026-11-07 HST, before repair):
--   SET LOCAL ROLE authenticated: connector_work_bundles rows = 0,
--   while this owner-privileged view exposed aggregate bundle_count = 6.
-- Transactional security_invoker dry run: same role retained 103 catalog
-- connector rows but bundle_count changed to 0, respecting RLS.
-- Preserve the existing view query, column contract and service_role access.
-- This is an access-control repair, not a claim that provider operations ran.
ALTER VIEW public.connector_mega_plane_status_v1
  SET (security_invoker = true);
