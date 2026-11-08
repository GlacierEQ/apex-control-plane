-- Targeted high-authority relevance protection for live APEX native memory.
-- Red: unrelated 'NEX theft citation SKU confiscated' returned the general
-- Logical Progress Foundation user_assertion as rank 1 (fuzzy=0.194).
-- Green acceptance: direct Foundation recall remains, unrelated exact-case
-- semantics still enforced, unrelated high-authority pointer excluded.
-- Do not edit source memory, user assertion status, legal proof, or compiler.
-- Query lexemes are regex-escaped alphanumeric terms; no dynamic raw SQL.
-- Exact substring check protects short or quoted queries without ILIKE
-- wildcard interpretation; blank input now returns no candidates.
-- Service-role-only access retained.

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
  WITH query_terms AS (
    SELECT DISTINCT lower(t.matches[1]) AS token
    FROM regexp_matches(coalesce(p_query,''),'([[:alnum:]]{3,})','g') AS t(matches)
  ),
  lexical_query AS (
    SELECT CASE WHEN count(*) > 0
      THEN to_tsquery('english',string_agg(token,' | ' ORDER BY token))
      ELSE NULL::tsquery END AS tsq
    FROM query_terms
  ),
  scored AS (
    SELECT
      a.id AS memory_id,
      GREATEST(
        extensions.similarity(COALESCE(a.content,''),COALESCE(p_query,'')),
        extensions.word_similarity(COALESCE(p_query,''),COALESCE(a.content,''))
      )::real AS recall_score,
      (q.tsq IS NOT NULL AND to_tsvector('english',coalesce(a.content,'')) @@ q.tsq)
        AS lexical_match,
      position(lower(btrim(coalesce(p_query,''))) in lower(a.content)) > 0
        AS exact_match,
      CASE LOWER(COALESCE(a.authority_status,'unresolved'))
        WHEN 'verified_record' THEN 1
        WHEN 'verified' THEN 1
        WHEN 'source_verified' THEN 1
        WHEN 'provider_native' THEN 1
        WHEN 'external_verified' THEN 2
        WHEN 'user_assertion' THEN 2
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
    FROM public.apex_memories a CROSS JOIN lexical_query q
    WHERE a.content IS NOT NULL
      AND BTRIM(a.content) <> ''
      AND a.case_id IS NOT DISTINCT FROM NULLIF(BTRIM(p_case_id),'')
      AND NOT EXISTS (
        SELECT 1 FROM public.apex_memories newer WHERE newer.supersedes=a.id
      )
  )
  SELECT s.memory_id,s.recall_score
  FROM scored s
  WHERE btrim(coalesce(p_query,'')) <> ''
    AND (s.recall_score > 0.01 OR s.exact_match)
    AND (
      s.authority_rank >= 5
      OR s.lexical_match
      OR s.recall_score >= 0.32
      OR s.exact_match
    )
  ORDER BY s.authority_rank ASC,s.recall_score DESC,s.importance_score DESC,s.created_at DESC
  LIMIT GREATEST(1,LEAST(COALESCE(p_limit,24),100));
$function$;
REVOKE ALL ON FUNCTION public.memory_authoritative_candidates_v1(text,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.memory_authoritative_candidates_v1(text,text,integer) TO service_role;
