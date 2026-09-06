create table if not exists public.continuity_matter_aliases_v1(
  alias_id uuid primary key default gen_random_uuid(),
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  alias_key text not null,
  alias_type text not null check(alias_type in (
    'case_id','forensic_id','stable_alias','external_id','human_label','legacy_key','other'
  )),
  source_system text,
  priority integer not null default 90 check(priority between 0 and 100),
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists continuity_matter_aliases_unique_idx
  on public.continuity_matter_aliases_v1(
    lower(alias_key),coalesce(lower(source_system),'')
  );

create index if not exists continuity_matter_aliases_matter_idx
  on public.continuity_matter_aliases_v1(matter_id,enabled,priority desc);

alter table public.continuity_matter_aliases_v1 enable row level security;
revoke all on table public.continuity_matter_aliases_v1 from public,anon,authenticated;
grant select,insert,update,delete on table public.continuity_matter_aliases_v1 to service_role;

create or replace function public.continuity_canonical_matter_v1(
  p_key text,
  p_source_system text default null
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_matter public.continuity_matters_v1%rowtype;
begin
  if coalesce(trim(p_key),'')='' then
    return jsonb_build_object('resolved',false,'reason','empty_key');
  end if;

  select * into v_matter
  from public.continuity_matters_v1
  where lower(matter_key)=lower(trim(p_key))
    and status<>'archived'
  order by priority desc,updated_at desc
  limit 1;

  if found then
    return jsonb_build_object(
      'resolved',true,
      'resolution','matter_key',
      'matter_id',v_matter.matter_id,
      'matter_key',v_matter.matter_key,
      'title',v_matter.title,
      'status',v_matter.status
    );
  end if;

  select m.* into v_matter
  from public.continuity_matter_aliases_v1 a
  join public.continuity_matters_v1 m on m.matter_id=a.matter_id
  where a.enabled=true
    and m.status<>'archived'
    and lower(a.alias_key)=lower(trim(p_key))
    and (
      a.source_system is null
      or p_source_system is null
      or lower(a.source_system)=lower(p_source_system)
    )
  order by
    case
      when p_source_system is not null and a.source_system is not null
           and lower(a.source_system)=lower(p_source_system) then 0
      when a.source_system is null then 1
      else 2
    end,
    a.priority desc,
    m.priority desc,
    a.updated_at desc
  limit 1;

  if found then
    return jsonb_build_object(
      'resolved',true,
      'resolution','alias',
      'matter_id',v_matter.matter_id,
      'matter_key',v_matter.matter_key,
      'title',v_matter.title,
      'status',v_matter.status
    );
  end if;

  return jsonb_build_object('resolved',false,'reason','no_match','input',p_key);
end;
$$;

revoke all on function public.continuity_canonical_matter_v1(text,text)
  from public,anon,authenticated;
grant execute on function public.continuity_canonical_matter_v1(text,text)
  to service_role;

create or replace function public.continuity_route_matches_v1(
  p_match_type text,
  p_match_value text,
  p_subject text,
  p_body text,
  p_addresses text[],
  p_phones text[],
  p_external_ids text[]
)
returns boolean
language plpgsql
immutable
set search_path='pg_catalog','pg_temp'
as $$
declare
  v_value text:=coalesce(trim(p_match_value),'');
  v_subject text:=coalesce(p_subject,'');
  v_body text:=coalesce(p_body,'');
  v_text text;
  v_phone_value text;
begin
  if v_value='' then return false; end if;

  v_text:=lower(
    v_subject||E'\n'||v_body||E'\n'
    ||array_to_string(coalesce(p_addresses,'{}'::text[]),E'\n')
    ||E'\n'||array_to_string(coalesce(p_external_ids,'{}'::text[]),E'\n')
  );

  if p_match_type='email' then
    return exists(
      select 1 from unnest(coalesce(p_addresses,'{}'::text[])) x
      where lower(trim(x))=lower(v_value)
    );
  elsif p_match_type='phone' then
    v_phone_value:=regexp_replace(v_value,'[^0-9+]','','g');
    return exists(
      select 1 from unnest(coalesce(p_phones,'{}'::text[])) x
      where regexp_replace(trim(x),'[^0-9+]','','g')=v_phone_value
    );
  elsif p_match_type='external_id' then
    return exists(
      select 1 from unnest(coalesce(p_external_ids,'{}'::text[])) x
      where lower(trim(x))=lower(v_value)
    );
  elsif p_match_type='exact' then
    return lower(trim(v_subject))=lower(v_value)
      or lower(trim(v_body))=lower(v_value)
      or exists(
        select 1 from unnest(coalesce(p_external_ids,'{}'::text[])) x
        where lower(trim(x))=lower(v_value)
      );
  elsif p_match_type='contains' then
    return position(lower(v_value) in v_text)>0;
  elsif p_match_type='regex' then
    begin
      return v_text ~* v_value;
    exception when invalid_regular_expression then
      return false;
    end;
  end if;

  return false;
end;
$$;

revoke all on function public.continuity_route_matches_v1(
  text,text,text,text,text[],text[],text[]
) from public,anon,authenticated;
grant execute on function public.continuity_route_matches_v1(
  text,text,text,text,text[],text[],text[]
) to service_role;

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
      greatest(m.priority,r.weight) as score_component,
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
      least(100,max(weight) + least(20,greatest(0,(count(*)-1)::integer)*5))::integer as score,
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
    max(matter_id) filter(where rn=1),
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

create or replace view public.continuity_matter_identity_v1 as
select
  m.matter_id,
  m.matter_key,
  m.title,
  m.status,
  m.priority,
  coalesce(
    jsonb_agg(
      jsonb_build_object(
        'alias_key',a.alias_key,
        'alias_type',a.alias_type,
        'source_system',a.source_system,
        'priority',a.priority
      )
      order by a.priority desc,a.alias_key
    ) filter(where a.alias_id is not null and a.enabled),
    '[]'::jsonb
  ) as aliases
from public.continuity_matters_v1 m
left join public.continuity_matter_aliases_v1 a on a.matter_id=m.matter_id
group by m.matter_id,m.matter_key,m.title,m.status,m.priority;

revoke all on public.continuity_matter_identity_v1 from public,anon,authenticated;
grant select on public.continuity_matter_identity_v1 to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'matter_identity_resolution',true,
  jsonb_build_object(
    'version',1,
    'canonical_lookup','continuity_canonical_matter_v1',
    'resolver','continuity_resolve_matter_v1',
    'auto_bind_min_score',80,
    'auto_bind_min_margin',20,
    'ambiguity_policy','fail_closed',
    'archived_matters_auto_bind',false,
    'rule','Strong identifiers may bind automatically; ambiguous or weak signals remain unresolved.'
  )
)
on conflict(control_key) do update set
  enabled=true,
  state=public.continuity_control_state_v1.state||excluded.state,
  updated_at=now();

