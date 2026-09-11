create table if not exists public.continuity_federated_execution_permits_v1(
  permit_id uuid primary key default gen_random_uuid(),
  action_id uuid not null references public.continuity_outbound_actions_v1(action_id) on delete cascade,
  plan_action_id uuid not null references public.continuity_case_execution_plan_actions_v1(plan_action_id) on delete restrict,
  packet_id uuid not null references public.continuity_context_packets_v1(packet_id) on delete restrict,
  packet_snapshot_hash text not null check(packet_snapshot_hash ~ '^[0-9a-f]{64}$'),
  global_frontier_hash text not null check(global_frontier_hash ~ '^[0-9a-f]{64}$'),
  global_frontier_watermark_at timestamptz not null,
  primary_awareness_receipt_ref text not null,
  primary_awareness_source_watermark_at timestamptz not null,
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null,
  issuer text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check(expires_at > issued_at),
  unique(action_id,packet_snapshot_hash,global_frontier_hash,primary_awareness_receipt_ref)
);

create table if not exists public.continuity_federated_execution_permit_receipts_v1(
  receipt_id uuid primary key default gen_random_uuid(),
  permit_id uuid not null references public.continuity_federated_execution_permits_v1(permit_id) on delete cascade,
  action_id uuid not null references public.continuity_outbound_actions_v1(action_id) on delete cascade,
  receipt_type text not null check(receipt_type in ('ISSUED','VALIDATED','CONSUMED','REVOKED','EXPIRED_REJECTED','VALIDATION_REJECTED')),
  outcome text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(permit_id,receipt_type)
);

create index if not exists continuity_federated_permits_action_idx
  on public.continuity_federated_execution_permits_v1(action_id,expires_at desc);
create index if not exists continuity_federated_permit_receipts_action_idx
  on public.continuity_federated_execution_permit_receipts_v1(action_id,created_at desc);

alter table public.continuity_federated_execution_permits_v1 enable row level security;
alter table public.continuity_federated_execution_permit_receipts_v1 enable row level security;
revoke all on public.continuity_federated_execution_permits_v1 from public,anon,authenticated;
revoke all on public.continuity_federated_execution_permit_receipts_v1 from public,anon,authenticated;
grant select,insert on public.continuity_federated_execution_permits_v1 to service_role;
grant select,insert on public.continuity_federated_execution_permit_receipts_v1 to service_role;

create or replace function public.continuity_federated_permit_receipts_append_only_v1()
returns trigger
language plpgsql
set search_path='public','pg_temp'
as $$
begin
  raise exception 'continuity_federated_execution_permit_receipts_v1 is append-only';
end;
$$;

drop trigger if exists continuity_federated_permit_receipts_append_only
  on public.continuity_federated_execution_permit_receipts_v1;
create trigger continuity_federated_permit_receipts_append_only
before update or delete on public.continuity_federated_execution_permit_receipts_v1
for each row execute function public.continuity_federated_permit_receipts_append_only_v1();

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
  v_plan_authorized boolean:=false;
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

  v_plan_authorized:=coalesce((a.execution_guard->'plan_gate'->>'authorized')::boolean,false);
  if not v_plan_authorized then raise exception 'active_plan_gate_not_authorized'; end if;

  select * into cp from public.continuity_context_packets_v1 where packet_id=a.packet_id;
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

  insert into public.continuity_federated_execution_permits_v1(
    action_id,plan_action_id,packet_id,packet_snapshot_hash,
    global_frontier_hash,global_frontier_watermark_at,
    primary_awareness_receipt_ref,primary_awareness_source_watermark_at,
    expires_at,issuer,detail
  ) values (
    a.action_id,a.plan_action_id,a.packet_id,cp.snapshot_hash,
    p.last_snapshot_hash,p.last_watermark_at,
    trim(p_primary_awareness_receipt_ref),p_primary_awareness_source_watermark_at,
    now()+make_interval(secs=>v_ttl),trim(p_issuer),coalesce(p_detail,'{}'::jsonb)
  )
  on conflict(action_id,packet_snapshot_hash,global_frontier_hash,primary_awareness_receipt_ref)
  do update set detail=public.continuity_federated_execution_permits_v1.detail||excluded.detail
  returning * into v_permit;

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
  ) on conflict(permit_id,receipt_type) do nothing;

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

