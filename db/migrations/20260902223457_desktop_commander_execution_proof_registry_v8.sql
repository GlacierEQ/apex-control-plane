update public.connector_registry_v2
set metadata=metadata||jsonb_build_object(
      'runtime_hardening',
      coalesce(metadata->'runtime_hardening','{}'::jsonb)
        || jsonb_build_object(
             'execution_proof_policy_bound',true,
             'execution_proof_requires_result_hash',true,
             'execution_proof_result_hash_algorithm','sha256',
             'migration_v7','20260902223417'
           )
    ),
    last_checked_at=now(),
    updated_at=now()
where connector_key='desktop_commander.glacier';

update public.connector_capability_matrix_v2
set notes='Physical Desktop Commander execution remains unverified until a policy-bound completed read-only claimed job returns a SHA-256 result hash after approved-device signed heartbeat.',
    metadata=metadata||jsonb_build_object(
      'selection_enabled',false,
      'policy_bound_read_required',true,
      'result_hash_required',true,
      'result_hash_algorithm','sha256',
      'proof_migration','20260902223417'
    ),
    updated_at=now()
where connector_key='desktop_commander.glacier'
  and capability='physical_device_execution'
  and verified=false;
