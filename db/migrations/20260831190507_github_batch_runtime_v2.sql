create table if not exists public.github_batch_runs_v2 (
  batch_id uuid primary key default gen_random_uuid(),
  batch_key text not null unique,
  name text not null,
  workload_class text not null check (workload_class in ('interactive','bulk_read','audit','mutation','event_replay','mixed')),
  status text not null default 'queued' check (status in ('queued','running','completed','completed_with_errors','quality_failed','cancelled')),
  priority smallint not null default 50 check (priority between 0 and 100),
  max_concurrency smallint not null default 8 check (max_concurrency between 1 and 32),
  target_rps numeric(8,2) not null default 12 check (target_rps > 0 and target_rps <= 100),
  claim_size smallint not null default 50 check (claim_size between 1 and 100),
  total_items integer not null default 0,
  succeeded_items integer not null default 0,
  failed_items integer not null default 0,
  blocked_items integer not null default 0,
  retry_items integer not null default 0,
  quality_passed_items integer not null default 0,
  quality_failed_items integer not null default 0,
  quality_policy jsonb not null default '{"minimum_success_ratio":0.98,"require_write_readback":true,"require_no_ambiguous_outcomes":true}'::jsonb,
  quality_summary jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.github_batch_items_v2 (
  item_id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.github_batch_runs_v2(batch_id) on delete cascade,
  ordinal integer not null,
  request_id text not null unique,
  operation text not null,
  repository text not null,
  arguments jsonb not null default '{}'::jsonb,
  full_fidelity boolean not null default false,
  expected_before_sha text,
  expected_before_sha_present boolean not null default false,
  execution_lane text not null default 'backend_ops'
    check (execution_lane in ('backend_ops','github_native','desktop_commander','github_runner')),
  status text not null default 'pending'
    check (status in ('pending','running','retry','succeeded','failed','blocked','ignored','cancelled')),
  priority smallint not null default 50 check (priority between 0 and 100),
  attempts integer not null default 0,
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  available_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  payload_hash text not null,
  response_status integer,
  outcome text,
  result_summary jsonb not null default '{}'::jsonb,
  error_code text,
  quality_status text not null default 'pending'
    check (quality_status in ('pending','passed','warning','failed','not_applicable')),
  quality_detail jsonb not null default '{}'::jsonb,
  duration_ms integer,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  unique(batch_id,ordinal)
);

create table if not exists public.github_batch_receipts_v2 (
  receipt_id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.github_batch_runs_v2(batch_id),
  item_id uuid references public.github_batch_items_v2(item_id),
  receipt_type text not null check (receipt_type in (
    'batch_created','item_claimed','item_completed','item_retry','item_failed','item_blocked',
    'quality_finalized','batch_completed','batch_cancelled','worker_heartbeat'
  )),
  worker_id text,
  outcome text not null,
  payload_hash text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.github_batch_workers_v2 (
  worker_id text primary key,
  worker_type text not null check (worker_type in ('edge','desktop_commander','github_runner','external')),
  connector_key text,
  status text not null check (status in ('online','offline','draining','quarantined','source_ready')),
  max_concurrency smallint not null default 1 check (max_concurrency between 1 and 64),
  capabilities jsonb not null default '[]'::jsonb,
  last_heartbeat_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists github_batch_runs_v2_status_priority_idx
  on public.github_batch_runs_v2(status,priority,created_at);
create index if not exists github_batch_items_v2_claim_idx
  on public.github_batch_items_v2(execution_lane,status,available_at,priority,batch_id,ordinal);
create index if not exists github_batch_items_v2_batch_status_idx
  on public.github_batch_items_v2(batch_id,status);
create index if not exists github_batch_items_v2_repo_operation_idx
  on public.github_batch_items_v2(repository,operation,status);
create index if not exists github_batch_receipts_v2_batch_created_idx
  on public.github_batch_receipts_v2(batch_id,created_at desc);

alter table public.github_batch_runs_v2 enable row level security;
alter table public.github_batch_items_v2 enable row level security;
alter table public.github_batch_receipts_v2 enable row level security;
alter table public.github_batch_workers_v2 enable row level security;

revoke all on public.github_batch_runs_v2 from public,anon,authenticated;
revoke all on public.github_batch_items_v2 from public,anon,authenticated;
revoke all on public.github_batch_receipts_v2 from public,anon,authenticated;
revoke all on public.github_batch_workers_v2 from public,anon,authenticated;

grant select,insert,update on public.github_batch_runs_v2 to service_role;
grant select,insert,update on public.github_batch_items_v2 to service_role;
grant select,insert on public.github_batch_receipts_v2 to service_role;
grant select,insert,update on public.github_batch_workers_v2 to service_role;

comment on table public.github_batch_runs_v2 is
  'Service-role-only GitHub batch control plane. RLS with no client policies is intentional.';
comment on table public.github_batch_items_v2 is
  'Service-role-only GitHub batch item queue. Raw credentials are prohibited; arguments may contain bounded workload payloads.';
comment on table public.github_batch_receipts_v2 is
  'Append-only service-role-only batch evidence.';
comment on table public.github_batch_workers_v2 is
  'Worker capability/heartbeat registry. Offline/source_ready workers are never claimable.';

create or replace function public.github_batch_receipts_v2_block_mutation()
returns trigger
language plpgsql
set search_path='pg_catalog'
as $$
begin
  raise exception 'github_batch_receipts_v2 is append-only';
end;
$$;

drop trigger if exists github_batch_receipts_v2_immutable on public.github_batch_receipts_v2;
create trigger github_batch_receipts_v2_immutable
before update or delete on public.github_batch_receipts_v2
for each row execute function public.github_batch_receipts_v2_block_mutation();

create or replace function public.create_github_batch_v2(
  p_batch_key text,
  p_name text,
  p_workload_class text,
  p_items jsonb,
  p_priority integer default 50,
  p_max_concurrency integer default 8,
  p_target_rps numeric default 12,
  p_claim_size integer default 50,
  p_quality_policy jsonb default null,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','extensions','pg_temp'
as $$
declare
  v_batch_id uuid;
  v_existing public.github_batch_runs_v2%rowtype;
  v_count integer;
  v_item jsonb;
  v_ord integer := 0;
  v_operation text;
  v_repository text;
  v_args jsonb;
  v_lane text;
  v_req text;
  v_expected_present boolean;
  v_expected text;
  v_hash text;
begin
  if p_batch_key is null or length(trim(p_batch_key)) < 8 or length(p_batch_key) > 256 then
    raise exception 'invalid_batch_key';
  end if;
  if p_name is null or length(trim(p_name)) < 1 or length(p_name) > 256 then
    raise exception 'invalid_batch_name';
  end if;
  if p_workload_class not in ('interactive','bulk_read','audit','mutation','event_replay','mixed') then
    raise exception 'invalid_workload_class';
  end if;
  if p_items is null or jsonb_typeof(p_items) <> 'array' then
    raise exception 'items_must_be_array';
  end if;
  v_count := jsonb_array_length(p_items);
  if v_count < 1 or v_count > 5000 then
    raise exception 'batch_item_count_out_of_range';
  end if;

  select * into v_existing from public.github_batch_runs_v2 where batch_key=trim(p_batch_key);
  if found then
    return jsonb_build_object(
      'created',false,'idempotent_replay',true,'batch_id',v_existing.batch_id,
      'batch_key',v_existing.batch_key,'status',v_existing.status,'total_items',v_existing.total_items
    );
  end if;

  insert into public.github_batch_runs_v2(
    batch_key,name,workload_class,priority,max_concurrency,target_rps,claim_size,total_items,
    quality_policy,metadata
  ) values (
    trim(p_batch_key),trim(p_name),p_workload_class,
    greatest(0,least(p_priority,100)),
    greatest(1,least(p_max_concurrency,32)),
    greatest(0.1,least(p_target_rps,100)),
    greatest(1,least(p_claim_size,100)),
    v_count,
    coalesce(p_quality_policy,'{"minimum_success_ratio":0.98,"require_write_readback":true,"require_no_ambiguous_outcomes":true}'::jsonb),
    coalesce(p_metadata,'{}'::jsonb)
  ) returning batch_id into v_batch_id;

  for v_item in select value from jsonb_array_elements(p_items)
  loop
    v_ord := v_ord + 1;
    if jsonb_typeof(v_item) <> 'object' then raise exception 'batch_item_must_be_object'; end if;

    v_operation := nullif(trim(v_item->>'operation'),'');
    v_repository := nullif(trim(v_item->>'repository'),'');
    v_args := coalesce(v_item->'args','{}'::jsonb);

    if v_operation is null or length(v_operation)>128 then raise exception 'invalid_item_operation'; end if;
    if v_repository is null or v_repository !~ '^GlacierEQ/[A-Za-z0-9_.-]+$' then raise exception 'invalid_item_repository'; end if;
    if jsonb_typeof(v_args) <> 'object' then raise exception 'invalid_item_args'; end if;
    if octet_length(v_args::text) > 262144 then raise exception 'item_args_too_large'; end if;

    v_lane := coalesce(nullif(v_item->>'execution_lane',''),
      case
        when v_operation in ('pull.create','pull.review') then 'github_native'
        when v_operation like 'local.%' then 'desktop_commander'
        else 'backend_ops'
      end
    );
    if v_lane not in ('backend_ops','github_native','desktop_commander','github_runner') then
      raise exception 'invalid_execution_lane';
    end if;

    v_expected_present := v_item ? 'expected_before_sha';
    v_expected := case when v_expected_present then v_item->>'expected_before_sha' else null end;
    if v_operation='contents.put' and not v_expected_present then
      raise exception 'contents_put_requires_expected_before_sha';
    end if;

    v_req := coalesce(nullif(v_item->>'request_id',''),
      'batch:' || v_batch_id::text || ':' || lpad(v_ord::text,6,'0'));
    v_hash := encode(extensions.digest(convert_to(v_item::text,'UTF8'),'sha256'),'hex');

    insert into public.github_batch_items_v2(
      batch_id,ordinal,request_id,operation,repository,arguments,full_fidelity,
      expected_before_sha,expected_before_sha_present,execution_lane,status,priority,max_attempts,payload_hash
    ) values (
      v_batch_id,v_ord,v_req,v_operation,v_repository,v_args,coalesce((v_item->>'full_fidelity')::boolean,false),
      v_expected,v_expected_present,v_lane,'pending',
      greatest(0,least(coalesce((v_item->>'priority')::integer,p_priority),100)),
      greatest(1,least(coalesce((v_item->>'max_attempts')::integer,3),10)),
      v_hash
    );
  end loop;

  insert into public.github_batch_receipts_v2(batch_id,receipt_type,outcome,detail)
  values (
    v_batch_id,'batch_created','succeeded',
    jsonb_build_object('batch_key',trim(p_batch_key),'total_items',v_count,'workload_class',p_workload_class)
  );

  return jsonb_build_object(
    'created',true,'idempotent_replay',false,'batch_id',v_batch_id,
    'batch_key',trim(p_batch_key),'status','queued','total_items',v_count
  );
end;
$$;

create or replace function public.claim_github_batch_items_v2(
  p_worker_id text,
  p_execution_lane text default 'backend_ops',
  p_limit integer default 50,
  p_lease_seconds integer default 90
)
returns setof public.github_batch_items_v2
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_batch_id uuid;
  v_limit integer := greatest(1,least(p_limit,100));
begin
  if p_worker_id is null or length(trim(p_worker_id))<3 then raise exception 'invalid_worker_id'; end if;
  if p_execution_lane not in ('backend_ops','github_native','desktop_commander','github_runner') then raise exception 'invalid_execution_lane'; end if;

  select i.batch_id into v_batch_id
  from public.github_batch_items_v2 i
  join public.github_batch_runs_v2 b on b.batch_id=i.batch_id
  where i.execution_lane=p_execution_lane
    and i.status in ('pending','retry')
    and i.available_at<=now()
    and (i.lease_expires_at is null or i.lease_expires_at<now())
    and b.status in ('queued','running')
  order by b.priority desc,i.priority desc,b.created_at,i.ordinal
  limit 1;

  if v_batch_id is null then return; end if;

  update public.github_batch_runs_v2
  set status='running',started_at=coalesce(started_at,now()),updated_at=now()
  where batch_id=v_batch_id and status='queued';

  return query
  with candidates as (
    select i.item_id
    from public.github_batch_items_v2 i
    join public.github_batch_runs_v2 b on b.batch_id=i.batch_id
    where i.batch_id=v_batch_id
      and i.execution_lane=p_execution_lane
      and i.status in ('pending','retry')
      and i.available_at<=now()
      and (i.lease_expires_at is null or i.lease_expires_at<now())
    order by i.priority desc,i.ordinal
    for update of i skip locked
    limit least(v_limit,(select claim_size from public.github_batch_runs_v2 where batch_id=v_batch_id))
  ),
  claimed as (
    update public.github_batch_items_v2 i
    set status='running',
        attempts=i.attempts+1,
        lease_owner=p_worker_id,
        lease_expires_at=now()+make_interval(secs=>greatest(15,least(p_lease_seconds,600))),
        started_at=coalesce(i.started_at,now()),
        updated_at=now()
    from candidates c
    where i.item_id=c.item_id
    returning i.*
  )
  select * from claimed order by ordinal;
end;
$$;

create or replace function public.finish_github_batch_item_v2(
  p_item_id uuid,
  p_worker_id text,
  p_status text,
  p_response_status integer default null,
  p_outcome text default null,
  p_result_summary jsonb default '{}'::jsonb,
  p_error_code text default null,
  p_quality_status text default 'not_applicable',
  p_quality_detail jsonb default '{}'::jsonb,
  p_duration_ms integer default null,
  p_retry_after_seconds integer default null
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_item public.github_batch_items_v2%rowtype;
  v_receipt_type text;
begin
  if p_status not in ('succeeded','failed','blocked','ignored','retry','cancelled') then raise exception 'invalid_item_status'; end if;
  if p_quality_status not in ('pending','passed','warning','failed','not_applicable') then raise exception 'invalid_quality_status'; end if;

  update public.github_batch_items_v2
  set status=p_status,
      response_status=p_response_status,
      outcome=p_outcome,
      result_summary=coalesce(p_result_summary,'{}'::jsonb),
      error_code=p_error_code,
      quality_status=p_quality_status,
      quality_detail=coalesce(p_quality_detail,'{}'::jsonb),
      duration_ms=p_duration_ms,
      available_at=case when p_status='retry'
        then now()+make_interval(secs=>greatest(1,least(coalesce(p_retry_after_seconds,30),3600)))
        else available_at end,
      lease_owner=null,
      lease_expires_at=null,
      completed_at=case when p_status in ('succeeded','failed','blocked','ignored','cancelled') then now() else null end,
      updated_at=now()
  where item_id=p_item_id
    and status='running'
    and lease_owner=p_worker_id
  returning * into v_item;

  if not found then raise exception 'item_not_owned_or_not_running'; end if;

  v_receipt_type := case p_status
    when 'succeeded' then 'item_completed'
    when 'retry' then 'item_retry'
    when 'blocked' then 'item_blocked'
    else 'item_failed'
  end;

  insert into public.github_batch_receipts_v2(
    batch_id,item_id,receipt_type,worker_id,outcome,payload_hash,detail
  ) values (
    v_item.batch_id,v_item.item_id,v_receipt_type,p_worker_id,coalesce(p_outcome,p_status),v_item.payload_hash,
    jsonb_build_object(
      'operation',v_item.operation,'repository',v_item.repository,'response_status',p_response_status,
      'quality_status',p_quality_status,'error_code',p_error_code,'attempts',v_item.attempts,
      'duration_ms',p_duration_ms
    )
  );

  return jsonb_build_object('item_id',v_item.item_id,'batch_id',v_item.batch_id,'status',p_status,'attempts',v_item.attempts);
end;
$$;

create or replace function public.heartbeat_github_batch_worker_v2(
  p_worker_id text,p_worker_type text,p_connector_key text,p_status text,
  p_max_concurrency integer,p_capabilities jsonb,p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
begin
  if p_worker_type not in ('edge','desktop_commander','github_runner','external') then raise exception 'invalid_worker_type'; end if;
  if p_status not in ('online','offline','draining','quarantined','source_ready') then raise exception 'invalid_worker_status'; end if;
  if jsonb_typeof(coalesce(p_capabilities,'[]'::jsonb)) <> 'array' then raise exception 'capabilities_must_be_array'; end if;

  insert into public.github_batch_workers_v2(worker_id,worker_type,connector_key,status,max_concurrency,capabilities,last_heartbeat_at,metadata,updated_at)
  values (p_worker_id,p_worker_type,p_connector_key,p_status,greatest(1,least(p_max_concurrency,64)),p_capabilities,
          case when p_status='online' then now() else null end,coalesce(p_metadata,'{}'::jsonb),now())
  on conflict(worker_id) do update set
    worker_type=excluded.worker_type,connector_key=excluded.connector_key,status=excluded.status,
    max_concurrency=excluded.max_concurrency,capabilities=excluded.capabilities,
    last_heartbeat_at=case when excluded.status='online' then now() else public.github_batch_workers_v2.last_heartbeat_at end,
    metadata=public.github_batch_workers_v2.metadata||excluded.metadata,updated_at=now();

  return jsonb_build_object('worker_id',p_worker_id,'status',p_status);
end;
$$;

revoke all on function public.create_github_batch_v2(text,text,text,jsonb,integer,integer,numeric,integer,jsonb,jsonb) from public,anon,authenticated;
revoke all on function public.claim_github_batch_items_v2(text,text,integer,integer) from public,anon,authenticated;
revoke all on function public.finish_github_batch_item_v2(uuid,text,text,integer,text,jsonb,text,text,jsonb,integer,integer) from public,anon,authenticated;
revoke all on function public.heartbeat_github_batch_worker_v2(text,text,text,text,integer,jsonb,jsonb) from public,anon,authenticated;

grant execute on function public.create_github_batch_v2(text,text,text,jsonb,integer,integer,numeric,integer,jsonb,jsonb) to service_role;
grant execute on function public.claim_github_batch_items_v2(text,text,integer,integer) to service_role;
grant execute on function public.finish_github_batch_item_v2(uuid,text,text,integer,text,jsonb,text,text,jsonb,integer,integer) to service_role;
grant execute on function public.heartbeat_github_batch_worker_v2(text,text,text,text,integer,jsonb,jsonb) to service_role;

insert into public.github_batch_workers_v2(
  worker_id,worker_type,connector_key,status,max_concurrency,capabilities,last_heartbeat_at,metadata
) values
  ('github-edge-batch-v2','edge','github.backend_ops','online',16,
   '["repo.get","contents.get","tree.list","branches.list","commits.list","code.search","issues.list","issue.get","pulls.list","pull.get","actions.runs","branch.create","contents.put","issue.create","issue.comment","pull.comment","workflow.dispatch"]'::jsonb,
   now(),'{"lane":"backend_ops","runtime":"supabase_edge"}'::jsonb),
  ('glacier-desktop-commander','desktop_commander','desktop_commander.glacier','source_ready',8,
   '["local.read","local.search","local.test","local.build","local.scan","local.edit"]'::jsonb,
   null,'{"repository":"GlacierEQ/UDC","live_endpoint":false,"selection_enabled":false}'::jsonb),
  ('github-key-runner','github_runner','github.runner','offline',8,
   '["repo.test","repo.build","workflow.execute"]'::jsonb,
   null,'{"bound_sessions":0,"selection_enabled":false}'::jsonb)
on conflict(worker_id) do update set
  worker_type=excluded.worker_type,connector_key=excluded.connector_key,status=excluded.status,
  max_concurrency=excluded.max_concurrency,capabilities=excluded.capabilities,
  last_heartbeat_at=excluded.last_heartbeat_at,metadata=public.github_batch_workers_v2.metadata||excluded.metadata,updated_at=now();
