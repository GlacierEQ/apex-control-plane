-- Live provider repair on supabase-glaciereq; verified by two independent reads.
-- Red: anon=true, authenticated=true, service_role=true, read_only_user=true;
-- Supabase SECURITY lint flagged public EXECUTE of this SECURITY DEFINER
-- function as a risk of unauthenticated writes to apex_loop_health.
-- Green: anon=false, authenticated=false, read_only_user=false,
-- service_role=true. Relevant linter warning count fell from 4 to 3.
-- No rows, evidence, scheduled jobs or credentials were touched.
-- Other functions flagged by the advisor are not changed here.
REVOKE EXECUTE ON FUNCTION public.record_provider_native_connector_probe_v1(
  text,text,text,jsonb,integer
) FROM PUBLIC, anon, authenticated, supabase_read_only_user;
GRANT EXECUTE ON FUNCTION public.record_provider_native_connector_probe_v1(
  text,text,text,jsonb,integer
) TO service_role;
