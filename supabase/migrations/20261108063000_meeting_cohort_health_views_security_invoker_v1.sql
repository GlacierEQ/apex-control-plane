-- Close remaining Supabase security-definer-view advisor errors.
-- Both views select from already security_invoker meeting cohort latest views.
-- Preserve the exact existing projections and service_role access while
-- ensuring future caller access cannot silently revert to owner privileges.
ALTER VIEW public.meeting_intelligence_connector_cohort_health_v1 SET (security_invoker = true);
ALTER VIEW public.meeting_intelligence_connector_cohort_health_v2 SET (security_invoker = true);