revoke all on function public.continuity_issue_federated_execution_permit_v1(uuid,text,text,timestamptz,text,integer,jsonb)
from public,anon,authenticated;
grant execute on function public.continuity_issue_federated_execution_permit_v1(uuid,text,text,timestamptz,text,integer,jsonb)
to service_role;

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
  consumed boolean:=false;
  revoked boolean:=false;
begin
  select * into pmt from public.continuity_federated_execution_permits_v1 where permit_id=p_permit_id;
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

  select * into a from public.continuity_outbound_actions_v1 where action_id=p_action_id;
  if not found or a.status<>'executing' then return jsonb_build_object('ready',false,'reason','action_not_executing'); end if;
  if a.plan_action_id is distinct from pmt.plan_action_id then return jsonb_build_object('ready',false,'reason','plan_action_changed'); end if;
  if a.packet_id is distinct from pmt.packet_id then return jsonb_build_object('ready',false,'reason','packet_changed'); end if;
  if coalesce((a.execution_guard->>'execution_ready')::boolean,false) is not true then return jsonb_build_object('ready',false,'reason','backend_execution_guard_not_ready'); end if;

  select * into peer from public.continuity_peer_frontiers_v1 where peer_key='supabase-glaciereq.global-frontier';
  if not found or peer.sync_status<>'healthy' then return jsonb_build_object('ready',false,'reason','global_frontier_peer_not_healthy'); end if;
  if peer.last_snapshot_hash is distinct from pmt.global_frontier_hash then return jsonb_build_object('ready',false,'reason','global_frontier_advanced_or_changed'); end if;
  if peer.last_watermark_at is null or peer.last_watermark_at < now()-interval '15 minutes' then return jsonb_build_object('ready',false,'reason','global_frontier_checkpoint_stale'); end if;

  insert into public.continuity_federated_execution_permit_receipts_v1(permit_id,action_id,receipt_type,outcome,detail)
  values(pmt.permit_id,pmt.action_id,'VALIDATED','READY_FOR_PROVIDER_DISPATCH',jsonb_build_object('validated_at',now()))
  on conflict(permit_id,receipt_type) do nothing;

  return jsonb_build_object('ready',true,'reason','federated_execution_current','permit_id',pmt.permit_id,'expires_at',pmt.expires_at);
end;
$$;

revoke all on function public.continuity_validate_federated_execution_permit_v1(uuid,uuid)
from public,anon,authenticated;
grant execute on function public.continuity_validate_federated_execution_permit_v1(uuid,uuid)
to service_role;

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
begin
  v:=public.continuity_validate_federated_execution_permit_v1(p_permit_id,p_action_id);
  if not coalesce((v->>'ready')::boolean,false) then return v; end if;

  insert into public.continuity_federated_execution_permit_receipts_v1(permit_id,action_id,receipt_type,outcome,detail)
  values(p_permit_id,p_action_id,'CONSUMED','PROVIDER_DISPATCH_STARTED',coalesce(p_detail,'{}'::jsonb)||jsonb_build_object('provider_ref',p_provider_ref,'consumed_at',now()))
  on conflict(permit_id,receipt_type) do nothing;

  return jsonb_build_object('ready',true,'consumed',true,'permit_id',p_permit_id,'action_id',p_action_id,'provider_ref',p_provider_ref);
end;
$$;

revoke all on function public.continuity_consume_federated_execution_permit_v1(uuid,uuid,text,jsonb)
from public,anon,authenticated;
grant execute on function public.continuity_consume_federated_execution_permit_v1(uuid,uuid,text,jsonb)
to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'federated_execution_permit',true,
  jsonb_build_object(
    'version',1,
    'mode','staged_adapter_binding',
    'ttl_seconds_default',300,
    'ttl_seconds_max',600,
    'requires_backend_execution_guard',true,
    'requires_active_plan_gate',true,
    'requires_current_primary_frontier_hash',true,
    'requires_primary_awareness_receipt',true,
    'provider_adapter_enforcement','pending_explicit_adapter_binding',
    'rule','Provider adapters may claim globally current execution only after validating and consuming an unexpired federated execution permit.'
  )
)
on conflict(control_key) do update set enabled=true,state=public.continuity_control_state_v1.state||excluded.state,updated_at=now();