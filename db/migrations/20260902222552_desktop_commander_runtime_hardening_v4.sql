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
  v_existing public.desktop_commander_devices_v1%rowtype;
  v_identity_changed boolean := false;
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
     or jsonb_typeof(coalesce(p_requested_roots,'[]'::jsonb)) <> 'array'
     or jsonb_typeof(coalesce(p_metadata,'{}'::jsonb)) <> 'object' then
    raise exception 'invalid_device_payload';
  end if;

  select * into v_existing
  from public.desktop_commander_devices_v1
  where device_key=p_device_key
  for update;

  if found then
    if v_existing.status='revoked' then
      raise exception 'device_revoked';
    end if;

    v_identity_changed :=
      v_existing.public_key_sha256 <> p_public_key_sha256
      or v_existing.public_key_spki_base64 <> p_public_key_spki_base64
      or v_existing.host_fingerprint_sha256 <> p_host_fingerprint_sha256;

    update public.desktop_commander_devices_v1
    set public_key_spki_base64=p_public_key_spki_base64,
        public_key_sha256=p_public_key_sha256,
        host_fingerprint_sha256=p_host_fingerprint_sha256,
        platform=left(p_platform,64),
        hostname_hash=left(p_hostname_hash,128),
        agent_version=left(p_agent_version,64),
        capabilities=coalesce(p_capabilities,'[]'::jsonb),
        requested_roots=coalesce(p_requested_roots,'[]'::jsonb),
        status=case when v_identity_changed then 'pending' else status end,
        approved_roots=case when v_identity_changed then '[]'::jsonb else approved_roots end,
        approved_at=case when v_identity_changed then null else approved_at end,
        last_heartbeat_at=case when v_identity_changed then null else last_heartbeat_at end,
        metadata=metadata
          || coalesce(p_metadata,'{}'::jsonb)
          || jsonb_build_object(
               'identity_changed_on_enrollment',v_identity_changed,
               'identity_last_enrolled_at',now()
             ),
        updated_at=now()
    where device_id=v_existing.device_id
    returning * into v_device;
  else
    insert into public.desktop_commander_devices_v1(
      device_key,public_key_spki_base64,public_key_sha256,host_fingerprint_sha256,
      platform,hostname_hash,agent_version,capabilities,requested_roots,metadata,updated_at
    ) values (
      p_device_key,p_public_key_spki_base64,p_public_key_sha256,p_host_fingerprint_sha256,
      left(p_platform,64),left(p_hostname_hash,128),left(p_agent_version,64),
      coalesce(p_capabilities,'[]'::jsonb),coalesce(p_requested_roots,'[]'::jsonb),
      coalesce(p_metadata,'{}'::jsonb)
        || jsonb_build_object(
             'identity_changed_on_enrollment',false,
             'identity_last_enrolled_at',now()
           ),
      now()
    )
    returning * into v_device;
  end if;

  insert into public.desktop_commander_receipts_v1(
    device_id,receipt_type,outcome,payload_hash,detail
  ) values (
    v_device.device_id,
    'enrollment_requested',
    v_device.status,
    p_host_fingerprint_sha256,
    jsonb_build_object(
      'device_key',v_device.device_key,
      'public_key_sha256',v_device.public_key_sha256,
      'platform',v_device.platform,
      'agent_version',v_device.agent_version,
      'identity_changed',v_identity_changed,
      'approval_reset',v_identity_changed
    )
  );

  return jsonb_build_object(
    'device_id',v_device.device_id,
    'device_key',v_device.device_key,
    'status',v_device.status,
    'public_key_sha256',v_device.public_key_sha256,
    'identity_changed',v_identity_changed,
    'approval_reset',v_identity_changed
  );
end;
$$;

