update public.connector_registry_v2
set metadata=metadata||jsonb_build_object(
      'backend_bridge',jsonb_build_object(
        'function','apex-desktop-commander-bridge',
        'version',3,
        'sha256','a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6'
      ),
      'runtime_hardening',jsonb_build_object(
        're_enrollment_approval_reset',true,
        'atomic_enqueue_idempotency',true,
        'expired_lease_recovery',true,
        'live_lease_required_for_finish',true,
        'result_size_enforced',true,
        'heartbeat_receipt_transactional',true,
        'heartbeat_metadata_merge',true,
        'selection_requires_read_only_execution_proof',true,
        'verified_selection_monotonic',true,
        'migration_v4','20260902222552',
        'migration_v5','20260902222903'
      )
    ),
    last_checked_at=now(),
    updated_at=now()
where connector_key='desktop_commander.glacier';

insert into public.connector_capability_matrix_v2(
  connector_key,capability,capability_level,verified,verification_source,
  risk_level,notes,metadata,last_verified_at,updated_at
) values (
  'desktop_commander.glacier',
  'signed_local_agent_bridge',
  4,
  true,
  'supabase:apex-desktop-commander-bridge:v3',
  'high',
  'Bridge v3 delegates heartbeat and claim evidence to transactional RPCs and distinguishes nonce replay from nonce persistence failure.',
  jsonb_build_object(
    'function','apex-desktop-commander-bridge',
    'version',3,
    'sha256','a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6',
    'heartbeat_rpc','record_desktop_commander_heartbeat_v1',
    'claim_receipts_transactional',true,
    'nonce_error_split',true
  ),
  now(),
  now()
)
on conflict(connector_key,capability) do update set
  capability_level=excluded.capability_level,
  verified=excluded.verified,
  verification_source=excluded.verification_source,
  risk_level=excluded.risk_level,
  notes=excluded.notes,
  metadata=public.connector_capability_matrix_v2.metadata||excluded.metadata,
  last_verified_at=excluded.last_verified_at,
  updated_at=now();
