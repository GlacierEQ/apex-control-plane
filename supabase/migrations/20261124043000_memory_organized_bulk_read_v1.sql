-- Applied to Supabase project kjebemdgvjvuutzvhbtp via native migration
-- memory_organized_bulk_read_v1_20261124; UUID-cursor correction applied via
-- memory_organized_bulk_read_v1_uuid_cursor_fix_20261124.
-- Production readback: first general page 1498 records / 1,999,718 bytes,
-- second page 1499, zero ID overlap and zero content/source-hash mismatch.
-- Case 1FDV-23-0001009: 389 records, zero cross-case;
-- multi-case index: 457 pointers with zero full-content leakage.
-- Checkpoint index: 2599 pointers / 1,999,507 bytes, no content leakage.
-- Anonymous/authenticated EXECUTE false; service_role EXECUTE true.
-- Live source was fixed after initial native test surfaced max(uuid) error.
-- Distinct from the 8 source-owned Monolith Mem information pillars.
-- APEX/Supabase canonical memory organization: provider-native, read-only bulk cursor.
-- The existing 8 Mem information pillars remain a separate source-owned topic directory:
-- GlacierEQ/monolith/catalog/memory_information_pillars.json.
-- This query layer does not infer topic membership, copy memories, persist packets, or
-- mutate/supersede original content. Its grouping labels are derived, not verification.
-- Rollback (no data loss): DROP FUNCTION public.memory_organized_batch_v1(
--   text,text,uuid,integer,integer,boolean,boolean);
CREATE OR REPLACE FUNCTION public.memory_organized_batch_v1(
  p_scope text DEFAULT 'general',
  p_case_id text DEFAULT NULL,
  p_after_id uuid DEFAULT NULL,
  p_max_records integer DEFAULT 2048,
  p_max_bytes integer DEFAULT 1500000,
  p_include_content boolean DEFAULT true,
  p_include_metadata boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
DECLARE
  v_scope text := lower(btrim(coalesce(p_scope,'general')));
  v_case text := nullif(btrim(p_case_id),'');
  v_max_records integer := least(greatest(coalesce(p_max_records,2048),1),5000);
  v_max_bytes integer := least(greatest(coalesce(p_max_bytes,1500000),65536),2000000);
  v_content boolean;
  v_metadata boolean;
  v_result jsonb;
BEGIN
  IF v_scope NOT IN ('general','case','checkpoint','matter_index','checkpoint_index') THEN
    RAISE EXCEPTION 'memory_batch_scope_unsupported';
  END IF;
  IF v_scope IN ('case','checkpoint') THEN
    IF v_case IS NULL OR length(v_case)>256 THEN
      RAISE EXCEPTION 'memory_batch_exact_case_id_required';
    END IF;
    IF (v_scope='checkpoint') IS DISTINCT FROM (left(v_case,4)='chk_') THEN
      RAISE EXCEPTION 'memory_batch_scope_identity_mismatch';
    END IF;
  ELSIF v_case IS NOT NULL THEN
    RAISE EXCEPTION 'memory_batch_index_or_general_rejects_case_id';
  END IF;
  -- Multi-case indexes intentionally return pointers only: never combine matter facts.
  v_content := coalesce(p_include_content,true)
     AND v_scope IN ('general','case','checkpoint');
  v_metadata := coalesce(p_include_metadata,false)
     AND v_scope IN ('general','case','checkpoint');

  WITH candidates AS MATERIALIZED (
    SELECT a.id,a.user_id,a.case_id,a.memory_type,a.content,a.source,
      a.source_id,a.source_uri,a.source_hash,a.source_type,a.authority_status,
      a.verification_method,a.created_at,a.observed_at,a.importance_score,
      a.mem0_id,a.supermemory_id,a.supersedes,a.court_facing,a.metadata
    FROM public.apex_memories AS a
    WHERE (p_after_id IS NULL OR a.id>p_after_id)
      AND (
        (v_scope='general' AND a.case_id IS NULL)
        OR (v_scope='case' AND a.case_id=v_case)
        OR (v_scope='checkpoint' AND a.case_id=v_case)
        OR (v_scope='matter_index' AND a.case_id IS NOT NULL AND left(a.case_id,4)<>'chk_')
        OR (v_scope='checkpoint_index' AND left(a.case_id,4)='chk_')
      )
    ORDER BY a.id
    LIMIT v_max_records+1
  ),
  successors AS MATERIALIZED (
    SELECT DISTINCT a.supersedes AS id FROM public.apex_memories a
    WHERE a.supersedes IS NOT NULL
  ),
  serialized AS (
    SELECT c.id,
      (
        jsonb_build_object(
          'memory_id',c.id,'user_id',c.user_id,'case_id',c.case_id,
          'scope_kind',CASE WHEN c.case_id IS NULL THEN 'general'
            WHEN left(c.case_id,4)='chk_' THEN 'checkpoint' ELSE 'matter' END,
          'memory_type',c.memory_type,
          'memory_class',CASE
            WHEN c.memory_type IN ('continuity_checkpoint','runtime_observation','continuity_regression_observation') THEN 'RUNTIME_STATE'
            WHEN c.memory_type IN ('operator_directive','operator_runtime_directive','procedural') THEN 'OPERATIONAL_DOCTRINE'
            WHEN c.memory_type IN ('semantic','factual','structured_memory_graph_node','memory_architecture') THEN 'DURABLE_KNOWLEDGE'
            WHEN c.memory_type IN ('episodic','event','case_frontier') THEN 'PROJECT_STATE'
            ELSE 'UNCLASSIFIED' END,
          'topic_pillar_status','not_inferred',
          'source',c.source,'source_id',c.source_id,'source_uri',c.source_uri,
          'source_hash',c.source_hash,'source_type',c.source_type,
          'authority_status',c.authority_status,
          'verification_method',c.verification_method,
          'created_at',c.created_at,'observed_at',c.observed_at,
          'importance_score',c.importance_score,
          'mem0_id',c.mem0_id,'supermemory_id',c.supermemory_id,
          'supersedes',c.supersedes,'has_successor',(s.id IS NOT NULL),
          'court_facing',c.court_facing
        )
        || CASE WHEN v_content THEN jsonb_build_object('content',c.content)
             ELSE '{}'::jsonb END
        || CASE WHEN v_metadata THEN jsonb_build_object('metadata',c.metadata)
             ELSE '{}'::jsonb END
      ) AS item
    FROM candidates c LEFT JOIN successors s ON s.id=c.id
  ),
  measured AS (
    SELECT id,item,octet_length(item::text)+1 AS item_bytes,
      sum(octet_length(item::text)+1) OVER (ORDER BY id) AS total_bytes,
      row_number() OVER (ORDER BY id) AS sequence_no
    FROM serialized
  ),
  page_rows AS MATERIALIZED (
    SELECT id,item,item_bytes FROM measured
    WHERE total_bytes<=v_max_bytes AND sequence_no<=v_max_records
  ),
  page AS (
    SELECT count(*) AS item_count,(SELECT id FROM page_rows ORDER BY id DESC LIMIT 1) AS after_id,
      coalesce(sum(item_bytes),0) AS item_bytes,
      coalesce(jsonb_agg(item ORDER BY id),'[]'::jsonb) AS items FROM page_rows
  ),
  groups AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'memory_class',memory_class,'memory_type',memory_type,'record_count',n)
      ORDER BY memory_class,memory_type),'[]'::jsonb) AS summary
    FROM (
      SELECT item->>'memory_class' AS memory_class,
        item->>'memory_type' AS memory_type,count(*) AS n
      FROM page_rows GROUP BY 1,2
    ) g
  )
  SELECT jsonb_build_object(
    'schema','apex.memory_organized_batch.v1',
    'source','public.apex_memories',
    'scope',v_scope,'case_id',v_case,
    'content_included',v_content,'metadata_included',v_metadata,
    'max_records',v_max_records,'max_bytes',v_max_bytes,
    'item_count',p.item_count,'item_bytes',p.item_bytes,
    'after_id',p.after_id,
    'has_more',(SELECT count(*) FROM candidates)>p.item_count,
    'groups',g.summary,
    'page_sha256',encode(extensions.digest(p.items::text,'sha256'),'hex'),
    'items',p.items
  ) INTO v_result
  FROM page p CROSS JOIN groups g;
  RETURN v_result;
END;
$function$;

REVOKE ALL ON FUNCTION public.memory_organized_batch_v1(
  text,text,uuid,integer,integer,boolean,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.memory_organized_batch_v1(
  text,text,uuid,integer,integer,boolean,boolean) TO service_role;
COMMENT ON FUNCTION public.memory_organized_batch_v1(
  text,text,uuid,integer,integer,boolean,boolean)
IS 'Read-only high-volume cursor over canonical APEX memories; no new packet/data copy; per-call byte budget, exact case/checkpoint scope and source provenance.';
