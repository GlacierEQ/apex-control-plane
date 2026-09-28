create table if not exists public.github_connector_operation_leases_v2 (
  lease_key text primary key,
  request_id text not null,
  correlation_id uuid not null default gen_random_uuid(),
  actor text,
  state text not null default 'active' check (state in ('active','completed','released','failed')),
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null,
  released_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists github_connector_operation_leases_v2_expires_idx
  on public.github_connector_operation_leases_v2(expires_at);

create table if not exists public.github_connector_route_decisions_v2 (
  decision_id uuid primary key default gen_random_uuid(),
  request_id text not null,
  correlation_id uuid not null,
  operation text not null,
  repository text,
  route_key text,
  selected_connector text,
  selected_tool text,
  outcome text not null check (outcome in ('executed','fallback','rejected','failed','planned')),
  response_status integer,
  attempts integer not null default 0 check (attempts >= 0),
  lease_key text,
  expected_before_sha text,
  observed_before_sha text,
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists github_connector_route_decisions_v2_request_idx
  on public.github_connector_route_decisions_v2(request_id, created_at desc);
create index if not exists github_connector_route_decisions_v2_repo_idx
  on public.github_connector_route_decisions_v2(repository, created_at desc);

create table if not exists public.github_connector_circuit_v2 (
  circuit_key text primary key,
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  opened_until timestamptz,
  last_status integer,
  last_error text,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.github_webhook_event_queue_v1 (
  event_id uuid primary key default gen_random_uuid(),
  delivery_id text not null unique,
  event_type text not null,
  action text,
  repository text,
  status text not null default 'pending' check (status in ('pending','processing','completed','failed','ignored')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  locked_at timestamptz,
  processed_at timestamptz,
  last_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists github_webhook_event_queue_v1_ready_idx
  on public.github_webhook_event_queue_v1(status, available_at, created_at);
create index if not exists github_webhook_event_queue_v1_repo_idx
  on public.github_webhook_event_queue_v1(repository, created_at desc);

alter table public.github_connector_operation_leases_v2 enable row level security;
alter table public.github_connector_route_decisions_v2 enable row level security;
alter table public.github_connector_circuit_v2 enable row level security;
alter table public.github_webhook_event_queue_v1 enable row level security;

revoke all on public.github_connector_operation_leases_v2 from public, anon, authenticated;
revoke all on public.github_connector_route_decisions_v2 from public, anon, authenticated;
revoke all on public.github_connector_circuit_v2 from public, anon, authenticated;
revoke all on public.github_webhook_event_queue_v1 from public, anon, authenticated;

grant select, insert, update, delete on public.github_connector_operation_leases_v2 to service_role;
grant select, insert on public.github_connector_route_decisions_v2 to service_role;
grant select, insert, update on public.github_connector_circuit_v2 to service_role;
grant select, insert, update on public.github_webhook_event_queue_v1 to service_role;

create or replace function public.github_connector_route_decisions_v2_block_mutation()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  raise exception 'github_connector_route_decisions_v2 is append-only';
end;
$$;

revoke all on function public.github_connector_route_decisions_v2_block_mutation() from public, anon, authenticated;
grant execute on function public.github_connector_route_decisions_v2_block_mutation() to service_role;

drop trigger if exists github_connector_route_decisions_v2_immutable on public.github_connector_route_decisions_v2;
create trigger github_connector_route_decisions_v2_immutable
before update or delete on public.github_connector_route_decisions_v2
for each row execute function public.github_connector_route_decisions_v2_block_mutation();

create or replace function public.acquire_github_connector_lease_v2(
  p_lease_key text,
  p_request_id text,
  p_actor text,
  p_ttl_seconds integer default 90,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_row public.github_connector_operation_leases_v2%rowtype;
begin
  if p_lease_key is null or length(p_lease_key) < 3 then raise exception 'invalid lease key'; end if;
  if p_request_id is null or length(p_request_id) < 8 then raise exception 'invalid request id'; end if;
  if p_ttl_seconds < 10 or p_ttl_seconds > 600 then raise exception 'invalid lease ttl'; end if;

  insert into public.github_connector_operation_leases_v2 (
    lease_key, request_id, actor, state, acquired_at, expires_at, released_at, metadata, updated_at
  ) values (
    p_lease_key, p_request_id, p_actor, 'active', now(), now() + make_interval(secs => p_ttl_seconds), null, coalesce(p_metadata,'{}'::jsonb), now()
  )
  on conflict (lease_key) do update set
    request_id = excluded.request_id,
    actor = excluded.actor,
    state = 'active',
    acquired_at = now(),
    expires_at = excluded.expires_at,
    released_at = null,
    metadata = public.github_connector_operation_leases_v2.metadata || excluded.metadata,
    updated_at = now()
  where public.github_connector_operation_leases_v2.expires_at <= now()
     or public.github_connector_operation_leases_v2.request_id = excluded.request_id
  returning * into v_row;

  if v_row.lease_key is not null then
    return jsonb_build_object('acquired',true,'lease_key',v_row.lease_key,'request_id',v_row.request_id,'correlation_id',v_row.correlation_id,'expires_at',v_row.expires_at);
  end if;

  select * into v_row from public.github_connector_operation_leases_v2 where lease_key = p_lease_key;
  return jsonb_build_object('acquired',false,'lease_key',v_row.lease_key,'holder_request_id',v_row.request_id,'holder_actor',v_row.actor,'expires_at',v_row.expires_at,'state',v_row.state);
end;
$$;

revoke all on function public.acquire_github_connector_lease_v2(text,text,text,integer,jsonb) from public, anon, authenticated;
grant execute on function public.acquire_github_connector_lease_v2(text,text,text,integer,jsonb) to service_role;

create or replace function public.release_github_connector_lease_v2(
  p_lease_key text,
  p_request_id text,
  p_state text default 'released',
  p_metadata jsonb default '{}'::jsonb
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if p_state not in ('completed','released','failed') then raise exception 'invalid terminal lease state'; end if;
  update public.github_connector_operation_leases_v2
  set state=p_state,released_at=now(),expires_at=least(expires_at,now()),metadata=metadata || coalesce(p_metadata,'{}'::jsonb),updated_at=now()
  where lease_key=p_lease_key and request_id=p_request_id;
  return found;
end;
$$;

revoke all on function public.release_github_connector_lease_v2(text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.release_github_connector_lease_v2(text,text,text,jsonb) to service_role;

create or replace function public.enqueue_github_webhook_delivery_v1()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.signature_verified then
    insert into public.github_webhook_event_queue_v1(delivery_id,event_type,action,repository,status,metadata)
    values(new.delivery_id,new.event_type,new.action,new.repository,'pending',jsonb_build_object('delivery_payload_sha256',new.payload_sha256,'sender_login',new.sender_login,'delivery_metadata',new.metadata))
    on conflict (delivery_id) do nothing;
  end if;
  return new;
end;
$$;

revoke all on function public.enqueue_github_webhook_delivery_v1() from public, anon, authenticated;
grant execute on function public.enqueue_github_webhook_delivery_v1() to service_role;

drop trigger if exists github_webhook_delivery_enqueue_v1 on public.github_webhook_deliveries_v1;
create trigger github_webhook_delivery_enqueue_v1
after insert on public.github_webhook_deliveries_v1
for each row execute function public.enqueue_github_webhook_delivery_v1();

comment on table public.github_connector_operation_leases_v2 is 'Atomic resource leases used by the GitHub router to prevent concurrent branch/path mutation races.';
comment on table public.github_connector_route_decisions_v2 is 'Append-only routing decisions for GitHub execution, fallback, retries, preconditions, and circuit state.';
comment on table public.github_connector_circuit_v2 is 'Per-operation circuit-breaker state for the GitHub backend-ops gateway.';
comment on table public.github_webhook_event_queue_v1 is 'Durable queue populated only after a GitHub webhook delivery has passed HMAC verification.';