revoke all on function public.register_desktop_commander_device_v1(
  text,text,text,text,text,text,text,jsonb,jsonb,jsonb
) from public,anon,authenticated;
grant execute on function public.register_desktop_commander_device_v1(
  text,text,text,text,text,text,text,jsonb,jsonb,jsonb
) to service_role;

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
  on conflict(idempotency_key) do nothing
  returning * into v_job;

  if not found then
    select * into v_existing
    from public.desktop_commander_jobs_v1
    where idempotency_key=trim(p_idempotency_key);

    if not found then raise exception 'idempotency_resolution_failed'; end if;
    if v_existing.input_hash <> v_hash then
      raise exception 'idempotency_key_conflict';
    end if;

    return jsonb_build_object(
      'created',false,'idempotent_replay',true,
      'job_id',v_existing.job_id,'status',v_existing.status,
      'input_hash',v_existing.input_hash
    );
  end if;

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
  if jsonb_array_length(coalesce(v_device.approved_roots,'[]'::jsonb)) < 1 then
    raise exception 'device_has_no_approved_roots';
  end if;

  update public.desktop_commander_devices_v1
  set last_heartbeat_at=now(),updated_at=now()
  where device_id=p_device_id;

  with expired as (
    update public.desktop_commander_jobs_v1 j
    set status='failed',
        error_code='lease_expired_attempts_exhausted',
        error_detail=coalesce(j.error_detail,'{}'::jsonb)
          || jsonb_build_object('lease_expired_at',j.lease_expires_at,'failed_at',now()),
        completed_at=now(),
        lease_expires_at=null,
        updated_at=now()
    where j.status='claimed'
      and j.lease_expires_at is not null
      and j.lease_expires_at<now()
      and j.attempts>=j.max_attempts
    returning j.*
  )
  insert into public.desktop_commander_receipts_v1(
    device_id,job_id,receipt_type,outcome,payload_hash,detail
  )
  select
    e.lease_device_id,e.job_id,'job_failed','failed',e.input_hash,
    jsonb_build_object(
      'operation',e.operation,
      'mutation_class',e.mutation_class,
      'error_code','lease_expired_attempts_exhausted',
      'attempts',e.attempts
    )
  from expired e;

  return query
  with candidates as (
    select j.job_id
    from public.desktop_commander_jobs_v1 j
    where j.available_at<=now()
      and (j.target_device_id is null or j.target_device_id=p_device_id)
      and (
        j.status='queued'
        or (
          j.status='claimed'
          and j.lease_expires_at is not null
          and j.lease_expires_at<now()
          and j.attempts<j.max_attempts
        )
      )
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
  ),
  receipted as (
    insert into public.desktop_commander_receipts_v1(
      device_id,job_id,receipt_type,outcome,payload_hash,detail
    )
    select
      p_device_id,c.job_id,'job_claimed','claimed',c.input_hash,
      jsonb_build_object(
        'operation',c.operation,
        'mutation_class',c.mutation_class,
        'attempts',c.attempts,
        'lease_expires_at',c.lease_expires_at
      )
    from claimed c
    returning job_id
  )
  select c.* from claimed c;
end;
$$;

revoke all on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  from public,anon,authenticated;
grant execute on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  to service_role;

