-- Source mirror of deployed Supabase compiler, reconciled with native correction migration 20261107083000.
-- Source-only correction: hydration is not downstream application; the original provider migration remains recorded.
-- Existing owner: GlacierEQ/apex-control-plane (kjebemdgvjvuutzvhbtp).
-- Native SQL fallback for the HTTP 402 memory-context compiler.
-- Reuses memory_authoritative_candidates_v1, memory_context_packets_v1,
-- upsert_cognition_context_binding_v1. No new scheduler or controller.
-- Acceptance: native packet ec1da303-9d8b-4101-a026-3f9e19070e36
-- returned 12 sources, zero cross-case, bound subject/hashes matched.
-- Repeated call reused same packet; cross-case binding was rejected.
-- Scope: provider service_role only. Original Edge 402 remains open.
-- Rollback: DROP FUNCTION public.compile_memory_context_native_v1(text,text,integer,text,text,text);
-- Do not delete packets or historical evidence on rollback.

CREATE OR REPLACE FUNCTION public.compile_memory_context_native_v1(p_query text, p_case_id text DEFAULT NULL::text, p_top_k integer DEFAULT 12, p_subject_type text DEFAULT NULL::text, p_subject_id text DEFAULT NULL::text, p_mission text DEFAULT 'continuity'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'extensions', 'pg_temp'
AS $function$
DECLARE
  v_q text := btrim(coalesce(p_query,''));
  v_case text := nullif(btrim(p_case_id),'');
  v_limit integer := greatest(4,least(coalesce(p_top_k,12),24));
  v_mission text := nullif(btrim(coalesce(p_mission,'')),'');
  v_sha text;
  v_packet public.memory_context_packets_v1%rowtype;
  v_original public.cognition_context_bindings_v1%rowtype;
  v_bound public.cognition_context_bindings_v1%rowtype;
  v_context jsonb;
  v_verified jsonb := '[]'::jsonb;
  v_unresolved jsonb := '[]'::jsonb;
  v_count integer := 0;
  v_high_count integer := 0;
BEGIN
  IF v_q='' OR length(v_q)>8000 THEN
    RAISE EXCEPTION 'native_context_query_required_max_8000';
  END IF;
  IF v_mission IS NULL THEN
    RAISE EXCEPTION 'native_context_mission_required';
  END IF;
  IF (p_subject_type IS NULL) <> (p_subject_id IS NULL) THEN
    RAISE EXCEPTION 'native_context_binding_subject_pair_required';
  END IF;
  IF p_subject_type IS NOT NULL THEN
    IF p_subject_type NOT IN ('connector_bundle','mcp_run') THEN
      RAISE EXCEPTION 'native_context_binding_type_not_supported';
    END IF;
    SELECT * INTO v_original FROM public.cognition_context_bindings_v1
      WHERE subject_type=p_subject_type AND subject_id=p_subject_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'native_context_binding_subject_not_found';
    END IF;
    IF v_original.case_id IS DISTINCT FROM v_case THEN
      RAISE EXCEPTION 'native_context_binding_case_scope_mismatch';
    END IF;
  END IF;

  v_sha:=encode(extensions.digest(v_q,'sha256'),'hex');
  SELECT * INTO v_packet
    FROM public.memory_context_packets_v1
    WHERE query_sha256=v_sha
      AND case_id IS NOT DISTINCT FROM v_case
      AND mission=v_mission
      AND created_by='native-supabase-memory-fallback-v1'
      AND created_at>=now()-interval '10 minutes'
      AND expires_at>now()
    ORDER BY created_at DESC LIMIT 1;

  IF NOT FOUND THEN
    WITH retrieved AS (
      SELECT a.*,x.recall_score,
      lower(coalesce(a.authority_status,'unresolved')) IN
      ('verified','source_verified','provider_native','external_verified',
       'operator_directive','operator_observation','firsthand') AS high_authority
      FROM public.memory_authoritative_candidates_v1(v_q,v_case,v_limit) x
      JOIN public.apex_memories a ON a.id=x.memory_id
      WHERE a.case_id IS NOT DISTINCT FROM v_case
    )
    SELECT
      coalesce(jsonb_agg(
        jsonb_build_object(
          'memory_id',id,'content',content,'case_id',case_id,
          'memory_type',memory_type,'source',source,'importance_score',importance_score,
          'authority_status',authority_status,'source_id',source_id,'source_uri',source_uri,
          'source_hash',source_hash,'source_type',source_type,
          'verification_method',verification_method,'observed_at',observed_at,
          'court_facing',court_facing,'contradiction_links',contradiction_links,
          'supersedes',supersedes,'created_at',created_at,
          'retrieval',jsonb_build_object('score',recall_score,'mem0_id',null,
                                        'routes',jsonb_build_array('supabase')))
        ORDER BY recall_score DESC,created_at DESC
      ) FILTER (WHERE high_authority),'[]'::jsonb),
      coalesce(jsonb_agg(
        jsonb_build_object(
          'memory_id',id,'content',content,'case_id',case_id,
          'memory_type',memory_type,'source',source,'importance_score',importance_score,
          'authority_status',authority_status,'source_id',source_id,'source_uri',source_uri,
          'source_hash',source_hash,'source_type',source_type,
          'verification_method',verification_method,'observed_at',observed_at,
          'court_facing',court_facing,'contradiction_links',contradiction_links,
          'supersedes',supersedes,'created_at',created_at,
          'retrieval',jsonb_build_object('score',recall_score,'mem0_id',null,
                                        'routes',jsonb_build_array('supabase')))
        ORDER BY recall_score DESC,created_at DESC
      ) FILTER (WHERE NOT high_authority),'[]'::jsonb),
      count(*)::integer,
      count(*) FILTER (WHERE high_authority)::integer
    INTO v_verified,v_unresolved,v_count,v_high_count
    FROM retrieved;

    v_context:=jsonb_build_object(
      'schema','glaciereq.memory.context.v3',
      'compiled_at',clock_timestamp(),
      'query',v_q,
      'mission',v_mission,
      'agent_id','native_sql_fallback',
      'objective',v_q,
      'matter_key',v_case,
      'scope',jsonb_build_object('user_id','operator','case_id',v_case),
      'compilation_policy',jsonb_build_object(
        'context_first',true,
        'transition_semantics','enrichment_not_permission',
        'missing_context_effect','recovery_debt_and_route_enrichment',
        'mission_stop_authority',false,
        'operator_authority_preserved',true,
        'native_sql_fallback_for_http_402',true),
      'invariants',jsonb_build_object(
        'mem0_is_projection',true,
        'mem0_text_never_promoted_without_supabase_rehydration',true,
        'unresolved_not_promoted_to_verified',true,
        'superseded_records_excluded',true,
        'provider_scores_are_retrieval_signals_not_truth_scores',true,
        'exact_case_scope',true),
      'verified_or_high_authority',v_verified,
      'unresolved_or_derived',v_unresolved,
      'retrieval_diagnostics',jsonb_build_object(
        'mem0',jsonb_build_object('status','not_attempted','reason','native_sql_fallback'),
        'supabase',jsonb_build_object('status','ok','returned',v_count),
        'exclusions',jsonb_build_object('superseded',0,'case_scope',0,'missing',0),
        'fallback','authenticated_native_postgres')
    );
    INSERT INTO public.memory_context_packets_v1(
      user_id,case_id,mission,agent_id,objective,matter_key,compilation_policy,
      query_text,query_sha256,context_json,snapshot_hash,retrieval_status,source_counts,
      expires_at,created_by
    ) VALUES (
      'operator',v_case,v_mission,'native_sql_fallback',v_q,v_case,
      v_context->'compilation_policy',v_q,v_sha,v_context,
      encode(extensions.digest(v_context::text,'sha256'),'hex'),
      v_context->'retrieval_diagnostics',
      jsonb_build_object('verified_or_high_authority',v_high_count,
        'unresolved_or_derived',v_count-v_high_count,
        'mem0_candidates',0,'supabase_candidates',v_count),
      now()+interval '24 hours',
      'native-supabase-memory-fallback-v1'
    ) RETURNING * INTO v_packet;
  ELSE
    v_context:=v_packet.context_json;
  END IF;

  IF p_subject_type IS NOT NULL THEN
    SELECT * INTO v_bound
    FROM public.upsert_cognition_context_binding_v1(
      p_subject_type=>v_original.subject_type,
      p_subject_id=>v_original.subject_id,
      p_objective=>v_original.objective,
      p_case_id=>v_original.case_id,
      p_mission=>v_original.mission,
      p_agent_id=>coalesce(v_original.agent_id,'native_sql_fallback'),
      p_hydration_state=>'hydrated',
      p_packet_id=>v_packet.packet_id,
      p_packet_snapshot_hash=>v_packet.snapshot_hash,
      p_context_created_at=>v_packet.created_at,
      p_context_expires_at=>v_packet.expires_at,
      p_recovery_debt=>jsonb_build_object('edge_http_402_unresolved',true,'native_sql_fallback_hydrated_only',true,'downstream_application_unverified',true),
      p_retrieval_status=>v_packet.retrieval_status,
      p_metadata=>jsonb_build_object(
        'native_sql_fallback_packet',v_packet.packet_id,
        'native_sql_fallback_version','v1',
        'original_edge_unrestored',true)
    );
  END IF;

  RETURN jsonb_build_object(
    'packet_id',v_packet.packet_id,
    'snapshot_hash',v_packet.snapshot_hash,
    'expires_at',v_packet.expires_at,
    'source_counts',v_packet.source_counts,
    'case_id',v_case,
    'bound_subject_type',p_subject_type,
    'bound_subject_id',p_subject_id,
    'retrieval_status',v_packet.retrieval_status,
    'context',v_context
  );
END;
$function$;
REVOKE ALL ON FUNCTION public.compile_memory_context_native_v1(text,text,integer,text,text,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.compile_memory_context_native_v1(text,text,integer,text,text,text)
  TO service_role;
