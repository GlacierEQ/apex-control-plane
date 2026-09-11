-- Security hardening for relevance-aware awareness helper functions.
-- Supabase advisor requires explicit search_path on callable functions.

create or replace function public.control_plane_normalize_awareness_text_v2(p_text text)
returns text
language sql
immutable
parallel safe
set search_path='pg_catalog','public'
as $$
  select btrim(regexp_replace(lower(coalesce(p_text,'')), '[^a-z0-9]+', ' ', 'g'));
$$;

create or replace function public.control_plane_action_target_matches_v2(
  p_target_system text,
  p_target_ref text,
  p_text text
)
returns boolean
language sql
immutable
parallel safe
set search_path='pg_catalog','public'
as $$
  with n as (
    select public.control_plane_normalize_awareness_text_v2(p_target_system) as target_system,
           public.control_plane_normalize_awareness_text_v2(p_target_ref) as target_ref,
           public.control_plane_normalize_awareness_text_v2(p_text) as haystack
  )
  select (length(target_system)>=3 and strpos(haystack,target_system)>0)
      or (length(target_ref)>=4 and strpos(haystack,target_ref)>0)
  from n;
$$;