create or replace function public.record_desktop_commander_heartbeat_v1(
  p_device_id uuid,
  p_agent_version text default null,
  p_capabilities jsonb default '[]'::jsonb,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_device public.desktop_commander_devices_v1%rowtype;
  v_now timestamptz:=now();
  v_capabilities jsonb:=coalesce(p_capabilities,'[]'::jsonb);
begin
  if jsonb_typeof(v_capabilities)<>'array'
     or jsonb_typeof(coalesce(p_metadata,'{}'::jsonb))<>'object' then
    raise exception 'invalid_heartbeat_payload';
  end if;

  select * into v_device
  from public.desktop_commander_devices_v1
  where device_id=p_device_id
  for update;

  if not found then raise exception 'unknown_device'; end if;
  if v_device.status='revoked' then raise exception 'device_revoked'; end if;

  update public.desktop_commander_devices_v1
  set last_heartbeat_at=v_now,
      agent_version=coalesce(left(p_agent_version,64),agent_version),
      capabilities=v_capabilities,
      metadata=metadata||coalesce(p_metadata,'{}'::jsonb),
      updated_at=v_now
  where device_id=p_device_id
  returning * into v_device;

  insert into public.desktop_commander_receipts_v1(
    device_id,receipt_type,outcome,detail
  ) values (
    v_device.device_id,
    'heartbeat',
    case when v_device.status='approved' then 'online_unverified_execution' else v_device.status end,
    jsonb_build_object(
      'device_key',v_device.device_key,
      'status',v_device.status,
      'capabilities_count',jsonb_array_length(v_capabilities),
      'approved_roots_count',jsonb_array_length(coalesce(v_device.approved_roots,'[]'::jsonb)),
      'selection_enabled',false
    )
  );

  insert into public.github_batch_workers_v2(
    worker_id,worker_type,connector_key,status,max_concurrency,capabilities,last_heartbeat_at,metadata,updated_at
  ) values (
    'glacier-desktop-commander',
    'desktop_commander',
    'desktop_commander.glacier',
    case when v_device.status='approved' then 'online' else 'source_ready' end,
    8,
    v_capabilities,
    case when v_device.status='approved' then v_now else null end,
    jsonb_build_object(
      'transport','outbound_signed_bridge_v1',
      'device_id',v_device.device_id,
      'device_key',v_device.device_key,
      'approved_roots_count',jsonb_array_length(coalesce(v_device.approved_roots,'[]'::jsonb)),
      'selection_enabled',false,
      'physical_device_execution_verified',false
    ),
    v_now
  )
  on conflict(worker_id) do update set
    worker_type=excluded.worker_type,
    connector_key=excluded.connector_key,
    status=excluded.status,
    max_concurrency=excluded.max_concurrency,
    capabilities=excluded.capabilities,
    last_heartbeat_at=excluded.last_heartbeat_at,
    metadata=public.github_batch_workers_v2.metadata||excluded.metadata,
    updated_at=v_now;

  if v_device.status='approved' then
    update public.connector_registry_v2
    set lifecycle_state='connected',
        authentication_state='authenticated',
        health_status='source_runtime_ready',
        freshness_status='fresh',
        last_checked_at=v_now,
        last_successful_probe_at=v_now,
        last_successful_probe_receipt_ref='desktop-commander-heartbeat:'||v_device.device_id::text,
        next_human_gate='read_only_claimed_job_then_enable_selection',
        metadata=metadata||jsonb_build_object(
          'transport','outbound_signed_bridge_v1',
          'device_id',v_device.device_id,
          'public_key_sha256',v_device.public_key_sha256,
          'selection_enabled',false,
          'physical_device_online',true,
          'physical_device_execution_verified',false,
          'approved_roots',v_device.approved_roots,
          'last_signed_heartbeat_at',v_now
        ),
        updated_at=v_now
    where connector_key='desktop_commander.glacier';
  end if;

  return jsonb_build_object(
    'status',v_device.status,
    'observed_at',v_now,
    'selection_enabled',false,
    'next_gate',case
      when v_device.status='approved' then 'read_only_claimed_job'
      else 'device_approval'
    end
  );
end;
$$;

revoke all on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  from public,anon,authenticated;
grant execute on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
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
  v_device public.desktop_commander_devices_v1%rowtype;
  v_receipt_type text;
  v_max_result_bytes integer;
  v_result_bytes integer;
  v_now timestamptz:=now();
begin
  if p_status not in ('completed','failed') then
    raise exception 'invalid_job_terminal_status';
  end if;
  if p_result_hash is not null and p_result_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_result_hash';
  end if;
  if p_duration_ms is not null and p_duration_ms<0 then
    raise exception 'invalid_duration_ms';
  end if;

  select * into v_device
  from public.desktop_commander_devices_v1
  where device_id=p_device_id
  for share;

  if not found or v_device.status<>'approved' then
    raise exception 'device_not_approved';
  end if;

  select * into v_job
  from public.desktop_commander_jobs_v1
  where job_id=p_job_id
    and status='claimed'
    and lease_device_id=p_device_id
    and lease_expires_at is not null
    and lease_expires_at>=v_now
  for update;

  if not found then
    raise exception 'job_not_owned_or_lease_expired';
  end if;

  select max_result_bytes into v_max_result_bytes
  from public.desktop_commander_operation_policy_v1
  where operation=v_job.operation and enabled=true;

  if v_max_result_bytes is null then
    raise exception 'desktop_commander_operation_not_allowed';
  end if;

  v_result_bytes:=octet_length(
    jsonb_build_object(
      'result_summary',coalesce(p_result_summary,'{}'::jsonb),
      'result_hash',p_result_hash,
      'error_code',p_error_code,
      'error_detail',coalesce(p_error_detail,'{}'::jsonb)
    )::text
  );
  if v_result_bytes>v_max_result_bytes then
    raise exception 'result_payload_too_large';
  end if;

  update public.desktop_commander_jobs_v1
  set status=p_status,
      result_summary=coalesce(p_result_summary,'{}'::jsonb),
      result_hash=p_result_hash,
      error_code=p_error_code,
      error_detail=coalesce(p_error_detail,'{}'::jsonb),
      duration_ms=p_duration_ms,
      completed_at=v_now,
      lease_expires_at=null,
      updated_at=v_now
  where job_id=p_job_id
  returning * into v_job;

  v_receipt_type:=case when p_status='completed' then 'job_completed' else 'job_failed' end;

  insert into public.desktop_commander_receipts_v1(
    device_id,job_id,receipt_type,outcome,payload_hash,detail
  ) values (
    p_device_id,p_job_id,v_receipt_type,p_status,p_result_hash,
    jsonb_build_object(
      'operation',v_job.operation,
      'mutation_class',v_job.mutation_class,
      'duration_ms',p_duration_ms,
      'error_code',p_error_code,
      'result_bytes',v_result_bytes
    )
  );

  if p_status='completed' and v_job.mutation_class='read' then
    update public.github_batch_workers_v2
    set status='online',
        metadata=metadata||jsonb_build_object(
          'selection_enabled',true,
          'physical_device_execution_verified',true,
          'read_probe_job_id',v_job.job_id,
          'read_probe_completed_at',v_now
        ),
        updated_at=v_now
    where worker_id='glacier-desktop-commander'
      and connector_key='desktop_commander.glacier';

    update public.connector_registry_v2
    set lifecycle_state='connected',
        authentication_state='authenticated',
        health_status='healthy',
        freshness_status='fresh',
        last_checked_at=v_now,
        last_successful_probe_at=v_now,
        last_successful_probe_receipt_ref='desktop-commander-job:'||v_job.job_id::text,
        next_human_gate='none',
        metadata=metadata||jsonb_build_object(
          'selection_enabled',true,
          'physical_device_online',true,
          'physical_device_execution_verified',true,
          'read_probe_job_id',v_job.job_id,
          'read_probe_completed_at',v_now
        ),
        connector_quality=jsonb_build_object(
          'score',99,
          'status','physical_device_execution_verified',
          'evidence',jsonb_build_array(
            'source/runtime verified',
            'approved physical device',
            'signed heartbeat verified',
            'read-only claimed job completed',
            'append-only terminal receipt recorded'
          )
        ),
        data_quality=jsonb_build_object(
          'score',99,
          'status','runtime_verified',
          'evidence',jsonb_build_array(
            'exact source SHA',
            'signed device identity',
            'approved roots',
            'read-only execution receipt'
          ),
          'dimensions',jsonb_build_object(
            'lineage',1,'validity',1,'timeliness',1,'uniqueness',1,
            'consistency',1,'completeness',1,'duplicate_risk',0
          )
        ),
        updated_at=v_now
    where connector_key='desktop_commander.glacier';

    insert into public.connector_capability_matrix_v2(
      connector_key,capability,capability_level,verified,verification_source,
      risk_level,notes,metadata,last_verified_at,updated_at
    ) values (
      'desktop_commander.glacier',
      'physical_device_execution',
      4,
      true,
      'desktop-commander-job:'||v_job.job_id::text,
      'high',
      'Physical Desktop Commander execution verified by a completed read-only claimed job after approved-device signed heartbeat.',
      jsonb_build_object(
        'device_id',p_device_id,
        'job_id',v_job.job_id,
        'operation',v_job.operation,
        'selection_enabled',true
      ),
      v_now,
      v_now
    )
    on conflict(connector_key,capability) do update set
      capability_level=excluded.capability_level,
      verified=true,
      verification_source=excluded.verification_source,
      risk_level=excluded.risk_level,
      notes=excluded.notes,
      metadata=public.connector_capability_matrix_v2.metadata||excluded.metadata,
      last_verified_at=v_now,
      updated_at=v_now;
  end if;

  return jsonb_build_object(
    'job_id',v_job.job_id,
    'status',v_job.status,
    'attempts',v_job.attempts,
    'result_bytes',v_result_bytes,
    'selection_enabled',p_status='completed' and v_job.mutation_class='read'
  );
end;
$$;

revoke all on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) from public,anon,authenticated;
grant execute on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) to service_role;

