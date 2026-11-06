-- Live Supabase production repair deployed 2026-11-06 UTC, organization Free.
-- Four existing SECURITY DEFINER functions were externally executable by
-- anon/authenticated. Provider security advisors warned of direct public RPC.
-- This migration preserves their definitions, real monitoring trigger, records,
-- sources and service-role worker access, while removing public direct execute.
--
-- Native RED: advisory categories 0028 and 0029 each counted four warnings.
-- Native GREEN: anon/authenticated=false and service_role=true on all four.
-- After provider advisory readback both categories disappeared.
-- Monitoring trigger trg_provider_plugin_check_to_health remains enabled.
-- Rollback requires review of public-caller risk: GRANT EXECUTE ... TO roles;
-- original functions/rows remain untouched.

REVOKE EXECUTE ON FUNCTION public.capture_meeting_intelligence_cohort_snapshot_v1()
 FROM PUBLIC,anon,authenticated;
REVOKE EXECUTE ON FUNCTION public.capture_meeting_intelligence_cohort_snapshot_v2()
 FROM PUBLIC,anon,authenticated;
REVOKE EXECUTE ON FUNCTION public.project_provider_plugin_check_to_health()
 FROM PUBLIC,anon,authenticated;

GRANT EXECUTE ON FUNCTION public.capture_meeting_intelligence_cohort_snapshot_v1()
 TO service_role;
GRANT EXECUTE ON FUNCTION public.capture_meeting_intelligence_cohort_snapshot_v2()
 TO service_role;
GRANT EXECUTE ON FUNCTION public.project_provider_plugin_check_to_health()
 TO service_role;
