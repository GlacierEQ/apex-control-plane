drop trigger if exists desktop_commander_device_execution_guard
  on public.desktop_commander_devices_v1;
create trigger desktop_commander_device_execution_guard
after update of device_id,status,device_key,public_key_spki_base64,public_key_sha256,host_fingerprint_sha256,approved_roots
on public.desktop_commander_devices_v1
for each row
execute function public.desktop_commander_device_execution_guard_v1();

update public.connector_registry_v2
set next_human_gate='physical_device_enrollment_then_approved_roots_then_signed_heartbeat_then_policy_bound_read_job_with_sha256_result',
    metadata=metadata||jsonb_build_object(
      'runtime_hardening',
      coalesce(metadata->'runtime_hardening','{}'::jsonb)
        || jsonb_build_object(
             'device_specific_execution_binding',true,
             'secondary_device_claim_isolation',true,
             'secondary_device_heartbeat_isolation',true,
             'binding_invalidation_on_identity_or_approval_loss',true,
             'execution_promotion_serialized',true,
             'migration_v9','device_binding_guard'
           )
    ),
    last_checked_at=now(),
    updated_at=now()
where connector_key='desktop_commander.glacier'
  and not coalesce((metadata->>'physical_device_execution_verified')::boolean,false);

update public.connector_capability_matrix_v2
set notes='Physical Desktop Commander execution remains unverified until one approved device establishes a device-specific policy-bound read proof with SHA-256 evidence. Once bound, secondary devices cannot inherit, claim through, or replace that execution binding automatically.',
    metadata=metadata||jsonb_build_object(
      'selection_enabled',false,
      'device_specific_binding_required',true,
      'secondary_device_claim_isolation',true,
      'secondary_device_heartbeat_isolation',true,
      'binding_invalidation_on_identity_or_approval_loss',true,
      'promotion_serialized',true,
      'next_gate','physical_device_enrollment_then_approved_roots_then_signed_heartbeat_then_policy_bound_read_job_with_sha256_result'
    ),
    updated_at=now()
where connector_key='desktop_commander.glacier'
  and capability='physical_device_execution'
  and verified=false;
