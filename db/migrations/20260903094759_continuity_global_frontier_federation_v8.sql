create table if not exists public.continuity_peer_frontiers_v1(
  peer_key text primary key,
  peer_role text not null,
  authority_scope jsonb not null default '[]'::jsonb,
  projection_scope jsonb not null default '[]'::jsonb,
  last_snapshot_hash text,
  last_watermark_at timestamptz,
  last_receipt_ref text,
  sync_status text not null default 'never_synced'
    check(sync_status in ('never_synced','healthy','stale','error')),
  error_state jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.continuity_peer_frontiers_v1 enable row level security;
revoke all on table public.continuity_peer_frontiers_v1 from public,anon,authenticated;
grant select,insert,update,delete on table public.continuity_peer_frontiers_v1 to service_role;

create or replace function public.continuity_record_peer_frontier_v1(
  p_peer_key text,
  p_peer_role text,
  p_authority_scope jsonb,
  p_projection_scope jsonb,
  p_snapshot_hash text,
  p_watermark_at timestamptz,
  p_receipt_ref text default null,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_row public.continuity_peer_frontiers_v1%rowtype;
begin
  if coalesce(trim(p_peer_key),'')='' then raise exception 'peer_key_required'; end if;
  if coalesce(trim(p_peer_role),'')='' then raise exception 'peer_role_required'; end if;
  if p_snapshot_hash is not null and p_snapshot_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_snapshot_hash';
  end if;
  if jsonb_typeof(coalesce(p_authority_scope,'[]'::jsonb))<>'array'
     or jsonb_typeof(coalesce(p_projection_scope,'[]'::jsonb))<>'array'
     or jsonb_typeof(coalesce(p_metadata,'{}'::jsonb))<>'object' then
    raise exception 'invalid_peer_frontier_payload';
  end if;

  insert into public.continuity_peer_frontiers_v1(
    peer_key,peer_role,authority_scope,projection_scope,last_snapshot_hash,
    last_watermark_at,last_receipt_ref,sync_status,error_state,metadata,updated_at
  ) values (
    p_peer_key,p_peer_role,coalesce(p_authority_scope,'[]'::jsonb),
    coalesce(p_projection_scope,'[]'::jsonb),p_snapshot_hash,p_watermark_at,p_receipt_ref,
    'healthy','{}'::jsonb,coalesce(p_metadata,'{}'::jsonb),now()
  )
  on conflict(peer_key) do update set
    peer_role=excluded.peer_role,
    authority_scope=excluded.authority_scope,
    projection_scope=excluded.projection_scope,
    last_snapshot_hash=excluded.last_snapshot_hash,
    last_watermark_at=excluded.last_watermark_at,
    last_receipt_ref=excluded.last_receipt_ref,
    sync_status='healthy',
    error_state='{}'::jsonb,
    metadata=public.continuity_peer_frontiers_v1.metadata||excluded.metadata,
    updated_at=now()
  returning * into v_row;

  return jsonb_build_object(
    'peer_key',v_row.peer_key,
    'sync_status',v_row.sync_status,
    'last_snapshot_hash',v_row.last_snapshot_hash,
    'last_watermark_at',v_row.last_watermark_at,
    'last_receipt_ref',v_row.last_receipt_ref
  );
end;
$$;

revoke all on function public.continuity_record_peer_frontier_v1(
  text,text,jsonb,jsonb,text,timestamptz,text,jsonb
) from public,anon,authenticated;
grant execute on function public.continuity_record_peer_frontier_v1(
  text,text,jsonb,jsonb,text,timestamptz,text,jsonb
) to service_role;

insert into public.continuity_peer_frontiers_v1(
  peer_key,peer_role,authority_scope,projection_scope,sync_status,metadata
) values (
  'supabase-glaciereq.global-frontier',
  'global_projection',
  '["estate_global_frontier","global_action_outbox","global_obligations","operator_cursor"]'::jsonb,
  '["frontier_hash","watermark","operator_cursor_ref","receipt_refs","priority_counts"]'::jsonb,
  'never_synced',
  jsonb_build_object(
    'project_id','kjebemdgvjvuutzvhbtp',
    'source_view','control_plane_global_frontier_v2',
    'authority_direction','DOCKETS -> Backend Ops continuity/legal runtime -> primary global projection',
    'replication_policy','hash_watermark_receipts_only'
  )
)
on conflict(peer_key) do update set
  peer_role=excluded.peer_role,
  authority_scope=excluded.authority_scope,
  projection_scope=excluded.projection_scope,
  metadata=public.continuity_peer_frontiers_v1.metadata||excluded.metadata,
  updated_at=now();

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'federated_global_frontier',true,
  jsonb_build_object(
    'version',1,
    'case_truth','GlacierEQ/DOCKETS',
    'communications_legal_runtime','supabase-backend-ops',
    'global_projection','supabase-glaciereq/control_plane_global_frontier_v2',
    'provider_truth','provider-native receipts',
    'replication_policy','frontier_hash_watermark_receipts_only',
    'sync_function','continuity_record_peer_frontier_v1',
    'split_brain_policy','fail_closed_on_conflicting_authority_claims'
  )
)
on conflict(control_key) do update set
  enabled=true,
  state=public.continuity_control_state_v1.state||excluded.state,
  updated_at=now();

