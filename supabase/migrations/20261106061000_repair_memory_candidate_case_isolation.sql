-- GlacierEQ production native SQL scope repair, 2026-11-06 UTC.
-- Existing memory-context-compiler-v2 calls this function; no new controller.
-- NULL p_case_id now means general memory only (case_id IS NULL).
-- Specific p_case_id remains exact-case only; no cross-case expansion.
-- Existing authority ranking, supersession and score ordering are preserved.
--
-- RED provider readback before repair:
-- search('NEX theft citation SKU confiscated', NULL, 24): 24 returned,
-- 11 illegally case-scoped across three case IDs, 13 general.
-- GREEN provider readback after repair:
-- same query NULL: 24 returned, 0 case-scoped, 24 general;
-- exact case NEX-JBPHH-2026-08-14: 10 returned, 0 other cases.
-- The endpoint's organization-level HTTP 402 remains a separate billing restriction.

CREATE OR REPLACE FUNCTION public.memory_authoritative_candidates_v1(
  p_query text,
  p_case_id text DEFAULT NULL,
  p_limit integer DEFAULT 24
)
RETURNS TABLE(memory_id uuid, recall_score real)
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path TO 'public','extensions','pg_temp'
AS $function$
  WITH scored AS (
    SELECT
      a.id AS memory_id,
      GREATEST(
        extensions.similarity(COALESCE(a.content,''),COALESCE(p_query,'')),
        extensions.word_similarity(COALESCE(p_query,''),COALESCE(a.content,''))
      )::real AS recall_score,
      CASE LOWER(COALESCE(a.authority_status,'unresolved'))
        WHEN 'verified' THEN 1
        WHEN 'source_verified' THEN 1
        WHEN 'provider_native' THEN 1
        WHEN 'external_verified' THEN 2
        WHEN 'operator_directive' THEN 2
        WHEN 'operator_observation' THEN 3
        WHEN 'firsthand' THEN 3
        WHEN 'unresolved' THEN 5
        WHEN 'derived' THEN 6
        WHEN 'inference' THEN 7
        ELSE 8
      END AS authority_rank,
      COALESCE(a.importance_score,0.5) AS importance_score,
      a.created_at
    FROM public.apex_memories a
    WHERE a.content IS NOT NULL
      AND BTRIM(a.content) <> ''
      AND a.case_id IS NOT DISTINCT FROM NULLIF(BTRIM(p_case_id),'')
      AND NOT EXISTS (
        SELECT 1 FROM public.apex_memories newer WHERE newer.supersedes=a.id
      )
  )
  SELECT s.memory_id,s.recall_score
  FROM scored s
  WHERE s.recall_score > 0.01
     OR EXISTS (
       SELECT 1 FROM public.apex_memories a
       WHERE a.id=s.memory_id
         AND a.content ILIKE '%' || REPLACE(COALESCE(p_query,''),'%','\%') || '%' ESCAPE '\'
     )
  ORDER BY s.authority_rank ASC,s.recall_score DESC,s.importance_score DESC,s.created_at DESC
  LIMIT GREATEST(1,LEAST(COALESCE(p_limit,24),100));
$function$;
