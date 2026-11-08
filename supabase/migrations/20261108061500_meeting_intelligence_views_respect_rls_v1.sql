-- Respect underlying operator-scoped RLS in meeting intelligence read models.
-- Before: authenticated, non-operator source counts = 0 while five views
-- showed 30 + 21 + 6 + 7 + 18 = 82 derived rows.
-- Transactional dry-run of security_invoker=true made all five counts 0.
-- Preserve view SQL, authenticated access to permitted rows, and privileged
-- service_role access; no primary evidence or source records are altered.
ALTER VIEW public.meeting_intelligence_connector_cohort_drift_v1 SET (security_invoker = true);
ALTER VIEW public.meeting_intelligence_connector_cohort_drift_v2 SET (security_invoker = true);
ALTER VIEW public.meeting_intelligence_connector_cohort_latest_v1 SET (security_invoker = true);
ALTER VIEW public.meeting_intelligence_connector_cohort_latest_v2 SET (security_invoker = true);
ALTER VIEW public.meeting_intelligence_integration_route_health_v1 SET (security_invoker = true);
