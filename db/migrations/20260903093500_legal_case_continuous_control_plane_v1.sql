create table if not exists public.legal_case_control_events_v1 (
  event_id text primary key,
  case_id text not null,
  event_type text not null,
  source text not null,
  correlation_id text not null,
  causation_id text,
  idempotency_key text not null unique,
  occurred_at timestamptz not null,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now()
);

create table if not exists public.legal_case_runtime_health_v1 (
  case_id text primary key,
  observed_at timestamptz not null,
  source_status text not null,
  effective_status text not null
    check (effective_status in ('healthy','degraded','blocked','unknown')),
  backlog integer not null default 0 check (backlog >= 0),
  inflight integer not null default 0 check (inflight >= 0),
  failed integer not null default 0 check (failed >= 0),
  blocked integer not null default 0 check (blocked >= 0),
  live_workers integer not null default 0 check (live_workers >= 0),
  stale_workers integer not null default 0 check (stale_workers >= 0),
  revision_chain_valid boolean,
  evidence_chain_valid boolean,
  build_verified boolean,
  truth_acceptance text not null default 'unknown'
    check (truth_acceptance in ('unknown','accepted','rejected')),
  blocked_reasons jsonb not null default '[]'::jsonb,
  degraded_reasons jsonb not null default '[]'::jsonb,
  detail jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.legal_case_control_receipts_v1 (
  receipt_id uuid primary key default gen_random_uuid(),
  case_id text not null,
  event_id text,
  receipt_type text not null
    check (receipt_type in (
      'event_ingested',
      'event_idempotent_replay',
      'health_upserted'
    )),
  outcome text not null
    check (outcome in ('succeeded','replayed','rejected')),
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists legal_case_events_case_time_idx
  on public.legal_case_control_events_v1(case_id,occurred_at desc);
create index if not exists legal_case_events_type_time_idx
  on public.legal_case_control_events_v1(event_type,occurred_at desc);
create index if not exists legal_case_health_status_idx
  on public.legal_case_runtime_health_v1(effective_status,updated_at desc);
create index if not exists legal_case_receipts_case_time_idx
  on public.legal_case_control_receipts_v1(case_id,created_at desc);

alter table public.legal_case_control_events_v1 enable row level security;
alter table public.legal_case_runtime_health_v1 enable row level security;
alter table public.legal_case_control_receipts_v1 enable row level security;

revoke all on public.legal_case_control_events_v1 from public,anon,authenticated;
revoke all on public.legal_case_runtime_health_v1 from public,anon,authenticated;
revoke all on public.legal_case_control_receipts_v1 from public,anon,authenticated;

grant select,insert on public.legal_case_control_events_v1 to service_role;
grant select,insert,update on public.legal_case_runtime_health_v1 to service_role;
grant select,insert on public.legal_case_control_receipts_v1 to service_role;

comment on table public.legal_case_control_events_v1 is
  'Service-role-only immutable mirror of Casebuilder4000 control events. Event lifecycle never promotes case truth class.';
comment on table public.legal_case_runtime_health_v1 is
  'Service-role-only current operational health projection for legal cases. Historical failures live in event/receipt history and do not permanently poison recovered current health.';
comment on table public.legal_case_control_receipts_v1 is
  'Append-only receipts for legal case event/health projection ingestion.';

create or replace function public.legal_case_control_immutable_v1()
returns trigger
language plpgsql
set search_path='pg_catalog'
as $$
begin
  raise exception 'legal_case_control_history_is_append_only';
end;
$$;

drop trigger if exists legal_case_control_events_v1_immutable
  on public.legal_case_control_events_v1;
create trigger legal_case_control_events_v1_immutable
before update or delete on public.legal_case_control_events_v1
for each row execute function public.legal_case_control_immutable_v1();

drop trigger if exists legal_case_control_receipts_v1_immutable
  on public.legal_case_control_receipts_v1;
create trigger legal_case_control_receipts_v1_immutable
before update or delete on public.legal_case_control_receipts_v1
for each row execute function public.legal_case_control_immutable_v1();

create or replace function public.ingest_legal_case_control_event_v1(
  p_event jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_event_id text;
  v_case_id text;
  v_event_type text;
  v_source text;
  v_correlation_id text;
  v_causation_id text;
  v_idempotency_key text;
  v_occurred_at timestamptz;
  v_existing public.legal_case_control_events_v1%rowtype;
begin
  if p_event is null or jsonb_typeof(p_event) <> 'object' then
    raise exception 'event_must_be_object';
  end if;
  if octet_length(p_event::text) > 1048576 then
    raise exception 'event_payload_too_large';
  end if;

  v_event_id := nullif(trim(p_event->>'id'),'');
  v_case_id := nullif(trim(p_event->>'case_id'),'');
  v_event_type := nullif(trim(p_event->>'event_type'),'');
  v_source := nullif(trim(p_event->>'source'),'');
  v_correlation_id := nullif(trim(p_event->>'correlation_id'),'');
  v_causation_id := nullif(trim(p_event->>'causation_id'),'');
  v_idempotency_key := nullif(trim(p_event->>'idempotency_key'),'');
  v_occurred_at := nullif(trim(p_event->>'occurred_at'),'')::timestamptz;

  if v_event_id is null or length(v_event_id) > 128 then
    raise exception 'invalid_event_id';
  end if;
  if v_case_id is null or length(v_case_id) > 256 then
    raise exception 'invalid_case_id';
  end if;
  if v_event_type is null or length(v_event_type) > 128 then
    raise exception 'invalid_event_type';
  end if;
  if v_source is null or length(v_source) > 256 then
    raise exception 'invalid_event_source';
  end if;
  if v_correlation_id is null or length(v_correlation_id) > 128 then
    raise exception 'invalid_correlation_id';
  end if;
  if v_idempotency_key is null or length(v_idempotency_key) > 512 then
    raise exception 'invalid_idempotency_key';
  end if;
  if v_occurred_at is null then
    raise exception 'invalid_occurred_at';
  end if;
  if coalesce(jsonb_typeof(p_event->'payload'),'object') <> 'object' then
    raise exception 'event_payload_must_be_object';
  end if;

  select * into v_existing
  from public.legal_case_control_events_v1
  where idempotency_key=v_idempotency_key;

  if found then
    insert into public.legal_case_control_receipts_v1(
      case_id,event_id,receipt_type,outcome,detail
    ) values (
      v_existing.case_id,
      v_existing.event_id,
      'event_idempotent_replay',
      'replayed',
      jsonb_build_object(
        'idempotency_key',v_idempotency_key,
        'original_received_at',v_existing.received_at
      )
    );
    return jsonb_build_object(
      'created',false,
      'idempotent_replay',true,
      'event_id',v_existing.event_id,
      'case_id',v_existing.case_id
    );
  end if;

  insert into public.legal_case_control_events_v1(
    event_id,case_id,event_type,source,correlation_id,causation_id,
    idempotency_key,occurred_at,payload
  ) values (
    v_event_id,v_case_id,v_event_type,v_source,v_correlation_id,v_causation_id,
    v_idempotency_key,v_occurred_at,coalesce(p_event->'payload','{}'::jsonb)
  );

  insert into public.legal_case_control_receipts_v1(
    case_id,event_id,receipt_type,outcome,detail
  ) values (
    v_case_id,
    v_event_id,
    'event_ingested',
    'succeeded',
    jsonb_build_object(
      'event_type',v_event_type,
      'source',v_source,
      'correlation_id',v_correlation_id
    )
  );

  return jsonb_build_object(
    'created',true,
    'idempotent_replay',false,
    'event_id',v_event_id,
    'case_id',v_case_id
  );
end;
$$;

create or replace function public.upsert_legal_case_runtime_health_v1(
  p_case_id text,
  p_health jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_status text;
  v_source_status text;
  v_observed_at timestamptz;
  v_backlog integer;
  v_inflight integer;
  v_failed integer;
  v_blocked integer;
  v_live_workers integer;
  v_stale_workers integer;
  v_revision boolean;
  v_evidence boolean;
  v_build boolean;
  v_truth text;
begin
  if p_case_id is null or length(trim(p_case_id)) < 1 or length(p_case_id) > 256 then
    raise exception 'invalid_case_id';
  end if;
  if p_health is null or jsonb_typeof(p_health) <> 'object' then
    raise exception 'health_must_be_object';
  end if;
  if p_health->>'schema' <> 'apex.legal-case-runtime-health.v1' then
    raise exception 'invalid_health_schema';
  end if;
  if octet_length(p_health::text) > 1048576 then
    raise exception 'health_payload_too_large';
  end if;

  v_status := coalesce(nullif(p_health->>'status',''),'unknown');
  if v_status not in ('healthy','degraded','blocked','unknown') then
    raise exception 'invalid_effective_status';
  end if;
  v_source_status := coalesce(nullif(p_health->>'source_status',''),'unknown');
  v_observed_at := coalesce(
    nullif(p_health->>'observed_at','')::timestamptz,
    now()
  );
  v_backlog := greatest(0,coalesce((p_health#>>'{casebuilder,work,backlog}')::integer,0));
  v_inflight := greatest(0,coalesce((p_health#>>'{casebuilder,work,inflight}')::integer,0));
  v_failed := greatest(0,coalesce((p_health#>>'{casebuilder,work,failed}')::integer,0));
  v_blocked := greatest(0,coalesce((p_health#>>'{casebuilder,work,blocked}')::integer,0));
  v_live_workers := coalesce((
    select count(*)::integer
    from jsonb_array_elements(coalesce(p_health#>'{casebuilder,workers}','[]'::jsonb)) worker
    where coalesce((worker->>'stale')::boolean,false)=false
      and coalesce(worker->>'status','') in ('online','ready','running')
  ),0);
  v_stale_workers := coalesce((
    select count(*)::integer
    from jsonb_array_elements(coalesce(p_health#>'{casebuilder,workers}','[]'::jsonb)) worker
    where coalesce((worker->>'stale')::boolean,false)=true
  ),0);
  v_revision := nullif(p_health#>>'{integrity,revision_chain_valid}','')::boolean;
  v_evidence := nullif(p_health#>>'{integrity,evidence_chain_valid}','')::boolean;
  v_build := nullif(p_health#>>'{integrity,build_verified}','')::boolean;
  v_truth := coalesce(nullif(p_health#>>'{integrity,truth_acceptance}',''),'unknown');
  if v_truth not in ('unknown','accepted','rejected') then
    raise exception 'invalid_truth_acceptance';
  end if;

  insert into public.legal_case_runtime_health_v1(
    case_id,observed_at,source_status,effective_status,
    backlog,inflight,failed,blocked,live_workers,stale_workers,
    revision_chain_valid,evidence_chain_valid,build_verified,truth_acceptance,
    blocked_reasons,degraded_reasons,detail,updated_at
  ) values (
    trim(p_case_id),v_observed_at,v_source_status,v_status,
    v_backlog,v_inflight,v_failed,v_blocked,v_live_workers,v_stale_workers,
    v_revision,v_evidence,v_build,v_truth,
    coalesce(p_health->'blocked_reasons','[]'::jsonb),
    coalesce(p_health->'degraded_reasons','[]'::jsonb),
    p_health,now()
  )
  on conflict(case_id) do update set
    observed_at=excluded.observed_at,
    source_status=excluded.source_status,
    effective_status=excluded.effective_status,
    backlog=excluded.backlog,
    inflight=excluded.inflight,
    failed=excluded.failed,
    blocked=excluded.blocked,
    live_workers=excluded.live_workers,
    stale_workers=excluded.stale_workers,
    revision_chain_valid=excluded.revision_chain_valid,
    evidence_chain_valid=excluded.evidence_chain_valid,
    build_verified=excluded.build_verified,
    truth_acceptance=excluded.truth_acceptance,
    blocked_reasons=excluded.blocked_reasons,
    degraded_reasons=excluded.degraded_reasons,
    detail=excluded.detail,
    updated_at=now()
  where public.legal_case_runtime_health_v1.observed_at <= excluded.observed_at;

  insert into public.legal_case_control_receipts_v1(
    case_id,receipt_type,outcome,detail
  ) values (
    trim(p_case_id),
    'health_upserted',
    'succeeded',
    jsonb_build_object(
      'observed_at',v_observed_at,
      'effective_status',v_status,
      'backlog',v_backlog,
      'inflight',v_inflight,
      'failed',v_failed,
      'blocked',v_blocked
    )
  );

  return jsonb_build_object(
    'case_id',trim(p_case_id),
    'observed_at',v_observed_at,
    'effective_status',v_status,
    'backlog',v_backlog,
    'inflight',v_inflight,
    'failed',v_failed,
    'blocked',v_blocked,
    'live_workers',v_live_workers,
    'stale_workers',v_stale_workers
  );
end;
$$;

revoke all on function public.ingest_legal_case_control_event_v1(jsonb)
  from public,anon,authenticated;
grant execute on function public.ingest_legal_case_control_event_v1(jsonb)
  to service_role;

revoke all on function public.upsert_legal_case_runtime_health_v1(text,jsonb)
  from public,anon,authenticated;
grant execute on function public.upsert_legal_case_runtime_health_v1(text,jsonb)
  to service_role;

create or replace view public.legal_case_control_plane_health_v1
with (security_invoker=true)
as
select
  case_id,
  observed_at,
  source_status,
  effective_status,
  backlog,
  inflight,
  failed,
  blocked,
  live_workers,
  stale_workers,
  revision_chain_valid,
  evidence_chain_valid,
  build_verified,
  truth_acceptance,
  blocked_reasons,
  degraded_reasons,
  updated_at,
  detail
from public.legal_case_runtime_health_v1;

revoke all on public.legal_case_control_plane_health_v1
  from public,anon,authenticated;
grant select on public.legal_case_control_plane_health_v1
  to service_role;

comment on view public.legal_case_control_plane_health_v1 is
  'Service-role-only current legal-case control-plane health. Operational state only; never a case-truth authority.';
