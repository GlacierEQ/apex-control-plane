-- Harden federated execution permits against stale authorization, expired/changed
-- context packets, expired-permit reuse, and concurrent double consumption.

create index if not exists continuity_federated_permits_identity_idx
  on public.continuity_federated_execution_permits_v1(
    action_id, packet_snapshot_hash, global_frontier_hash,
    primary_awareness_receipt_ref, issued_at desc
  );

create or replace function public.continuity_issue_federated_execution_permit_v1(
  p_action_id uuid,
  p_expected_global_frontier_hash text,
  p_primary_awareness_receipt_ref text,
  p_primary_awareness_source_watermark_at timestamptz,
  p_issuer text,
  p_ttl_seconds integer default 300,
  p_detail jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  a public.continuity_outbound_actions_v1%rowtype;
  p public.continuity_peer_frontiers_v1%rowtype;
  cp public.continuity_context_packets_v1%rowtype;
  v_permit public.continuity_federated_execution_permits_v1%rowtype;
  v_ttl integer:=greatest(30,least(coalesce(p_ttl_seconds,300),600));
  v_plan_gate jsonb;
  v_checkpointed_awareness_ref text;
  v_checkpointed_awareness_watermark timestamptz;
begin
  if p_expected_global_frontier_hash is null or p_expected_global_frontier_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_global_frontier_hash';
  end if;
  if coalesce(trim(p_primary_awareness_receipt_ref),'')='' then raise exception 'primary_awareness_receipt_required'; end if;
  if p_primary_awareness_source_watermark_at is null then raise exception 'primary_awareness_watermark_required'; end if;
  if coalesce(trim(p_issuer),'')='' then raise exception 'issuer_required'; end if;

  select * into a
  from public.continuity_outbound_actions_v1
  where action_id=p_action_id
  for update;
  if not found then raise exception 'unknown_action'; end if;
  if a.status<>'executing' then raise exception 'action_not_in_executing_state'; end if;
  if a.plan_action_id is null then raise exception 'plan_action_binding_required'; end if;
  if coalesce((a.execution_guard->>'execution_ready')::boolean,false) is not true then
    raise exception 'backend_execution_guard_not_ready';
  end if;

  v_plan_gate:=public.continuity_case_plan_gate_v1(a.action_id);
  if coalesce((v_plan_gate->>'authorized')::boolean,false) is not true then
    raise exception 'active_plan_gate_not_authorized';
  end if;

  select * into cp
  from public.continuity_context_packets_v1
  where packet_id=a.packet_id
  for share;
  if not found then raise exception 'context_packet_missing'; end if;
  if cp.expires_at<=now() then raise exception 'context_packet_expired'; end if;

  select * into p
  from public.continuity_peer_frontiers_v1
  where peer_key='supabase-glaciereq.global-frontier';
  if not found then raise exception 'global_frontier_peer_missing'; end if;
  if p.sync_status<>'healthy' then raise exception 'global_frontier_peer_not_healthy'; end if;
  if p.last_snapshot_hash is distinct from p_expected_global_frontier_hash then
    raise exception 'global_frontier_hash_mismatch';
  end if;
  if p.last_watermark_at is null or p.last_watermark_at < now()-interval '15 minutes' then
    raise exception 'global_frontier_checkpoint_stale';
  end if;
  if p_primary_awareness_source_watermark_at < p.last_watermark_at then
    raise exception 'primary_awareness_older_than_global_frontier_checkpoint';
  end if;

  v_checkpointed_awareness_ref:=nullif(trim(coalesce(p.metadata->>'primary_awareness_receipt_ref','')),'');
  begin
    v_checkpointed_awareness_watermark:=nullif(trim(coalesce(p.metadata->>'primary_awareness_source_watermark_at','')),'')::timestamptz;
  exception when others then
    raise exception 'primary_awareness_checkpoint_invalid';
  end;
  if v_checkpointed_awareness_ref is null or v_checkpointed_awareness_watermark is null then raise exception 'primary_awareness_receipt_not_checkpointed'; end if;
  if v_checkpointed_awareness_ref is distinct from trim(p_primary_awareness_receipt_ref) then raise exception 'primary_awareness_receipt_mismatch'; end if;
  if v_checkpointed_awareness_watermark is distinct from p_primary_awareness_source_watermark_at then raise exception 'primary_awareness_watermark_mismatch'; end if;

  select pmt.* into v_permit
  from public.continuity_federated_execution_permits_v1 pmt
  where pmt.action_id=a.action_id
    and pmt.packet_snapshot_hash=cp.snapshot_hash
    and pmt.global_frontier_hash=p.last_snapshot_hash
    and pmt.primary_awareness_receipt_ref=trim(p_primary_awareness_receipt_ref)
    and pmt.expires_at>now()
    and not exists (
      select 1 from public.continuity_federated_execution_permit_receipts_v1 r
      where r.permit_id=pmt.permit_id and r.receipt_type in ('CONSUMED','REVOKED')
    )
  order by pmt.issued_at desc
  limit 1;

  if not found then
    insert into public.continuity_federated_execution_permits_v1(
      action_id,plan_action_id,packet_id,packet_snapshot_hash,
      global_frontier_hash,global_frontier_watermark_at,
      primary_awareness_receipt_ref,primary_awareness_source_watermark_at,
      expires_at,issuer,detail
    ) values (
      a.action_id,a.plan_action_id,a.packet_id,cp.snapshot_hash,
      p.last_snapshot_hash,p.last_watermark_at,
      trim(p_primary_awareness_receipt_ref),p_primary_awareness_source_watermark_at,
      least(cp.expires_at,now()+make_interval(secs=>v_ttl)),trim(p_issuer),coalesce(p_detail,'{}'::jsonb)
    ) returning * into v_permit;

    insert into public.continuity_federated_execution_permit_receipts_v1(
      permit_id,action_id,receipt_type,outcome,detail
    ) values (
      v_permit.permit_id,a.action_id,'ISSUED','READY_FOR_PROVIDER_DISPATCH',
      jsonb_build_object(
        'packet_snapshot_hash',v_permit.packet_snapshot_hash,
        'global_frontier_hash',v_permit.global_frontier_hash,
        'global_frontier_watermark_at',v_permit.global_frontier_watermark_at,
        'primary_awareness_receipt_ref',v_permit.primary_awareness_receipt_ref,
        'primary_awareness_source_watermark_at',v_permit.primary_awareness_source_watermark_at,
        'expires_at',v_permit.expires_at,
        'issuer',v_permit.issuer
      )
    );
  end if;

  return jsonb_build_object(
    'permit_id',v_permit.permit_id,
    'action_id',v_permit.action_id,
    'ready',true,
    'expires_at',v_permit.expires_at,
    'packet_snapshot_hash',v_permit.packet_snapshot_hash,
    'global_frontier_hash',v_permit.global_frontier_hash,
    'primary_awareness_receipt_ref',v_permit.primary_awareness_receipt_ref
  );
end;
$$;

create or replace function public.continuity_validate_federated_execution_permit_v1(
  p_permit_id uuid,
  p_action_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  pmt public.continuity_federated_execution_permits_v1%rowtype;
  a public.continuity_outbound_actions_v1%rowtype;
  peer public.continuity_peer_frontiers_v1%rowtype;
  cp public.continuity_context_packets_v1%rowtype;
  v_plan_gate jsonb;
  consumed boolean:=false;
  revoked boolean:=false;
  v_checkpointed_awareness_ref text;
  v_checkpointed_awareness_watermark timestamptz;
begin
  select * into pmt
  from public.continuity_federated_execution_permits_v1
  where permit_id=p_permit_id
  for update;
  if not found then return jsonb_build_object('ready',false,'reason','permit_missing'); end if;
  if pmt.action_id<>p_action_id then return jsonb_build_object('ready',false,'reason','permit_action_mismatch'); end if;

  select exists(select 1 from public.continuity_federated_execution_permit_receipts_v1 r where r.permit_id=p_permit_id and r.receipt_type='CONSUMED') into consumed;
  select exists(select 1 from public.continuity_federated_execution_permit_receipts_v1 r where r.permit_id=p_permit_id and r.receipt_type='REVOKED') into revoked;
  if consumed then return jsonb_build_object('ready',false,'reason','permit_consumed'); end if;
  if revoked then return jsonb_build_object('ready',false,'reason','permit_revoked'); end if;
  if pmt.expires_at<=now() then
    insert into public.continuity_federated_execution_permit_receipts_v1(permit_id,action_id,receipt_type,outcome,detail)
    values(pmt.permit_id,pmt.action_id,'EXPIRED_REJECTED','BLOCKED',jsonb_build_object('expired_at',pmt.expires_at,'checked_at',now()))
    on conflict(permit_id,receipt_type) do nothing;
    return jsonb_build_object('ready',false,'reason','permit_expired','expired_at',pmt.expires_at);
  end if;

  select * into a
  from public.continuity_outbound_actions_v1
  where action_id=p_action_id;
  if not found or a.status<>'executing' then return jsonb_build_object('ready',false,'reason','action_not_executing'); end if;
  if a.plan_action_id is distinct from pmt.plan_action_id then return jsonb_build_object('ready',false,'reason','plan_action_changed'); end if;
  if a.packet_id is distinct from pmt.packet_id then return jsonb_build_object('ready',false,'reason','packet_changed'); end if;
  if coalesce((a.execution_guard->>'execution_ready')::boolean,false) is not true then return jsonb_build_object('ready',false,'reason','backend_execution_guard_not_ready'); end if;

  v_plan_gate:=public.continuity_case_plan_gate_v1(a.action_id);
  if coalesce((v_plan_gate->>'authorized')::boolean,false) is not true then
    return jsonb_build_object('ready',false,'reason','active_plan_gate_not_authorized','plan_gate',v_plan_gate);
  end if;

  select * into cp
  from public.continuity_context_packets_v1
  where packet_id=pmt.packet_id
  for share;
  if not found then return jsonb_build_object('ready',false,'reason','context_packet_missing'); end if;
  if cp.expires_at<=now() then return jsonb_build_object('ready',false,'reason','context_packet_expired'); end if;
  if cp.snapshot_hash is distinct from pmt.packet_snapshot_hash then return jsonb_build_object('ready',false,'reason','context_packet_snapshot_changed'); end if;

  select * into peer from public.continuity_peer_frontiers_v1 where peer_key='supabase-glaciereq.global-frontier';
  if not found or peer.sync_status<>'healthy' then return jsonb_build_object('ready',false,'reason','global_frontier_peer_not_healthy'); end if;
  if peer.last_snapshot_hash is distinct from pmt.global_frontier_hash then return jsonb_build_object('ready',false,'reason','global_frontier_advanced_or_changed'); end if;
  if peer.last_watermark_at is null or peer.last_watermark_at < now()-interval '15 minutes' then return jsonb_build_object('ready',false,'reason','global_frontier_checkpoint_stale'); end if;
  if pmt.primary_awareness_source_watermark_at < peer.last_watermark_at then return jsonb_build_object('ready',false,'reason','primary_awareness_older_than_global_frontier_checkpoint'); end if;

  v_checkpointed_awareness_ref:=nullif(trim(coalesce(peer.metadata->>'primary_awareness_receipt_ref','')),'');
  begin
    v_checkpointed_awareness_watermark:=nullif(trim(coalesce(peer.metadata->>'primary_awareness_source_watermark_at','')),'')::timestamptz;
  exception when others then
    return jsonb_build_object('ready',false,'reason','primary_awareness_checkpoint_invalid');
  end;
  if v_checkpointed_awareness_ref is null or v_checkpointed_awareness_watermark is null then return jsonb_build_object('ready',false,'reason','primary_awareness_receipt_not_checkpointed'); end if;
  if v_checkpointed_awareness_ref is distinct from pmt.primary_awareness_receipt_ref then return jsonb_build_object('ready',false,'reason','primary_awareness_receipt_mismatch'); end if;
  if v_checkpointed_awareness_watermark is distinct from pmt.primary_awareness_source_watermark_at then return jsonb_build_object('ready',false,'reason','primary_awareness_watermark_mismatch'); end if;

  insert into public.continuity_federated_execution_permit_receipts_v1(permit_id,action_id,receipt_type,outcome,detail)
  values(pmt.permit_id,pmt.action_id,'VALIDATED','READY_FOR_PROVIDER_DISPATCH',jsonb_build_object('validated_at',now()))
  on conflict(permit_id,receipt_type) do nothing;

  return jsonb_build_object('ready',true,'reason','federated_execution_current','permit_id',pmt.permit_id,'expires_at',pmt.expires_at);
end;
$$;

create or replace function public.continuity_consume_federated_execution_permit_v1(
  p_permit_id uuid,
  p_action_id uuid,
  p_provider_ref text default null,
  p_detail jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v jsonb;
  v_locked uuid;
  v_receipt uuid;
begin
  select permit_id into v_locked
  from public.continuity_federated_execution_permits_v1
  where permit_id=p_permit_id
  for update;
  if not found then return jsonb_build_object('ready',false,'reason','permit_missing'); end if;

  v:=public.continuity_validate_federated_execution_permit_v1(p_permit_id,p_action_id);
  if not coalesce((v->>'ready')::boolean,false) then return v; end if;

  insert into public.continuity_federated_execution_permit_receipts_v1(permit_id,action_id,receipt_type,outcome,detail)
  values(p_permit_id,p_action_id,'CONSUMED','PROVIDER_DISPATCH_STARTED',coalesce(p_detail,'{}'::jsonb)||jsonb_build_object('provider_ref',p_provider_ref,'consumed_at',now()))
  on conflict(permit_id,receipt_type) do nothing
  returning receipt_id into v_receipt;

  if v_receipt is null then
    return jsonb_build_object('ready',false,'reason','permit_consumed','permit_id',p_permit_id,'action_id',p_action_id);
  end if;

  return jsonb_build_object('ready',true,'consumed',true,'permit_id',p_permit_id,'action_id',p_action_id,'provider_ref',p_provider_ref,'consumption_receipt_id',v_receipt);
end;
$$;
