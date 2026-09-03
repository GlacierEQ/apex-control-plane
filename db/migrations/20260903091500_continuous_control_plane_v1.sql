-- APEX continuous control plane v1
create table if not exists public.control_missions_v1 (
  mission_id text primary key,
  correlation_id text not null,
  domain text not null,
  objective text not null,
  status text not null default 'active'
    check (status in ('active','waiting','blocked','complete','closed')),
  priority integer not null default 50 check (priority between 0 and 100),
  current_frontier jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_progress_at timestamptz,
  completed_at timestamptz
);

create table if not exists public.control_events_v1 (
  event_id text primary key,
  event_type text not null,
  source_system text not null,
  subject_id text not null,
  correlation_id text not null,
  causation_id text,
  dedupe_key text not null unique,
  occurred_at timestamptz not null,
  observed_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  provenance_refs jsonb not null default '[]'::jsonb
);
create index if not exists control_events_v1_corr_idx on public.control_events_v1(correlation_id,occurred_at desc);
create index if not exists control_events_v1_subject_idx on public.control_events_v1(subject_id,occurred_at desc);
create index if not exists control_events_v1_type_idx on public.control_events_v1(event_type,occurred_at desc);

create table if not exists public.control_work_items_v1 (
  work_id text primary key,
  mission_id text not null references public.control_missions_v1(mission_id) on delete cascade,
  correlation_id text not null,
  domain text not null,
  capability text not null,
  objective text not null,
  state text not null check (state in (
    'RECEIVED','HYDRATING','COMPILED','DISPATCHED','EXECUTING','WAITING',
    'RECONCILING','CHANGESET_READY','MUTATING','READBACK','VERIFYING',
    'COMPLETE','BLOCKED','DEAD_LETTER'
  )),
  priority integer not null default 50 check (priority between 0 and 100),
  idempotency_key text not null unique,
  external_action boolean not null default false,
  approval_ref text,
  source_event_ids jsonb not null default '[]'::jsonb,
  required_receipt_kinds jsonb not null default '[]'::jsonb,
  not_before timestamptz,
  lease_owner text,
  lease_expires_at timestamptz,
  attempt integer not null default 0,
  max_attempts integer not null default 5 check (max_attempts >= 1),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  check (not (state='MUTATING' and external_action and approval_ref is null))
);
create index if not exists control_work_items_v1_claim_idx on public.control_work_items_v1(state,priority desc,not_before,lease_expires_at);
create index if not exists control_work_items_v1_mission_idx on public.control_work_items_v1(mission_id,updated_at desc);
create index if not exists control_work_items_v1_cap_idx on public.control_work_items_v1(capability,state);

create table if not exists public.control_work_transitions_v1 (
  transition_id bigint generated always as identity primary key,
  work_id text not null references public.control_work_items_v1(work_id) on delete cascade,
  from_state text,
  to_state text not null,
  reason text not null,
  actor text,
  detail jsonb not null default '{}'::jsonb,
  recorded_at timestamptz not null default now()
);
create index if not exists control_work_transitions_v1_work_idx on public.control_work_transitions_v1(work_id,recorded_at);

