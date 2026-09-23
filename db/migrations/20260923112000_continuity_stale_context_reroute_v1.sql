-- Continuity stale-context reroute v1
-- DERIVED_FROM transport/context-enrichment-everywhere-20260921 and PR #275.
-- Stale context creates recovery debt and enrichment work; it does not acquire
-- authority to stop an otherwise authorized mission. Independent safety gates
-- (expiry, channel mismatch, duplicate action, delivery failure, plan/permit
-- authority) remain fail-closed.

create or replace function public.continuity_preflight_outbound_v2(
  p_packet_id uuid,
  p_channel text,
  p_target text
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_packet public.continuity_context_packets_v1%rowtype;
  v_matter_updated timestamptz;
  v_latest_fact timestamptz;
  v_latest_event timestamptz;
  v_latest_commitment timestamptz;
  v_recent_duplicate integer:=0;
  v_unresolved_failures integer:=0;
  v_overdue integer:=0;
  v_target_bounced integer:=0;
  v_stale boolean:=false;
  v_block_reason text:=null;
begin
  select * into v_packet
  from public.continuity_context_packets_v1
  where packet_id=p_packet_id;

  if not found then raise exception 'unknown_context_packet'; end if;

  if v_packet.expires_at<now() then
    return jsonb_build_object('ready',false,'reason','context_packet_expired','packet_id',p_packet_id);
  end if;

  if p_channel<>v_packet.action_channel then
    return jsonb_build_object('ready',false,'reason','channel_mismatch','packet_channel',v_packet.action_channel,'requested_channel',p_channel);
  end if;

  select updated_at into v_matter_updated
  from public.continuity_matters_v1 where matter_id=v_packet.matter_id;

  select max(created_at) into v_latest_fact
  from public.continuity_facts_v1
  where matter_id=v_packet.matter_id and superseded_by is null;

  select max(created_at) into v_latest_event
  from public.continuity_events_v1
  where matter_id=v_packet.matter_id;

  select max(updated_at) into v_latest_commitment
  from public.continuity_commitments_v1
  where matter_id=v_packet.matter_id;

  v_stale :=
    greatest(
      coalesce(v_matter_updated,'epoch'::timestamptz),
      coalesce(v_latest_fact,'epoch'::timestamptz),
      coalesce(v_latest_event,'epoch'::timestamptz),
      coalesce(v_latest_commitment,'epoch'::timestamptz)
    ) > v_packet.snapshot_at;

  select count(*) into v_recent_duplicate
  from public.continuity_outbound_actions_v1
  where matter_id=v_packet.matter_id
    and channel=p_channel
    and lower(target)=lower(p_target)
    and created_at>now()-interval '60 minutes'
    and status in ('planned','approved','executing','sent','completed');

  select count(*) into v_unresolved_failures
  from public.continuity_events_v1
  where matter_id=v_packet.matter_id
    and event_type='email_delivery_failure'
    and occurred_at>now()-interval '30 days';

  select count(*) into v_overdue
  from public.continuity_commitments_v1
  where matter_id=v_packet.matter_id
    and status in ('open','in_progress','waiting')
    and due_at is not null and due_at<now();

  if p_channel='email' then
    select count(*) into v_target_bounced
    from public.continuity_events_v1
    where matter_id=v_packet.matter_id
      and event_type='email_delivery_failure'
      and lower(coalesce(metadata->>'failed_recipient',''))=lower(p_target)
      and occurred_at>now()-interval '30 days';
  end if;

  if v_recent_duplicate>0 then v_block_reason:='recent_duplicate_action';
  elsif v_target_bounced>0 and lower(v_packet.action_purpose) not like '%repair%' then
    v_block_reason:='target_has_unrepaired_delivery_failure';
  end if;

  return jsonb_build_object(
    'ready',v_block_reason is null,
    'reason',coalesce(v_block_reason,case when v_stale then 'context_stale_recovery_debt' else 'ready' end),
    'packet_id',p_packet_id,
    'snapshot_hash',v_packet.snapshot_hash,
    'target',p_target,
    'context_enrichment',jsonb_build_object(
      'state',case when v_stale then 'recovery_pending' else 'hydrated' end,
      'mission_stop',false,
      'route_effect',case when v_stale then 'enrich_and_continue' else 'continue' end
    ),
    'warnings',jsonb_build_object(
      'context_stale',v_stale,
      'recent_duplicate_actions',v_recent_duplicate,
      'unresolved_delivery_failures',v_unresolved_failures,
      'target_bounced_recently',v_target_bounced,
      'overdue_commitments',v_overdue
    )
  );
end;
$$;

revoke all on function public.continuity_preflight_outbound_v2(uuid,text,text)
  from public,anon,authenticated;
grant execute on function public.continuity_preflight_outbound_v2(uuid,text,text)
  to service_role;

create or replace function public.continuity_preflight_outbound_v3(
  p_packet_id uuid,
  p_channel text,
  p_target text,
  p_exclude_action_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path='pg_catalog','public'
as $$
declare
  v_packet public.continuity_context_packets_v1%rowtype;
  v_matter_updated timestamptz;
  v_latest_fact timestamptz;
  v_latest_event timestamptz;
  v_latest_commitment timestamptz;
  v_recent_duplicate integer:=0;
  v_target_bounced integer:=0;
  v_stale boolean:=false;
  v_block_reason text:=null;
begin
  select * into v_packet
  from public.continuity_context_packets_v1
  where packet_id=p_packet_id;

  if not found then raise exception 'unknown_context_packet'; end if;

  if v_packet.expires_at<now() then
    return jsonb_build_object('ready',false,'reason','context_packet_expired','packet_id',p_packet_id);
  end if;

  if p_channel<>v_packet.action_channel then
    return jsonb_build_object('ready',false,'reason','channel_mismatch');
  end if;

  select updated_at into v_matter_updated
  from public.continuity_matters_v1 where matter_id=v_packet.matter_id;

  select max(created_at) into v_latest_fact
  from public.continuity_facts_v1
  where matter_id=v_packet.matter_id and superseded_by is null;

  select max(created_at) into v_latest_event
  from public.continuity_events_v1
  where matter_id=v_packet.matter_id;

  select max(updated_at) into v_latest_commitment
  from public.continuity_commitments_v1
  where matter_id=v_packet.matter_id;

  v_stale :=
    greatest(
      coalesce(v_matter_updated,'epoch'::timestamptz),
      coalesce(v_latest_fact,'epoch'::timestamptz),
      coalesce(v_latest_event,'epoch'::timestamptz),
      coalesce(v_latest_commitment,'epoch'::timestamptz)
    ) > v_packet.snapshot_at;

  select count(*) into v_recent_duplicate
  from public.continuity_outbound_actions_v1
  where matter_id=v_packet.matter_id
    and channel=p_channel
    and lower(target)=lower(p_target)
    and created_at>now()-interval '60 minutes'
    and status in('planned','approved','executing','sent','completed')
    and (p_exclude_action_id is null or action_id<>p_exclude_action_id);

  if p_channel='email' then
    select count(*) into v_target_bounced
    from public.continuity_events_v1
    where matter_id=v_packet.matter_id
      and event_type='email_delivery_failure'
      and lower(coalesce(metadata->>'failed_recipient',''))=lower(p_target)
      and occurred_at>now()-interval '30 days';
  end if;

  if v_recent_duplicate>0 then v_block_reason:='recent_duplicate_action';
  elsif v_target_bounced>0 and lower(v_packet.action_purpose) not like '%repair%' then
    v_block_reason:='target_has_unrepaired_delivery_failure';
  end if;

  return jsonb_build_object(
    'ready',v_block_reason is null,
    'reason',coalesce(v_block_reason,case when v_stale then 'context_stale_recovery_debt' else 'ready' end),
    'packet_id',p_packet_id,
    'snapshot_hash',v_packet.snapshot_hash,
    'target',p_target,
    'context_enrichment',jsonb_build_object(
      'state',case when v_stale then 'recovery_pending' else 'hydrated' end,
      'mission_stop',false,
      'route_effect',case when v_stale then 'enrich_and_continue' else 'continue' end
    )
  );
end;
$$;

revoke all on function public.continuity_preflight_outbound_v3(uuid,text,text,uuid)
  from public,anon,authenticated;
grant execute on function public.continuity_preflight_outbound_v3(uuid,text,text,uuid)
  to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'continuity_loop',
  true,
  jsonb_build_object(
    'stale_context_policy','recovery_debt_enrich_and_continue',
    'stale_context_mission_stop',false,
    'stale_context_route_effect','reevaluate_enrich_and_continue',
    'preflight_function','continuity_preflight_outbound_v3'
  )
)
on conflict(control_key) do update set
  enabled=true,
  state=public.continuity_control_state_v1.state||excluded.state,
  updated_at=now();