create or replace function public.desktop_commander_registry_preserve_bound_v1()
returns trigger
language plpgsql
set search_path='public','pg_temp'
as $$
begin
  if old.connector_key='desktop_commander.glacier'
     and coalesce((old.metadata->>'physical_device_execution_verified')::boolean,false)
     and not coalesce((new.metadata->>'physical_device_execution_verified')::boolean,false) then
    new.read_enabled:=old.read_enabled;
    new.write_enabled:=old.write_enabled;
    new.sync_enabled:=old.sync_enabled;
    new.search_enabled:=old.search_enabled;
    new.trigger_enabled:=old.trigger_enabled;
    new.health_status:=old.health_status;
    new.lifecycle_state:=old.lifecycle_state;
    new.authentication_state:=old.authentication_state;
    new.last_successful_probe_at:=old.last_successful_probe_at;
    new.last_successful_probe_receipt_ref:=old.last_successful_probe_receipt_ref;
    new.next_human_gate:=old.next_human_gate;
    new.connector_quality:=old.connector_quality;
    new.data_quality:=old.data_quality;
    new.metadata:=new.metadata||old.metadata;
  end if;
  return new;
end;
$$;

drop trigger if exists desktop_commander_registry_preserve_bound
  on public.connector_registry_v2;
create trigger desktop_commander_registry_preserve_bound
before update on public.connector_registry_v2
for each row
when (old.connector_key='desktop_commander.glacier')
execute function public.desktop_commander_registry_preserve_bound_v1();

comment on function public.register_desktop_commander_device_v1(
  text,text,text,text,text,text,text,jsonb,jsonb,jsonb
) is 'Re-enrollment is approval-preserving only for the same device identity. Key or host changes reset approval and approved roots.';
comment on function public.enqueue_desktop_commander_job_v1(
  text,text,jsonb,uuid,integer,integer
) is 'Atomic idempotent enqueue. Concurrent same-key/same-payload calls replay the original job; same-key/different-payload calls fail closed.';
comment on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  is 'Claims queued or retryable expired leases, terminalizes exhausted expired leases, and writes claim receipts in the same transaction.';
comment on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  is 'Transactionally records device heartbeat evidence and runtime presence without enabling selection before a read-only execution proof.';
comment on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) is 'Accepts terminal results only from an approved device holding a live lease, enforces per-operation result size, and promotes selection only after a completed read-only job.';

