create table if not exists public.desktop_commander_devices_v1 (
  device_id uuid primary key default gen_random_uuid(),
  device_key text not null unique,
  connector_key text not null default 'desktop_commander.glacier',
  status text not null default 'pending'
    check (status in ('pending','approved','suspended','revoked')),
  public_key_spki_base64 text not null,
  public_key_sha256 text not null,
  host_fingerprint_sha256 text not null,
  platform text not null,
  hostname_hash text,
  agent_version text,
  capabilities jsonb not null default '[]'::jsonb,
  requested_roots jsonb not null default '[]'::jsonb,
  approved_roots jsonb not null default '[]'::jsonb,
  last_heartbeat_at timestamptz,
  enrolled_at timestamptz not null default now(),
  approved_at timestamptz,
  revoked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  check (jsonb_typeof(capabilities)='array'),
  check (jsonb_typeof(requested_roots)='array'),
  check (jsonb_typeof(approved_roots)='array')
);

create table if not exists public.desktop_commander_jobs_v1 (
  job_id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  target_device_id uuid references public.desktop_commander_devices_v1(device_id),
  operation text not null,
  mutation_class text not null
    check (mutation_class in ('read','test','build','scan','edit')),
  arguments jsonb not null default '{}'::jsonb,
  status text not null default 'queued'
    check (status in ('queued','claimed','completed','failed','cancelled')),
  priority smallint not null default 50 check (priority between 0 and 100),
  attempts integer not null default 0,
  max_attempts integer not null default 3 check (max_attempts between 1 and 5),
  available_at timestamptz not null default now(),
  lease_device_id uuid references public.desktop_commander_devices_v1(device_id),
  lease_expires_at timestamptz,
  input_hash text not null,
  result_summary jsonb not null default '{}'::jsonb,
  result_hash text,
  error_code text,
  error_detail jsonb not null default '{}'::jsonb,
  duration_ms integer,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.desktop_commander_receipts_v1 (
  receipt_id uuid primary key default gen_random_uuid(),
  device_id uuid references public.desktop_commander_devices_v1(device_id),
  job_id uuid references public.desktop_commander_jobs_v1(job_id),
  receipt_type text not null
    check (receipt_type in (
      'enrollment_requested','device_approved','heartbeat',
      'job_enqueued','job_claimed','job_completed','job_failed','job_cancelled'
    )),
  outcome text not null,
  payload_hash text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.desktop_commander_nonces_v1 (
  device_id uuid not null references public.desktop_commander_devices_v1(device_id) on delete cascade,
  nonce text not null,
  used_at timestamptz not null default now(),
  primary key(device_id,nonce)
);

create index if not exists desktop_commander_jobs_claim_idx
  on public.desktop_commander_jobs_v1(status,available_at,priority desc,created_at)
  where status='queued';
create index if not exists desktop_commander_jobs_target_idx
  on public.desktop_commander_jobs_v1(target_device_id,status,available_at);
create index if not exists desktop_commander_receipts_device_idx
  on public.desktop_commander_receipts_v1(device_id,created_at desc);
create index if not exists desktop_commander_receipts_job_idx
  on public.desktop_commander_receipts_v1(job_id,created_at desc)
  where job_id is not null;
create index if not exists desktop_commander_devices_heartbeat_idx
  on public.desktop_commander_devices_v1(status,last_heartbeat_at desc);

alter table public.desktop_commander_devices_v1 enable row level security;
alter table public.desktop_commander_jobs_v1 enable row level security;
alter table public.desktop_commander_receipts_v1 enable row level security;
alter table public.desktop_commander_nonces_v1 enable row level security;

revoke all on public.desktop_commander_devices_v1 from public,anon,authenticated;
revoke all on public.desktop_commander_jobs_v1 from public,anon,authenticated;
revoke all on public.desktop_commander_receipts_v1 from public,anon,authenticated;
revoke all on public.desktop_commander_nonces_v1 from public,anon,authenticated;

grant select,insert,update on public.desktop_commander_devices_v1 to service_role;
grant select,insert,update on public.desktop_commander_jobs_v1 to service_role;
grant select,insert on public.desktop_commander_receipts_v1 to service_role;
grant select,insert,delete on public.desktop_commander_nonces_v1 to service_role;

create or replace function public.desktop_commander_receipts_v1_block_mutation()
returns trigger
language plpgsql
set search_path='pg_catalog'
as $$
begin
  raise exception 'desktop_commander_receipts_v1 is append-only';
end;
$$;

drop trigger if exists desktop_commander_receipts_v1_immutable on public.desktop_commander_receipts_v1;
create trigger desktop_commander_receipts_v1_immutable
before update or delete on public.desktop_commander_receipts_v1
for each row execute function public.desktop_commander_receipts_v1_block_mutation();

do $$
begin
  if not exists (
    select 1 from vault.secrets where name='desktop_commander_enrollment_token_v1'
  ) then
    perform vault.create_secret(
      encode(gen_random_bytes(32),'hex'),
      'desktop_commander_enrollment_token_v1',
      'One-time/bootstrap enrollment credential for Glacier Desktop Commander local-agent bridge.'
    );
  end if;
end;
$$;

create or replace function public.validate_desktop_commander_enrollment_token_v1(p_candidate text)
returns boolean
language sql
security definer
set search_path='public','vault','extensions','pg_temp'
as $$
  select exists(
    select 1
    from vault.decrypted_secrets
    where name='desktop_commander_enrollment_token_v1'
      and encode(extensions.digest(convert_to(decrypted_secret,'UTF8'),'sha256'),'hex')
        = encode(extensions.digest(convert_to(coalesce(p_candidate,''),'UTF8'),'sha256'),'hex')
  );
$$;

revoke all on function public.validate_desktop_commander_enrollment_token_v1(text)
  from public,anon,authenticated;
grant execute on function public.validate_desktop_commander_enrollment_token_v1(text)
  to service_role;

create or replace function public.register_desktop_commander_device_v1(
  p_device_key text,
  p_public_key_spki_base64 text,
  p_public_key_sha256 text,
  p_host_fingerprint_sha256 text,
  p_platform text,
  p_hostname_hash text,
  p_agent_version text,
  p_capabilities jsonb,
  p_requested_roots jsonb,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_device public.desktop_commander_devices_v1%rowtype;
begin
  if p_device_key is null or p_device_key !~ '^[A-Za-z0-9._:-]{8,128}$' then
    raise exception 'invalid_device_key';
  end if;
  if p_public_key_spki_base64 is null or length(p_public_key_spki_base64) < 40 then
    raise exception 'invalid_public_key';
  end if;
  if p_public_key_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_public_key_hash';
  end if;
  if p_host_fingerprint_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_host_fingerprint';
  end if;
  if jsonb_typeof(coalesce(p_capabilities,'[]'::jsonb)) <> 'array'
     or jsonb_typeof(coalesce(p_requested_roots,'[]'::jsonb)) <> 'array' then
    raise exception 'invalid_device_arrays';
  end if;

  insert into public.desktop_commander_devices_v1(
    device_key,public_key_spki_base64,public_key_sha256,host_fingerprint_sha256,
    platform,hostname_hash,agent_version,capabilities,requested_roots,metadata,updated_at
  ) values (
    p_device_key,p_public_key_spki_base64,p_public_key_sha256,p_host_fingerprint_sha256,
    left(p_platform,64),left(p_hostname_hash,128),left(p_agent_version,64),
    coalesce(p_capabilities,'[]'::jsonb),coalesce(p_requested_roots,'[]'::jsonb),
    coalesce(p_metadata,'{}'::jsonb),now()
  )
  on conflict(device_key) do update set
    public_key_spki_base64=excluded.public_key_spki_base64,
    public_key_sha256=excluded.public_key_sha256,
    host_fingerprint_sha256=excluded.host_fingerprint_sha256,
    platform=excluded.platform,
    hostname_hash=excluded.hostname_hash,
    agent_version=excluded.agent_version,
    capabilities=excluded.capabilities,
    requested_roots=excluded.requested_roots,
    metadata=public.desktop_commander_devices_v1.metadata||excluded.metadata,
    updated_at=now()
  returning * into v_device;

  insert into public.desktop_commander_receipts_v1(
    device_id,receipt_type,outcome,payload_hash,detail
  ) values (
    v_device.device_id,'enrollment_requested','pending',p_host_fingerprint_sha256,
    jsonb_build_object(
      'device_key',v_device.device_key,
      'public_key_sha256',v_device.public_key_sha256,
      'platform',v_device.platform,
      'agent_version',v_device.agent_version
    )
  );

  return jsonb_build_object(
    'device_id',v_device.device_id,
    'device_key',v_device.device_key,
    'status',v_device.status,
    'public_key_sha256',v_device.public_key_sha256
  );
end;
$$;

revoke all on function public.register_desktop_commander_device_v1(
  text,text,text,text,text,text,text,jsonb,jsonb,jsonb
) from public,anon,authenticated;
grant execute on function public.register_desktop_commander_device_v1(
  text,text,text,text,text,text,text,jsonb,jsonb,jsonb
) to service_role;

create or replace function public.approve_desktop_commander_device_v1(
  p_device_id uuid,
  p_approved_roots jsonb,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_device public.desktop_commander_devices_v1%rowtype;
begin
  if jsonb_typeof(coalesce(p_approved_roots,'[]'::jsonb)) <> 'array'
     or jsonb_array_length(coalesce(p_approved_roots,'[]'::jsonb)) < 1 then
    raise exception 'approved_roots_required';
  end if;

  update public.desktop_commander_devices_v1
  set status='approved',
      approved_roots=p_approved_roots,
      approved_at=now(),
      revoked_at=null,
      metadata=metadata||coalesce(p_metadata,'{}'::jsonb),
      updated_at=now()
  where device_id=p_device_id
    and status in ('pending','suspended','approved')
  returning * into v_device;

  if not found then raise exception 'device_not_approvable'; end if;

  insert into public.desktop_commander_receipts_v1(
    device_id,receipt_type,outcome,detail
  ) values (
    v_device.device_id,'device_approved','approved',
    jsonb_build_object(
      'device_key',v_device.device_key,
      'approved_roots',v_device.approved_roots
    )
  );

  return jsonb_build_object(
    'device_id',v_device.device_id,
    'status',v_device.status,
    'approved_roots',v_device.approved_roots
  );
end;
$$;

revoke all on function public.approve_desktop_commander_device_v1(uuid,jsonb,jsonb)
  from public,anon,authenticated;
grant execute on function public.approve_desktop_commander_device_v1(uuid,jsonb,jsonb)
  to service_role;

create or replace function public.claim_desktop_commander_jobs_v1(
  p_device_id uuid,
  p_limit integer default 4,
  p_lease_seconds integer default 120
)
returns setof public.desktop_commander_jobs_v1
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_device public.desktop_commander_devices_v1%rowtype;
begin
  select * into v_device
  from public.desktop_commander_devices_v1
  where device_id=p_device_id
  for update;

  if not found or v_device.status <> 'approved' then
    raise exception 'device_not_approved';
  end if;

  update public.desktop_commander_devices_v1
  set last_heartbeat_at=now(),updated_at=now()
  where device_id=p_device_id;

  return query
  with candidates as (
    select j.job_id
    from public.desktop_commander_jobs_v1 j
    where j.status='queued'
      and j.available_at<=now()
      and (j.target_device_id is null or j.target_device_id=p_device_id)
      and (j.lease_expires_at is null or j.lease_expires_at<now())
    order by j.priority desc,j.created_at,j.job_id
    for update skip locked
    limit greatest(1,least(coalesce(p_limit,4),16))
  ),
  claimed as (
    update public.desktop_commander_jobs_v1 j
    set status='claimed',
        attempts=j.attempts+1,
        lease_device_id=p_device_id,
        lease_expires_at=now()+make_interval(secs=>greatest(30,least(coalesce(p_lease_seconds,120),600))),
        started_at=coalesce(j.started_at,now()),
        updated_at=now()
    from candidates c
    where j.job_id=c.job_id
    returning j.*
  )
  select * from claimed;
end;
$$;

revoke all on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  from public,anon,authenticated;
grant execute on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  to service_role;

create or replace function public.finish_desktop_commander_job_v1(
  p_job_id uuid,
  p_device_id uuid,
  p_status text,
  p_result_summary jsonb default '{}'::jsonb,
  p_result_hash text default null,
  p_error_code text default null,
  p_error_detail jsonb default '{}'::jsonb,
  p_duration_ms integer default null
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_job public.desktop_commander_jobs_v1%rowtype;
  v_receipt_type text;
begin
  if p_status not in ('completed','failed') then
    raise exception 'invalid_job_terminal_status';
  end if;

  update public.desktop_commander_jobs_v1
  set status=p_status,
      result_summary=coalesce(p_result_summary,'{}'::jsonb),
      result_hash=p_result_hash,
      error_code=p_error_code,
      error_detail=coalesce(p_error_detail,'{}'::jsonb),
      duration_ms=p_duration_ms,
      completed_at=now(),
      lease_expires_at=null,
      updated_at=now()
  where job_id=p_job_id
    and status='claimed'
    and lease_device_id=p_device_id
  returning * into v_job;

  if not found then raise exception 'job_not_owned_by_device'; end if;

  v_receipt_type:=case when p_status='completed' then 'job_completed' else 'job_failed' end;

  insert into public.desktop_commander_receipts_v1(
    device_id,job_id,receipt_type,outcome,payload_hash,detail
  ) values (
    p_device_id,p_job_id,v_receipt_type,p_status,p_result_hash,
    jsonb_build_object(
      'operation',v_job.operation,
      'mutation_class',v_job.mutation_class,
      'duration_ms',p_duration_ms,
      'error_code',p_error_code
    )
  );

  return jsonb_build_object(
    'job_id',v_job.job_id,
    'status',v_job.status,
    'attempts',v_job.attempts
  );
end;
$$;

revoke all on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) from public,anon,authenticated;
grant execute on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) to service_role;

comment on table public.desktop_commander_devices_v1 is
  'Approved local Glacier Desktop Commander device identities. Private keys never enter Supabase.';
comment on table public.desktop_commander_jobs_v1 is
  'Durable local-agent work queue, separate from GitHub batch semantics.';
comment on table public.desktop_commander_receipts_v1 is
  'Append-only evidence for Desktop Commander enrollment, heartbeat, claim, and terminal job outcomes.';
