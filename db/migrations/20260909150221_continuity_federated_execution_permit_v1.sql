-- Harmonized execution prerequisites retained from superseded branches/runtime state.
-- Only the substrate required by the surviving federated-permit contract is kept here.

alter table public.continuity_outbound_actions_v1
  add column if not exists requires_operator_approval boolean not null default true,
  add column if not exists approved_at timestamptz,
  add column if not exists approved_by text,
  add column if not exists not_before timestamptz,
  add column if not exists execution_guard jsonb not null default '{}'::jsonb;

create table if not exists public.continuity_case_execution_plans_v1 (
  plan_id uuid primary key default gen_random_uuid(),
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  plan_key text not null unique,
  title text not null,
  status text not null default 'draft' check (status in ('draft','active','paused','completed','withdrawn','superseded')),
  approved_at timestamptz,
  approved_by text,
  source_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status <> 'active') or (approved_at is not null and coalesce(trim(approved_by),'') <> ''))
);

create table if not exists public.continuity_case_execution_plan_actions_v1 (
  plan_action_id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.continuity_case_execution_plans_v1(plan_id) on delete cascade,
  action_key text not null,
  channel text check (channel is null or channel in ('email','phone','calendar','other')),
  target text,
  intended_action text,
  status text not null default 'authorized' check (status in ('authorized','paused','satisfied','superseded','withdrawn')),
  not_before timestamptz,
  expires_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(plan_id,action_key)
);

alter table public.continuity_case_execution_plans_v1 enable row level security;
alter table public.continuity_case_execution_plan_actions_v1 enable row level security;
drop policy if exists deny_client_case_execution_plans on public.continuity_case_execution_plans_v1;
create policy deny_client_case_execution_plans on public.continuity_case_execution_plans_v1 as restrictive for all to anon,authenticated using(false) with check(false);
drop policy if exists deny_client_case_execution_plan_actions on public.continuity_case_execution_plan_actions_v1;
create policy deny_client_case_execution_plan_actions on public.continuity_case_execution_plan_actions_v1 as restrictive for all to anon,authenticated using(false) with check(false);
revoke all on public.continuity_case_execution_plans_v1 from public,anon,authenticated;
revoke all on public.continuity_case_execution_plan_actions_v1 from public,anon,authenticated;
grant all on public.continuity_case_execution_plans_v1 to service_role;
grant all on public.continuity_case_execution_plan_actions_v1 to service_role;

alter table public.continuity_outbound_actions_v1
  add column if not exists plan_action_id uuid references public.continuity_case_execution_plan_actions_v1(plan_action_id) on delete set null,
  add column if not exists handoff_state text not null default 'REPLAN_REQUIRED';

do $$ begin
  if not exists(select 1 from pg_constraint where conname='continuity_outbound_actions_v1_handoff_state_check') then
    alter table public.continuity_outbound_actions_v1 add constraint continuity_outbound_actions_v1_handoff_state_check
      check(handoff_state in ('REPLAN_REQUIRED','READY_FOR_CROSS_CASE_EXECUTION','CONSUMED','SUPPRESSED'));
  end if;
end $$;

create index if not exists continuity_case_execution_plans_v1_matter_id_idx on public.continuity_case_execution_plans_v1(matter_id);
create index if not exists continuity_outbound_actions_v1_plan_action_id_idx on public.continuity_outbound_actions_v1(plan_action_id);

create or replace function public.continuity_case_plan_gate_v1(p_action_id uuid)
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare
  a public.continuity_outbound_actions_v1%rowtype;
  pa public.continuity_case_execution_plan_actions_v1%rowtype;
  p public.continuity_case_execution_plans_v1%rowtype;
  reason text;
