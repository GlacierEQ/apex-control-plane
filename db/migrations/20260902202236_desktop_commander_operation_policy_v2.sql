create table if not exists public.desktop_commander_operation_policy_v1 (
  operation text primary key,
  mutation_class text not null check (mutation_class in ('read','test','build','scan','edit')),
  enabled boolean not null default true,
  requires_approved_root boolean not null default true,
  requires_expected_before_sha boolean not null default false,
  max_argument_bytes integer not null default 262144 check (max_argument_bytes between 1024 and 1048576),
  max_result_bytes integer not null default 524288 check (max_result_bytes between 1024 and 4194304),
  description text not null,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.desktop_commander_operation_policy_v1 enable row level security;
revoke all on public.desktop_commander_operation_policy_v1 from public,anon,authenticated;
grant select,insert,update on public.desktop_commander_operation_policy_v1 to service_role;

insert into public.desktop_commander_operation_policy_v1(
  operation,mutation_class,enabled,requires_approved_root,requires_expected_before_sha,
  max_argument_bytes,max_result_bytes,description,metadata
) values
  ('read_file','read',true,true,false,65536,1048576,'Read one UTF-8 file under an approved root.','{}'),
  ('read_multiple_files','read',true,true,false,65536,2097152,'Read multiple UTF-8 files under approved roots.','{"max_files":20}'),
  ('list_directory','read',true,true,false,32768,524288,'List one directory under an approved root.','{}'),
  ('search_files','read',true,true,false,32768,1048576,'Search filenames under an approved root.','{}'),
  ('get_file_info','read',true,true,false,32768,131072,'Read file metadata under an approved root.','{}'),
  ('write_file','edit',true,true,true,1048576,262144,'Replace a file under an approved root with compare-before-write.','{"destructive":false,"precondition":"expected_before_sha"}'),
  ('edit_block','edit',true,true,true,1048576,262144,'Apply one search/replace block under an approved root with compare-before-write.','{"destructive":false,"precondition":"expected_before_sha"}'),
  ('run_profile','test',true,true,false,65536,1048576,'Run a fixed diagnostic/test/build profile in an approved working directory.','{"profiles":["git_status","git_diff","test","build","lint","typecheck"]}')
on conflict(operation) do update set
  mutation_class=excluded.mutation_class,
  enabled=excluded.enabled,
  requires_approved_root=excluded.requires_approved_root,
  requires_expected_before_sha=excluded.requires_expected_before_sha,
  max_argument_bytes=excluded.max_argument_bytes,
  max_result_bytes=excluded.max_result_bytes,
  description=excluded.description,
  metadata=excluded.metadata,
  updated_at=now();

create or replace function public.enqueue_desktop_commander_job_v1(
  p_idempotency_key text,
  p_operation text,
  p_arguments jsonb,
  p_target_device_id uuid default null,
  p_priority integer default 50,
  p_max_attempts integer default 3
)
returns jsonb
language plpgsql
security definer
set search_path='public','extensions','pg_temp'
as $$
declare
  v_policy public.desktop_commander_operation_policy_v1%rowtype;
  v_existing public.desktop_commander_jobs_v1%rowtype;
  v_job public.desktop_commander_jobs_v1%rowtype;
  v_hash text;
  v_bytes integer;
  v_expected text;
begin
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8
     or length(p_idempotency_key)>256 then
    raise exception 'invalid_idempotency_key';
  end if;

  select * into v_existing
  from public.desktop_commander_jobs_v1
  where idempotency_key=trim(p_idempotency_key);

  if found then
    return jsonb_build_object(
      'created',false,'idempotent_replay',true,
      'job_id',v_existing.job_id,'status',v_existing.status
    );
  end if;

  select * into v_policy
  from public.desktop_commander_operation_policy_v1
  where operation=p_operation and enabled=true;

  if not found then raise exception 'desktop_commander_operation_not_allowed'; end if;
  if jsonb_typeof(coalesce(p_arguments,'{}'::jsonb)) <> 'object' then
    raise exception 'arguments_must_be_object';
  end if;

  v_bytes:=octet_length(coalesce(p_arguments,'{}'::jsonb)::text);
  if v_bytes > v_policy.max_argument_bytes then raise exception 'arguments_too_large'; end if;

  if v_policy.requires_expected_before_sha then
    v_expected:=nullif(p_arguments->>'expected_before_sha','');
    if v_expected is null or v_expected !~ '^[0-9a-f]{64}$' then
      raise exception 'expected_before_sha_required';
    end if;
  end if;

  if p_operation='run_profile'
     and coalesce(p_arguments->>'profile','') not in
       ('git_status','git_diff','test','build','lint','typecheck') then
    raise exception 'invalid_run_profile';
  end if;

  if p_target_device_id is not null and not exists(
    select 1 from public.desktop_commander_devices_v1
    where device_id=p_target_device_id and status='approved'
  ) then
    raise exception 'target_device_not_approved';
  end if;

  v_hash:=encode(
    extensions.digest(
      convert_to(jsonb_build_object(
        'operation',p_operation,
        'arguments',coalesce(p_arguments,'{}'::jsonb),
        'target_device_id',p_target_device_id
      )::text,'UTF8'),
      'sha256'
    ),
    'hex'
  );

  insert into public.desktop_commander_jobs_v1(
    idempotency_key,target_device_id,operation,mutation_class,arguments,status,
    priority,max_attempts,input_hash
  ) values (
    trim(p_idempotency_key),p_target_device_id,p_operation,v_policy.mutation_class,
    coalesce(p_arguments,'{}'::jsonb),'queued',
    greatest(0,least(p_priority,100)),
    greatest(1,least(p_max_attempts,5)),
    v_hash
  )
  returning * into v_job;

  insert into public.desktop_commander_receipts_v1(
    device_id,job_id,receipt_type,outcome,payload_hash,detail
  ) values (
    p_target_device_id,v_job.job_id,'job_enqueued','queued',v_hash,
    jsonb_build_object(
      'operation',v_job.operation,
      'mutation_class',v_job.mutation_class,
      'priority',v_job.priority,
      'targeted',p_target_device_id is not null
    )
  );

  return jsonb_build_object(
    'created',true,'idempotent_replay',false,
    'job_id',v_job.job_id,'status',v_job.status,
    'operation',v_job.operation,'mutation_class',v_job.mutation_class,
    'input_hash',v_job.input_hash
  );
end;
$$;

revoke all on function public.enqueue_desktop_commander_job_v1(
  text,text,jsonb,uuid,integer,integer
) from public,anon,authenticated;
grant execute on function public.enqueue_desktop_commander_job_v1(
  text,text,jsonb,uuid,integer,integer
) to service_role;

comment on table public.desktop_commander_operation_policy_v1 is
  'Explicit remote-operation surface for Glacier Desktop Commander. Local MCP capabilities remain separate and may be broader.';
comment on function public.enqueue_desktop_commander_job_v1(text,text,jsonb,uuid,integer,integer) is
  'Service-role-only idempotent remote-job enqueue. Rejects unapproved operations and requires compare-before-write hashes for edits.';
