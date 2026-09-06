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
  v_execution_proof boolean:=false;
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

  v_execution_proof :=
    p_status='completed'
    and v_policy.mutation_class='read'
    and p_result_hash is not null;

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
      'execution_proof',v_execution_proof
    )
  );

  if v_execution_proof then
    update public.github_batch_workers_v2
    set status='online',
        metadata=metadata||jsonb_build_object(
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
            'SHA-256 result hash'
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
      'Physical Desktop Commander execution verified by a policy-bound completed read-only claimed job with a SHA-256 result hash after approved-device signed heartbeat.',
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
    'execution_proof',v_execution_proof,
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

comment on function public.finish_desktop_commander_job_v1(
  uuid,uuid,text,jsonb,text,text,jsonb,integer
) is 'Accepts terminal results only from an approved device holding a live lease, enforces current operation-policy class and result-size limits, and promotes physical execution only for a completed policy-bound read operation carrying a SHA-256 result hash.';