begin
  select * into a from public.continuity_outbound_actions_v1 where action_id=p_action_id;
  if not found then raise exception 'unknown_action'; end if;
  if a.plan_action_id is null then return jsonb_build_object('authorized',false,'state','REPLAN_REQUIRED','reason','no_active_plan_action_bound'); end if;
  select * into pa from public.continuity_case_execution_plan_actions_v1 where plan_action_id=a.plan_action_id;
  if not found then return jsonb_build_object('authorized',false,'state','REPLAN_REQUIRED','reason','plan_action_missing'); end if;
  select * into p from public.continuity_case_execution_plans_v1 where plan_id=pa.plan_id;
  if not found then return jsonb_build_object('authorized',false,'state','REPLAN_REQUIRED','reason','plan_missing'); end if;
  if p.matter_id<>a.matter_id then reason:='plan_matter_mismatch';
  elsif p.status<>'active' or p.approved_at is null or coalesce(trim(p.approved_by),'')='' then reason:='plan_not_active_operator_approved';
  elsif pa.status<>'authorized' then reason:='plan_action_not_authorized';
  elsif pa.not_before is not null and pa.not_before>now() then reason:='plan_action_not_yet_active';
  elsif pa.expires_at is not null and pa.expires_at<=now() then reason:='plan_action_expired';
  elsif pa.channel is not null and pa.channel<>a.channel then reason:='plan_action_channel_mismatch';
  elsif pa.target is not null and lower(pa.target)<>lower(a.target) then reason:='plan_action_target_mismatch';
  elsif pa.intended_action is not null and pa.intended_action<>a.intended_action then reason:='plan_action_intent_mismatch';
  end if;
  if reason is not null then return jsonb_build_object('authorized',false,'state','REPLAN_REQUIRED','reason',reason,'plan_id',p.plan_id,'plan_action_id',pa.plan_action_id); end if;
  return jsonb_build_object('authorized',true,'state','READY_FOR_CROSS_CASE_EXECUTION','reason','active_operator_approved_plan','plan_id',p.plan_id,'plan_key',p.plan_key,'plan_action_id',pa.plan_action_id,'approved_at',p.approved_at,'approved_by',p.approved_by);
end;
$$;
revoke all on function public.continuity_case_plan_gate_v1(uuid) from public,anon,authenticated;
grant execute on function public.continuity_case_plan_gate_v1(uuid) to service_role;

create or replace function public.continuity_preflight_outbound_v3(p_packet_id uuid,p_channel text,p_target text,p_exclude_action_id uuid default null)
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare
  v_packet public.continuity_context_packets_v1%rowtype;
  v_matter_updated timestamptz; v_latest_fact timestamptz; v_latest_event timestamptz; v_latest_commitment timestamptz;
  v_recent_duplicate integer:=0; v_target_bounced integer:=0; v_stale boolean:=false; v_block_reason text:=null;
begin
  select * into v_packet from public.continuity_context_packets_v1 where packet_id=p_packet_id;
  if not found then raise exception 'unknown_context_packet'; end if;
  if v_packet.expires_at<now() then return jsonb_build_object('ready',false,'reason','context_packet_expired','packet_id',p_packet_id); end if;
  if p_channel<>v_packet.action_channel then return jsonb_build_object('ready',false,'reason','channel_mismatch'); end if;
  select updated_at into v_matter_updated from public.continuity_matters_v1 where matter_id=v_packet.matter_id;
  select max(created_at) into v_latest_fact from public.continuity_facts_v1 where matter_id=v_packet.matter_id and superseded_by is null;
  select max(created_at) into v_latest_event from public.continuity_events_v1 where matter_id=v_packet.matter_id;
  select max(updated_at) into v_latest_commitment from public.continuity_commitments_v1 where matter_id=v_packet.matter_id;
  v_stale:=greatest(coalesce(v_matter_updated,'epoch'),coalesce(v_latest_fact,'epoch'),coalesce(v_latest_event,'epoch'),coalesce(v_latest_commitment,'epoch'))>v_packet.snapshot_at;
  select count(*) into v_recent_duplicate from public.continuity_outbound_actions_v1 where matter_id=v_packet.matter_id and channel=p_channel and lower(target)=lower(p_target) and created_at>now()-interval '60 minutes' and status in('planned','approved','executing','sent','completed') and (p_exclude_action_id is null or action_id<>p_exclude_action_id);
  if p_channel='email' then select count(*) into v_target_bounced from public.continuity_events_v1 where matter_id=v_packet.matter_id and event_type='email_delivery_failure' and lower(coalesce(metadata->>'failed_recipient',''))=lower(p_target) and occurred_at>now()-interval '30 days'; end if;
  if v_stale then v_block_reason:='context_packet_stale'; elsif v_recent_duplicate>0 then v_block_reason:='recent_duplicate_action'; elsif v_target_bounced>0 and lower(v_packet.action_purpose) not like '%repair%' then v_block_reason:='target_has_unrepaired_delivery_failure'; end if;
  return jsonb_build_object('ready',v_block_reason is null,'reason',coalesce(v_block_reason,'ready'),'packet_id',p_packet_id,'snapshot_hash',v_packet.snapshot_hash,'target',p_target);
