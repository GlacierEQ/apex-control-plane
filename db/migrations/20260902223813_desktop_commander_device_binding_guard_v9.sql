create or replace function public.desktop_commander_registry_preserve_bound_v1()
returns trigger
language plpgsql
set search_path='public','pg_temp'
as $$
declare
  v_execution_verified boolean:=false;
begin
  select coalesce(verified,false)
  into v_execution_verified
  from public.connector_capability_matrix_v2
  where connector_key='desktop_commander.glacier'
    and capability='physical_device_execution';

  v_execution_verified:=coalesce(v_execution_verified,false);

  if old.connector_key='desktop_commander.glacier'
     and coalesce((old.metadata->>'physical_device_execution_verified')::boolean,false)
     and not coalesce((new.metadata->>'physical_device_execution_verified')::boolean,false)
     and v_execution_verified then
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

create or replace function public.desktop_commander_device_execution_guard_v1()
returns trigger
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_verified boolean:=false;
  v_bound_device_id text;
  v_invalidate boolean:=false;
  v_reason text;
  v_now timestamptz:=now();
begin
  if old.device_id<>new.device_id then
    raise exception 'desktop_commander_device_id_immutable';
  end if;

  if old.status='approved' and new.status<>'approved' then
    v_invalidate:=true;
    v_reason:='device_status_'||new.status;
  elsif old.device_key is distinct from new.device_key
     or old.public_key_sha256 is distinct from new.public_key_sha256
     or old.public_key_spki_base64 is distinct from new.public_key_spki_base64
     or old.host_fingerprint_sha256 is distinct from new.host_fingerprint_sha256 then
    v_invalidate:=true;
    v_reason:='device_identity_changed';
  elsif jsonb_array_length(coalesce(new.approved_roots,'[]'::jsonb))<1
     and jsonb_array_length(coalesce(old.approved_roots,'[]'::jsonb))>0 then
    v_invalidate:=true;
    v_reason:='approved_roots_removed';
  end if;

  if not v_invalidate then return new; end if;

  select coalesce(verified,false),metadata->>'device_id'
  into v_verified,v_bound_device_id
  from public.connector_capability_matrix_v2
  where connector_key='desktop_commander.glacier'
    and capability='physical_device_execution';

  if coalesce(v_verified,false)
     and v_bound_device_id=old.device_id::text then
    update public.connector_capability_matrix_v2
    set verified=false,
        verification_source='runtime-required',
        notes='Physical Desktop Commander execution was invalidated because the bound device identity, approval status, or approved-root binding changed.',
        metadata=(metadata - 'device_id' - 'job_id' - 'operation' - 'result_hash')
          || jsonb_build_object(
               'selection_enabled',false,
               'binding_invalidated_at',v_now,
               'binding_invalidated_reason',v_reason,
               'previous_device_id',old.device_id,
               'policy_bound_read_required',true,
               'result_hash_required',true,
               'result_hash_algorithm','sha256'
             ),
        last_verified_at=null,
        updated_at=v_now
    where connector_key='desktop_commander.glacier'
      and capability='physical_device_execution';

    update public.github_batch_workers_v2
    set status='source_ready',
        last_heartbeat_at=null,
        metadata=(metadata - 'device_id' - 'read_probe_job_id' - 'read_probe_operation' - 'read_probe_result_hash')
          || jsonb_build_object(
               'selection_enabled',false,
               'physical_device_execution_verified',false,
               'binding_invalidated_at',v_now,
               'binding_invalidated_reason',v_reason,
               'previous_device_id',old.device_id
             ),
        updated_at=v_now
    where worker_id='glacier-desktop-commander'
      and connector_key='desktop_commander.glacier';

    update public.connector_registry_v2
    set health_status='source_runtime_ready',
        freshness_status='fresh',
        last_checked_at=v_now,
        last_successful_probe_at=v_now,
        last_successful_probe_receipt_ref='desktop-commander-binding-invalidated:'||old.device_id::text,
        next_human_gate='device_reapproval_then_signed_heartbeat_then_policy_bound_read_job_with_sha256_result',
        metadata=(metadata - 'device_id' - 'read_probe_job_id' - 'read_probe_operation' - 'read_probe_result_hash')
          || jsonb_build_object(
               'selection_enabled',false,
               'physical_device_online',false,
               'physical_device_execution_verified',false,
               'binding_invalidated_at',v_now,
               'binding_invalidated_reason',v_reason,
               'previous_device_id',old.device_id
             ),
        connector_quality=jsonb_build_object(
          'score',94,
          'status','source_runtime_verified_device_binding_invalidated',
          'evidence',jsonb_build_array(
            'source/runtime remains verified',
            'physical execution binding invalidated fail-closed',
            v_reason
          )
        ),
        updated_at=v_now
    where connector_key='desktop_commander.glacier';
  end if;

  return new;
