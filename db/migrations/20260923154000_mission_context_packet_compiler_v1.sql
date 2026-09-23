-- Mission-scoped context packet compiler v1
-- CAP-UPGRADE-20260923 / P0 context compiler.
-- Context is enrichment and routing input, never mission-stop authority.

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.mission_context_packets_v1 (
  packet_id uuid primary key default gen_random_uuid(),
  mission_id text not null,
  idempotency_key text not null unique,
  context_state text not null check (context_state in ('hydrated','degraded')),
  source_state jsonb not null default '{}'::jsonb,
  packet jsonb not null,
  packet_hash text not null,
  compiled_at timestamptz not null default now()
);

create index if not exists mission_context_packets_v1_mission_compiled_idx
  on public.mission_context_packets_v1(mission_id, compiled_at desc);

alter table public.mission_context_packets_v1 enable row level security;
revoke all on public.mission_context_packets_v1 from public, anon, authenticated;
grant select, insert on public.mission_context_packets_v1 to service_role;

create or replace function public.compile_mission_context_packet_v1(
  p_mission_id text,
  p_idempotency_key text,
  p_operator_state jsonb default '{}'::jsonb,
  p_prior_decisions jsonb default '[]'::jsonb,
  p_verified_sources jsonb default '[]'::jsonb,
  p_open_tasks jsonb default '[]'::jsonb,
  p_contradictions jsonb default '[]'::jsonb,
  p_superseded_state jsonb default '[]'::jsonb,
  p_repo_capabilities jsonb default '[]'::jsonb,
  p_connector_health jsonb default '[]'::jsonb,
  p_confidence jsonb default '{}'::jsonb,
  p_resume_point jsonb default '{}'::jsonb,
  p_lane_status jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='pg_catalog','public','extensions'
as $$
declare
  v_degraded_lanes jsonb;
  v_context_state text;
  v_packet jsonb;
  v_hash text;
  v_existing public.mission_context_packets_v1%rowtype;
  v_packet_id uuid;
begin
  if coalesce(btrim(p_mission_id),'')='' then
    raise exception 'mission_id_required';
  end if;
  if coalesce(btrim(p_idempotency_key),'')='' then
    raise exception 'idempotency_key_required';
  end if;

  select coalesce(jsonb_agg(key order by key),'[]'::jsonb)
    into v_degraded_lanes
  from jsonb_each_text(coalesce(p_lane_status,'{}'::jsonb))
  where lower(value) not in (
    'available','hydrated','verified','read_verified',
    'write_verified','readback_verified','production_verified'
  );

  v_context_state :=
    case when jsonb_array_length(v_degraded_lanes)=0 then 'hydrated' else 'degraded' end;

  v_packet := jsonb_build_object(
    'schema','glaciereq.mission-context/1.0',
    'mission',jsonb_build_object('mission_id',p_mission_id),
    'current_operator_state',coalesce(p_operator_state,'{}'::jsonb),
    'relevant_prior_decisions',coalesce(p_prior_decisions,'[]'::jsonb),
    'verified_sources',coalesce(p_verified_sources,'[]'::jsonb),
    'open_tasks',coalesce(p_open_tasks,'[]'::jsonb),
    'contradictions',coalesce(p_contradictions,'[]'::jsonb),
    'superseded_state',coalesce(p_superseded_state,'[]'::jsonb),
    'repo_capabilities',coalesce(p_repo_capabilities,'[]'::jsonb),
    'connector_health',coalesce(p_connector_health,'[]'::jsonb),
    'confidence',coalesce(p_confidence,'{}'::jsonb),
    'resume_point',coalesce(p_resume_point,'{}'::jsonb),
    'source_state',jsonb_build_object(
      'lanes',coalesce(p_lane_status,'{}'::jsonb),
      'degraded_lanes',v_degraded_lanes,
      'context_state',v_context_state,
      'mission_stop',false,
      'routing_effect',case when v_context_state='degraded'
        then 'DEGRADED_LANES_CHANGE_ROUTE_NOT_MISSION'
        else 'CONTINUE'
      end
    )
  );

  v_hash := encode(extensions.digest(convert_to(v_packet::text,'UTF8'),'sha256'),'hex');

  select * into v_existing
  from public.mission_context_packets_v1
  where idempotency_key=p_idempotency_key;

  if found then
    if v_existing.packet_hash<>v_hash then
      raise exception 'mission_context_packet_idempotency_conflict';
    end if;
    return jsonb_build_object(
      'packet_id',v_existing.packet_id,
      'mission_id',v_existing.mission_id,
      'context_state',v_existing.context_state,
      'packet_hash',v_existing.packet_hash,
      'compiled_at',v_existing.compiled_at,
      'idempotent_replay',true,
      'packet',v_existing.packet
    );
  end if;

  insert into public.mission_context_packets_v1(
    mission_id,idempotency_key,context_state,source_state,packet,packet_hash
  )
  values(
    p_mission_id,p_idempotency_key,v_context_state,
    v_packet->'source_state',v_packet,v_hash
  )
  returning packet_id into v_packet_id;

  return jsonb_build_object(
    'packet_id',v_packet_id,
    'mission_id',p_mission_id,
    'context_state',v_context_state,
    'packet_hash',v_hash,
    'idempotent_replay',false,
    'packet',v_packet
  );
end;
$$;

revoke all on function public.compile_mission_context_packet_v1(
  text,text,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb
) from public,anon,authenticated;
grant execute on function public.compile_mission_context_packet_v1(
  text,text,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb
) to service_role;

comment on function public.compile_mission_context_packet_v1(
  text,text,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb
) is 'Mission-scoped context compiler. Degraded or unavailable context lanes are explicit routing debt and never mission-stop authority.';