end;
$$;
revoke all on function public.continuity_preflight_outbound_v3(uuid,text,text,uuid) from public,anon,authenticated;
grant execute on function public.continuity_preflight_outbound_v3(uuid,text,text,uuid) to service_role;

create or replace function public.continuity_bind_outbound_to_plan_v1(p_action_id uuid,p_plan_action_id uuid)
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare v_gate jsonb; v_action public.continuity_outbound_actions_v1%rowtype;
begin
  update public.continuity_outbound_actions_v1 set plan_action_id=p_plan_action_id,updated_at=now() where action_id=p_action_id returning * into v_action;
  if not found then raise exception 'unknown_action'; end if;
  v_gate:=public.continuity_case_plan_gate_v1(p_action_id);
  update public.continuity_outbound_actions_v1 set handoff_state=case when coalesce((v_gate->>'authorized')::boolean,false) then 'READY_FOR_CROSS_CASE_EXECUTION' else 'REPLAN_REQUIRED' end,status=case when coalesce((v_gate->>'authorized')::boolean,false) and status='planned' then 'approved' else status end,execution_guard=coalesce(execution_guard,'{}'::jsonb)||jsonb_build_object('plan_gate',v_gate,'execution_ready',false),updated_at=now() where action_id=p_action_id returning * into v_action;
  return jsonb_build_object('action_id',v_action.action_id,'status',v_action.status,'handoff_state',v_action.handoff_state,'plan_gate',v_gate);
end;
$$;
revoke all on function public.continuity_bind_outbound_to_plan_v1(uuid,uuid) from public,anon,authenticated;
grant execute on function public.continuity_bind_outbound_to_plan_v1(uuid,uuid) to service_role;

create or replace function public.continuity_start_outbound_v1(p_action_id uuid,p_provider_ref text default null,p_detail jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare a public.continuity_outbound_actions_v1%rowtype; v_gate jsonb; v_preflight jsonb; v_guard jsonb;
begin
  select * into a from public.continuity_outbound_actions_v1 where action_id=p_action_id for update;
  if not found then raise exception 'unknown_action'; end if;
  v_gate:=public.continuity_case_plan_gate_v1(a.action_id);
  if not coalesce((v_gate->>'authorized')::boolean,false) then update public.continuity_outbound_actions_v1 set handoff_state='REPLAN_REQUIRED',execution_guard=coalesce(execution_guard,'{}'::jsonb)||jsonb_build_object('execution_ready',false,'block_reason','REPLAN_REQUIRED','plan_gate',v_gate),updated_at=now() where action_id=a.action_id; return jsonb_build_object('action_id',a.action_id,'ready',false,'reason',v_gate->>'reason','plan_gate',v_gate); end if;
  if a.status not in('approved','executing') then raise exception 'action_not_startable'; end if;
  v_preflight:=public.continuity_preflight_outbound_v3(a.packet_id,a.channel,a.target,a.action_id);
  if not coalesce((v_preflight->>'ready')::boolean,false) then update public.continuity_outbound_actions_v1 set execution_guard=coalesce(execution_guard,'{}'::jsonb)||jsonb_build_object('execution_ready',false,'block_reason',v_preflight->>'reason','plan_gate',v_gate),updated_at=now() where action_id=a.action_id; return jsonb_build_object('action_id',a.action_id,'ready',false,'reason',v_preflight->>'reason','preflight',v_preflight,'plan_gate',v_gate); end if;
  v_guard:=jsonb_build_object('execution_ready',true,'checked_at',now(),'packet_id',a.packet_id,'snapshot_hash',v_preflight->>'snapshot_hash','plan_gate',v_gate);
  update public.continuity_outbound_actions_v1 set status='executing',handoff_state='CONSUMED',provider_ref=coalesce(p_provider_ref,provider_ref),started_at=coalesce(started_at,now()),execution_guard=coalesce(execution_guard,'{}'::jsonb)||v_guard,updated_at=now() where action_id=a.action_id returning * into a;
  return jsonb_build_object('action_id',a.action_id,'status',a.status,'ready',true,'provider_ref',a.provider_ref,'preflight',v_preflight,'plan_gate',v_gate,'execution_guard',a.execution_guard,'detail',coalesce(p_detail,'{}'::jsonb));
end;
$$;
revoke all on function public.continuity_start_outbound_v1(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.continuity_start_outbound_v1(uuid,text,jsonb) to service_role;

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
  check(expires_at > issued_at)
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