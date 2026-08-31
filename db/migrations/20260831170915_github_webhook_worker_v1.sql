create table if not exists public.github_webhook_event_results_v1 (
  result_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.github_webhook_event_queue_v1(event_id) on delete cascade,
  delivery_id text not null,
  repository text,
  operation text not null,
  response_status integer,
  outcome text not null check (outcome in ('succeeded','failed','skipped')),
  result_summary jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists github_webhook_event_results_v1_event_idx
  on public.github_webhook_event_results_v1(event_id, created_at);
create index if not exists github_webhook_event_results_v1_repo_idx
  on public.github_webhook_event_results_v1(repository, created_at desc);

alter table public.github_webhook_event_results_v1 enable row level security;
revoke all on public.github_webhook_event_results_v1 from public, anon, authenticated;
grant select, insert on public.github_webhook_event_results_v1 to service_role;

create or replace function public.github_webhook_event_results_v1_block_mutation()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  raise exception 'github_webhook_event_results_v1 is append-only';
end;
$$;

revoke all on function public.github_webhook_event_results_v1_block_mutation() from public, anon, authenticated;
grant execute on function public.github_webhook_event_results_v1_block_mutation() to service_role;

drop trigger if exists github_webhook_event_results_v1_immutable on public.github_webhook_event_results_v1;
create trigger github_webhook_event_results_v1_immutable
before update or delete on public.github_webhook_event_results_v1
for each row execute function public.github_webhook_event_results_v1_block_mutation();

create or replace function public.claim_github_webhook_events_v1(p_limit integer default 10)
returns setof public.github_webhook_event_queue_v1
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if p_limit < 1 or p_limit > 50 then raise exception 'invalid claim limit'; end if;
  return query
  with candidates as (
    select q.event_id
    from public.github_webhook_event_queue_v1 q
    where q.status='pending' and q.available_at <= now()
    order by q.created_at
    for update skip locked
    limit p_limit
  )
  update public.github_webhook_event_queue_v1 q
  set status='processing',attempts=q.attempts+1,locked_at=now(),updated_at=now()
  from candidates c
  where q.event_id=c.event_id
  returning q.*;
end;
$$;

revoke all on function public.claim_github_webhook_events_v1(integer) from public, anon, authenticated;
grant execute on function public.claim_github_webhook_events_v1(integer) to service_role;

create or replace function public.finish_github_webhook_event_v1(
  p_event_id uuid,
  p_status text,
  p_last_error text default null,
  p_metadata jsonb default '{}'::jsonb,
  p_retry_after_seconds integer default null
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if p_status not in ('completed','failed','ignored','pending') then raise exception 'invalid event status'; end if;
  update public.github_webhook_event_queue_v1
  set status=p_status,
      last_error=p_last_error,
      available_at=case when p_status='pending' and p_retry_after_seconds is not null then now()+make_interval(secs => greatest(1,least(p_retry_after_seconds,3600))) else available_at end,
      locked_at=null,
      processed_at=case when p_status in ('completed','failed','ignored') then now() else null end,
      metadata=metadata || coalesce(p_metadata,'{}'::jsonb),
      updated_at=now()
  where event_id=p_event_id;
  return found;
end;
$$;

revoke all on function public.finish_github_webhook_event_v1(uuid,text,text,jsonb,integer) from public, anon, authenticated;
grant execute on function public.finish_github_webhook_event_v1(uuid,text,text,jsonb,integer) to service_role;

comment on table public.github_webhook_event_results_v1 is 'Append-only bounded results generated when verified GitHub webhook events are processed through the GitHub router.';