end;
$$;

revoke all on function public.desktop_commander_device_execution_guard_v1()
  from public,anon,authenticated;
grant execute on function public.desktop_commander_device_execution_guard_v1()
  to service_role;

drop trigger if exists desktop_commander_device_execution_guard
  on public.desktop_commander_devices_v1;
create trigger desktop_commander_device_execution_guard
after update of status,device_key,public_key_spki_base64,public_key_sha256,host_fingerprint_sha256,approved_roots
on public.desktop_commander_devices_v1
for each row
execute function public.desktop_commander_device_execution_guard_v1();

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
  v_execution_verified boolean:=false;
  v_bound_device_id text;
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

  select coalesce(verified,false),metadata->>'device_id'
  into v_execution_verified,v_bound_device_id
  from public.connector_capability_matrix_v2
  where connector_key='desktop_commander.glacier'
    and capability='physical_device_execution';

  if coalesce(v_execution_verified,false)
     and (v_bound_device_id is null or v_bound_device_id<>p_device_id::text) then
    raise exception 'device_not_active_execution_binding';
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
  v_any_execution_verified boolean:=false;
  v_bound_device_id text;
  v_active_binding boolean:=false;
  v_foreign_binding boolean:=false;
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

  select coalesce(verified,false),metadata->>'device_id'
  into v_any_execution_verified,v_bound_device_id
  from public.connector_capability_matrix_v2
  where connector_key='desktop_commander.glacier'
    and capability='physical_device_execution';

  v_any_execution_verified:=coalesce(v_any_execution_verified,false);
  v_active_binding :=
    v_any_execution_verified
    and v_bound_device_id=p_device_id::text;
  v_foreign_binding :=
    v_any_execution_verified
    and (v_bound_device_id is null or v_bound_device_id<>p_device_id::text);

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
    case
      when v_device.status='approved' and v_active_binding then 'online_verified_execution'
      when v_device.status='approved' and v_foreign_binding then 'online_secondary_device'
      when v_device.status='approved' then 'online_unverified_execution'
      else v_device.status
    end,
    jsonb_build_object(
      'device_key',v_device.device_key,
      'status',v_device.status,
      'capabilities_count',jsonb_array_length(v_capabilities),
      'approved_roots_count',jsonb_array_length(coalesce(v_device.approved_roots,'[]'::jsonb)),
      'selection_enabled',v_active_binding,
      'physical_device_execution_verified',v_active_binding,
      'foreign_execution_binding',v_foreign_binding
    )
  );

  if v_foreign_binding then
    return jsonb_build_object(
      'status',v_device.status,
      'observed_at',v_now,
      'selection_enabled',false,
      'physical_device_execution_verified',false,
      'next_gate','active_execution_bound_to_other_device'
    );
  end if;

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
      'selection_enabled',v_active_binding,
      'physical_device_execution_verified',v_active_binding
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
        health_status=case when v_active_binding then 'healthy' else 'source_runtime_ready' end,
        freshness_status='fresh',
        last_checked_at=v_now,
        last_successful_probe_at=case
          when v_active_binding then last_successful_probe_at
          else v_now
        end,
        last_successful_probe_receipt_ref=case
          when v_active_binding then last_successful_probe_receipt_ref
          else 'desktop-commander-heartbeat:'||v_device.device_id::text
        end,
        next_human_gate=case
          when v_active_binding then 'none'
          else 'policy_bound_read_job_with_sha256_result_then_enable_selection'
        end,
        metadata=metadata||jsonb_build_object(
          'transport','outbound_signed_bridge_v1',
          'device_id',v_device.device_id,
          'public_key_sha256',v_device.public_key_sha256,
          'selection_enabled',v_active_binding,
          'physical_device_online',true,
          'physical_device_execution_verified',v_active_binding,
          'approved_roots',v_device.approved_roots,
          'last_signed_heartbeat_at',v_now
        ),
        updated_at=v_now
    where connector_key='desktop_commander.glacier';
  end if;

  return jsonb_build_object(
    'status',v_device.status,
    'observed_at',v_now,
    'selection_enabled',v_active_binding,
    'physical_device_execution_verified',v_active_binding,
    'next_gate',case
      when v_device.status<>'approved' then 'device_approval'
      when v_active_binding then 'none'
      else 'policy_bound_read_job_with_sha256_result'
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
  v_policy public.desktop_commander_operation_policy_v1%rowtype;
  v_receipt_type text;
  v_result_bytes integer;
  v_now timestamptz:=now();
  v_candidate_execution_proof boolean:=false;
  v_execution_proof boolean:=false;
  v_existing_execution_verified boolean:=false;
  v_bound_device_id text;
  v_proof_blocked_reason text;
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

  select * into v_policy
  from public.desktop_commander_operation_policy_v1
  where operation=v_job.operation and enabled=true;

  if not found then
    raise exception 'desktop_commander_operation_not_allowed';
  end if;
  if v_job.mutation_class<>v_policy.mutation_class then
    raise exception 'job_policy_mismatch';
  end if;

  v_result_bytes:=octet_length(
    jsonb_build_object(
      'result_summary',coalesce(p_result_summary,'{}'::jsonb),
      'result_hash',p_result_hash,
      'error_code',p_error_code,
      'error_detail',coalesce(p_error_detail,'{}'::jsonb)
    )::text
  );
  if v_result_bytes>v_policy.max_result_bytes then
    raise exception 'result_payload_too_large';
  end if;

  v_candidate_execution_proof :=
    p_status='completed'
    and v_policy.mutation_class='read'
    and p_result_hash is not null;

  if v_candidate_execution_proof then
    perform pg_advisory_xact_lock(hashtext('desktop_commander.physical_execution_binding'));

    select coalesce(verified,false),metadata->>'device_id'
    into v_existing_execution_verified,v_bound_device_id
    from public.connector_capability_matrix_v2
    where connector_key='desktop_commander.glacier'
      and capability='physical_device_execution';

    v_existing_execution_verified:=coalesce(v_existing_execution_verified,false);

    if v_existing_execution_verified
       and (v_bound_device_id is null or v_bound_device_id<>p_device_id::text) then
      v_execution_proof:=false;
      v_proof_blocked_reason:='execution_binding_exists';
    else
      v_execution_proof:=true;
    end if;
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
      'policy_mutation_class',v_policy.mutation_class,
      'duration_ms',p_duration_ms,
      'error_code',p_error_code,
      'result_bytes',v_result_bytes,
      'candidate_execution_proof',v_candidate_execution_proof,
      'execution_proof',v_execution_proof,
      'proof_blocked_reason',v_proof_blocked_reason
    )
  );

  if v_execution_proof then
    update public.github_batch_workers_v2
    set status='online',
        metadata=metadata||jsonb_build_object(
          'device_id',p_device_id,
          'selection_enabled',true,
          'physical_device_execution_verified',true,
          'read_probe_job_id',v_job.job_id,
          'read_probe_operation',v_job.operation,
          'read_probe_result_hash',p_result_hash,
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
          'device_id',p_device_id,
          'selection_enabled',true,
          'physical_device_online',true,
          'physical_device_execution_verified',true,
          'read_probe_job_id',v_job.job_id,
          'read_probe_operation',v_job.operation,
          'read_probe_result_hash',p_result_hash,
          'read_probe_completed_at',v_now
        ),
        connector_quality=jsonb_build_object(
          'score',99,
          'status','physical_device_execution_verified',
          'evidence',jsonb_build_array(
            'source/runtime verified',
            'approved physical device',
            'signed heartbeat verified',
            'policy-bound read-only claimed job completed',
            'non-null SHA-256 result hash returned',
            'device-specific execution binding established',
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
            'policy-bound read-only execution receipt',
            'SHA-256 result hash',
            'device-specific execution binding'
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
      'Physical Desktop Commander execution verified by a device-bound policy-approved read-only claimed job with a SHA-256 result hash after approved-device signed heartbeat.',
      jsonb_build_object(
        'device_id',p_device_id,
        'job_id',v_job.job_id,
        'operation',v_job.operation,
        'result_hash',p_result_hash,
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
    'candidate_execution_proof',v_candidate_execution_proof,
    'execution_proof',v_execution_proof,
    'proof_blocked_reason',v_proof_blocked_reason,
    'selection_enabled',v_execution_proof
  );
end;
$$;

revoke all on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) from public,anon,authenticated;
grant execute on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) to service_role;

comment on function public.desktop_commander_device_execution_guard_v1()
  is 'Invalidates the physical execution binding fail-closed when the bound device loses approval, approved roots, or identity continuity.';
comment on function public.claim_desktop_commander_jobs_v1(uuid,integer,integer)
  is 'Claims work only for an approved rooted device and, after physical execution is verified, only for the device currently bound to that execution capability.';
comment on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  is 'Records signed heartbeat evidence without allowing a secondary device to inherit or overwrite another device execution binding.';
comment on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) is 'Serializes physical execution promotion, binds proof to one device, and requires current policy read classification plus SHA-256 result evidence.';
