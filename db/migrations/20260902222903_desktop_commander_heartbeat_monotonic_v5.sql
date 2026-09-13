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
  v_execution_verified boolean:=false;
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

  select coalesce(verified,false)
  into v_execution_verified
  from public.connector_capability_matrix_v2
  where connector_key='desktop_commander.glacier'
    and capability='physical_device_execution';

  v_execution_verified:=coalesce(v_execution_verified,false);

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
      when v_device.status='approved' and v_execution_verified then 'online_verified_execution'
      when v_device.status='approved' then 'online_unverified_execution'
      else v_device.status
    end,
    jsonb_build_object(
      'device_key',v_device.device_key,
      'status',v_device.status,
      'capabilities_count',jsonb_array_length(v_capabilities),
      'approved_roots_count',jsonb_array_length(coalesce(v_device.approved_roots,'[]'::jsonb)),
      'selection_enabled',v_execution_verified,
      'physical_device_execution_verified',v_execution_verified
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
      'selection_enabled',v_execution_verified,
      'physical_device_execution_verified',v_execution_verified
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
        health_status=case when v_execution_verified then 'healthy' else 'source_runtime_ready' end,
        freshness_status='fresh',
        last_checked_at=v_now,
        last_successful_probe_at=case
          when v_execution_verified then last_successful_probe_at
          else v_now
        end,
        last_successful_probe_receipt_ref=case
          when v_execution_verified then last_successful_probe_receipt_ref
          else 'desktop-commander-heartbeat:'||v_device.device_id::text
        end,
        next_human_gate=case
          when v_execution_verified then 'none'
          else 'read_only_claimed_job_then_enable_selection'
        end,
        metadata=metadata||jsonb_build_object(
          'transport','outbound_signed_bridge_v1',
          'device_id',v_device.device_id,
          'public_key_sha256',v_device.public_key_sha256,
          'selection_enabled',v_execution_verified,
          'physical_device_online',true,
          'physical_device_execution_verified',v_execution_verified,
          'approved_roots',v_device.approved_roots,
          'last_signed_heartbeat_at',v_now
        ),
        updated_at=v_now
    where connector_key='desktop_commander.glacier';
  end if;

  return jsonb_build_object(
    'status',v_device.status,
    'observed_at',v_now,
    'selection_enabled',v_execution_verified,
    'physical_device_execution_verified',v_execution_verified,
    'next_gate',case
      when v_device.status<>'approved' then 'device_approval'
      when v_execution_verified then 'none'
      else 'read_only_claimed_job'
    end
  );
end;
$$;

revoke all on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  from public,anon,authenticated;
grant execute on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  to service_role;

comment on function public.record_desktop_commander_heartbeat_v1(uuid,text,jsonb,jsonb)
  is 'Transactionally records signed device heartbeat evidence. Heartbeat cannot promote unverified physical execution and cannot demote an execution capability previously verified by a completed read-only claimed job.';
