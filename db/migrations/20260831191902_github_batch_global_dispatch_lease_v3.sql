create table if not exists public.github_batch_dispatch_leases_v2 (
  lease_key text primary key,
  lease_owner text not null,
  lease_expires_at timestamptz not null,
  acquired_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

alter table public.github_batch_dispatch_leases_v2 enable row level security;
revoke all on public.github_batch_dispatch_leases_v2 from public,anon,authenticated;
grant select,insert,update,delete on public.github_batch_dispatch_leases_v2 to service_role;

create or replace function public.acquire_github_batch_dispatch_lease_v2(
  p_lease_key text,p_lease_owner text,p_ttl_seconds integer default 55,p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare v_row public.github_batch_dispatch_leases_v2%rowtype;
begin
  if p_lease_key is null or length(trim(p_lease_key))<3 then raise exception 'invalid_lease_key'; end if;
  if p_lease_owner is null or length(trim(p_lease_owner))<8 then raise exception 'invalid_lease_owner'; end if;

  perform pg_advisory_xact_lock(hashtext('github_batch_dispatch:'||p_lease_key));

  select * into v_row from public.github_batch_dispatch_leases_v2 where lease_key=p_lease_key for update;

  if found and v_row.lease_expires_at>now() and v_row.lease_owner<>p_lease_owner then
    return jsonb_build_object(
      'acquired',false,'lease_key',p_lease_key,'lease_owner',v_row.lease_owner,
      'lease_expires_at',v_row.lease_expires_at
    );
  end if;

  insert into public.github_batch_dispatch_leases_v2(
    lease_key,lease_owner,lease_expires_at,acquired_at,updated_at,metadata
  ) values (
    p_lease_key,p_lease_owner,now()+make_interval(secs=>greatest(10,least(p_ttl_seconds,120))),
    now(),now(),coalesce(p_metadata,'{}'::jsonb)
  )
  on conflict(lease_key) do update set
    lease_owner=excluded.lease_owner,lease_expires_at=excluded.lease_expires_at,
    acquired_at=now(),updated_at=now(),
    metadata=public.github_batch_dispatch_leases_v2.metadata||excluded.metadata
  returning * into v_row;

  return jsonb_build_object(
    'acquired',true,'lease_key',v_row.lease_key,'lease_owner',v_row.lease_owner,
    'lease_expires_at',v_row.lease_expires_at
  );
end;
$$;

create or replace function public.release_github_batch_dispatch_lease_v2(
  p_lease_key text,p_lease_owner text,p_metadata jsonb default '{}'::jsonb
)
returns boolean
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
begin
  update public.github_batch_dispatch_leases_v2
  set lease_expires_at=now(),updated_at=now(),metadata=metadata||coalesce(p_metadata,'{}'::jsonb)
  where lease_key=p_lease_key and lease_owner=p_lease_owner;
  return found;
end;
$$;

revoke all on function public.acquire_github_batch_dispatch_lease_v2(text,text,integer,jsonb) from public,anon,authenticated;
revoke all on function public.release_github_batch_dispatch_lease_v2(text,text,jsonb) from public,anon,authenticated;
grant execute on function public.acquire_github_batch_dispatch_lease_v2(text,text,integer,jsonb) to service_role;
grant execute on function public.release_github_batch_dispatch_lease_v2(text,text,jsonb) to service_role;

comment on table public.github_batch_dispatch_leases_v2 is
  'Global batch dispatcher lease. Prevents overlapping Edge worker invocations from multiplying internal concurrency.';
