create or replace function public.continuity_resolve_matter_v1(
  p_source_system text,
  p_subject text default null,
  p_body text default null,
  p_addresses text[] default '{}'::text[],
  p_phones text[] default '{}'::text[],
  p_external_ids text[] default '{}'::text[]
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_candidates jsonb:='[]'::jsonb;
  v_top_score integer:=null;
  v_second_score integer:=null;
  v_top_matter_id uuid:=null;
  v_top_matter_key text:=null;
  v_top_title text:=null;
  v_auto_bind boolean:=false;
begin
  with matched as (
    select
      m.matter_id,
      m.matter_key,
      m.title,
      r.weight,
      r.match_type,
      r.match_value,
      r.route_id
    from public.continuity_matter_routes_v1 r
    join public.continuity_matters_v1 m on m.matter_id=r.matter_id
    where r.enabled=true
      and m.status<>'archived'
      and (r.source_system is null or p_source_system is null
           or lower(r.source_system)=lower(p_source_system))
      and public.continuity_route_matches_v1(
        r.match_type,r.match_value,p_subject,p_body,
        coalesce(p_addresses,'{}'::text[]),
        coalesce(p_phones,'{}'::text[]),
        coalesce(p_external_ids,'{}'::text[])
      )
  ),
  ranked as (
    select
      matter_id,
      matter_key,
      title,
      least(
        100,
        max(weight) + least(20,greatest(0,(count(*)-1)::integer)*5)
      )::integer as score,
      jsonb_agg(
        jsonb_build_object(
          'route_id',route_id,
          'match_type',match_type,
          'match_value',match_value,
          'weight',weight
        )
        order by weight desc,match_type,match_value
      ) as matches
    from matched
    group by matter_id,matter_key,title
  ),
  ordered as (
    select *,row_number() over(order by score desc,matter_key) rn
    from ranked
  )
  select
    coalesce(jsonb_agg(
      jsonb_build_object(
        'matter_id',matter_id,
        'matter_key',matter_key,
        'title',title,
        'score',score,
        'matches',matches
      ) order by score desc,matter_key
    ),'[]'::jsonb),
    max(score) filter(where rn=1),
    max(score) filter(where rn=2),
    (max(matter_id::text) filter(where rn=1))::uuid,
    max(matter_key) filter(where rn=1),
    max(title) filter(where rn=1)
  into
    v_candidates,v_top_score,v_second_score,v_top_matter_id,v_top_matter_key,v_top_title
  from ordered;

  v_auto_bind :=
    v_top_score is not null
    and v_top_score>=80
    and (v_second_score is null or v_top_score-v_second_score>=20);

  return jsonb_build_object(
    'auto_bind',v_auto_bind,
    'reason',case
      when v_top_score is null then 'no_match'
      when v_top_score<80 then 'insufficient_confidence'
      when v_second_score is not null and v_top_score-v_second_score<20 then 'ambiguous'
      else 'high_confidence'
    end,
    'source_system',p_source_system,
    'matter_id',case when v_auto_bind then v_top_matter_id else null end,
    'matter_key',case when v_auto_bind then v_top_matter_key else null end,
    'title',case when v_auto_bind then v_top_title else null end,
    'top_score',v_top_score,
    'second_score',v_second_score,
    'candidates',v_candidates
  );
end;
$$;

revoke all on function public.continuity_resolve_matter_v1(
  text,text,text,text[],text[],text[]
) from public,anon,authenticated;
grant execute on function public.continuity_resolve_matter_v1(
  text,text,text,text[],text[],text[]
) to service_role;