create table if not exists public.control_execution_receipts_v1 (
  receipt_id text primary key,
  work_id text not null references public.control_work_items_v1(work_id) on delete cascade,
  mission_id text not null references public.control_missions_v1(mission_id) on delete cascade,
  correlation_id text not null,
  receipt_kind text not null,
  status text not null,
  source_system text not null,
  provider_receipt_id text,
  details jsonb not null default '{}'::jsonb,
  details_sha256 text not null check (details_sha256 ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz not null default now()
);
create unique index if not exists control_execution_receipts_v1_provider_uidx
  on public.control_execution_receipts_v1(source_system,provider_receipt_id)
  where provider_receipt_id is not null;
create index if not exists control_execution_receipts_v1_work_idx
  on public.control_execution_receipts_v1(work_id,recorded_at desc);

create table if not exists public.control_mission_checkpoints_v1 (
  checkpoint_id bigint generated always as identity primary key,
  mission_id text not null references public.control_missions_v1(mission_id) on delete cascade,
  correlation_id text not null,
  frontier jsonb not null,
  work_state_counts jsonb not null,
  receipt_count integer not null default 0,
  checkpoint_sha256 text not null check (checkpoint_sha256 ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz not null default now()
);
create index if not exists control_mission_checkpoints_v1_mission_idx
  on public.control_mission_checkpoints_v1(mission_id,recorded_at desc);

create or replace function public.claim_control_work_v1(
  p_worker_id text,
  p_capabilities text[],
  p_lease_seconds integer default 90
)
returns public.control_work_items_v1
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  claimed public.control_work_items_v1;
begin
  if p_worker_id is null or btrim(p_worker_id)='' then
    raise exception 'worker id required';
  end if;
  if p_lease_seconds < 1 then
    raise exception 'lease seconds must be positive';
  end if;

  select *
  into claimed
  from public.control_work_items_v1
  where state='COMPILED'
    and capability = any(p_capabilities)
    and (not_before is null or not_before <= now())
    and (lease_expires_at is null or lease_expires_at <= now())
    and attempt < max_attempts
  order by priority desc,created_at,work_id
  for update skip locked
  limit 1;

  if claimed.work_id is null then
    return null;
  end if;

  update public.control_work_items_v1
  set state='DISPATCHED',
      lease_owner=p_worker_id,
      lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
      attempt=attempt+1,
      updated_at=now()
  where work_id=claimed.work_id
  returning * into claimed;

  insert into public.control_work_transitions_v1(work_id,from_state,to_state,reason,actor)
  values(claimed.work_id,'COMPILED','DISPATCHED','claimed',p_worker_id);

  return claimed;
end;
$$;

create or replace function public.reawaken_due_control_work_v1()
returns integer
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare changed integer;
begin
  with due as (
    update public.control_work_items_v1
    set state='RECEIVED',lease_owner=null,lease_expires_at=null,updated_at=now()
    where state='WAITING' and not_before is not null and not_before <= now()
    returning work_id
  ),
  history as (
    insert into public.control_work_transitions_v1(work_id,from_state,to_state,reason,actor)
    select work_id,'WAITING','RECEIVED','waiting_deadline_due','scheduler' from due
    returning 1
  )
  select count(*) into changed from history;
  return coalesce(changed,0);
end;
$$;

create or replace view public.continuous_control_plane_snapshot_v1 as
with work as (
  select
    count(*) as total_work,
    count(*) filter(where state='COMPLETE') as complete_work,
    count(*) filter(where state='WAITING') as waiting_work,
    count(*) filter(where state='BLOCKED') as blocked_work,
    count(*) filter(where state='DEAD_LETTER') as dead_letter_work,
    count(*) filter(where lease_expires_at < now() and state in ('DISPATCHED','EXECUTING')) as expired_leases
  from public.control_work_items_v1
),
missions as (
  select
    count(*) as total_missions,
    count(*) filter(where status='active') as active_missions,
    count(*) filter(where status='blocked') as blocked_missions
  from public.control_missions_v1
),
events as (
  select count(*) as total_events,max(observed_at) as latest_event_at from public.control_events_v1
),
receipts as (
  select count(*) as total_receipts,max(recorded_at) as latest_receipt_at from public.control_execution_receipts_v1
)
select now() as observed_at,missions.*,work.*,events.*,receipts.*
from missions cross join work cross join events cross join receipts;

revoke all on public.control_missions_v1 from public,anon,authenticated;
revoke all on public.control_events_v1 from public,anon,authenticated;
revoke all on public.control_work_items_v1 from public,anon,authenticated;
revoke all on public.control_work_transitions_v1 from public,anon,authenticated;
revoke all on public.control_execution_receipts_v1 from public,anon,authenticated;
revoke all on public.control_mission_checkpoints_v1 from public,anon,authenticated;
revoke all on public.continuous_control_plane_snapshot_v1 from public,anon,authenticated;
grant select,insert,update on public.control_missions_v1 to service_role;
grant select,insert on public.control_events_v1 to service_role;
grant select,insert,update on public.control_work_items_v1 to service_role;
grant select,insert on public.control_work_transitions_v1 to service_role;
grant select,insert on public.control_execution_receipts_v1 to service_role;
grant select,insert on public.control_mission_checkpoints_v1 to service_role;
grant select on public.continuous_control_plane_snapshot_v1 to service_role;
grant execute on function public.claim_control_work_v1(text,text[],integer) to service_role;
grant execute on function public.reawaken_due_control_work_v1() to service_role;
