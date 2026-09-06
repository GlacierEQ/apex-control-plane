insert into public.control_plane_connector_bindings(
  binding_key,source_system,account_ref,account_label,connector_ref,
  capabilities,scope,status,metadata,updated_at
) values (
  'binding:supabase:backend_ops_continuity',
  'supabase',
  null,
  'supabase-backend-ops / communications continuity',
  'mcp__Supabase__',
  '["continuity_frontier","continuity_attention","continuity_preflight","continuity_receipts","legal_execution"]'::jsonb,
  jsonb_build_object(
    'project_id','dyhprklicgewmrimecey',
    'authority_role','communications_and_legal_execution_runtime',
    'replication_policy','frontier_hash_watermark_receipts_only'
  ),
  'ACTIVE',
  jsonb_build_object(
    'peer','backend_ops',
    'authoritative_for',jsonb_build_array(
      'communications_continuity',
      'provider_action_preflight',
      'continuity_receipts',
      'legal_execution_runtime'
    ),
    'not_authoritative_for',jsonb_build_array(
      'case_source_truth',
      'global_frontier',
      'provider_native_truth'
    ),
    'global_projection_owner','supabase-glaciereq',
    'case_source_owner','GlacierEQ/DOCKETS',
    'provider_truth_rule','provider-native receipt outranks projection'
  ),
  now()
)
on conflict(binding_key) do update set
  source_system=excluded.source_system,
  account_ref=excluded.account_ref,
  account_label=excluded.account_label,
  connector_ref=excluded.connector_ref,
  capabilities=excluded.capabilities,
  scope=excluded.scope,
  status=excluded.status,
  metadata=public.control_plane_connector_bindings.metadata||excluded.metadata,
  updated_at=now();

insert into public.control_plane_ingestion_cursors(
  binding_key,stream_key,cursor_value,watermark_at,last_attempt_at,last_success_at,last_error,metadata,updated_at
) values
(
  'binding:supabase:backend_ops_continuity',
  'continuity_frontier',
  null,null,null,null,null,
  '{"direction":"backend_ops_to_global_projection","payload_policy":"hash_watermark_counts_receipts"}'::jsonb,
  now()
),
(
  'binding:supabase:backend_ops_continuity',
  'global_frontier',
  null,null,null,null,null,
  '{"direction":"global_projection_to_backend_ops","payload_policy":"hash_watermark_operator_cursor"}'::jsonb,
  now()
),
(
  'binding:supabase:backend_ops_continuity',
  'provider_receipts',
  null,null,null,null,null,
  '{"direction":"bidirectional_reconciliation","payload_policy":"receipt_refs_statuses_only"}'::jsonb,
  now()
)
on conflict(binding_key,stream_key) do update set
  metadata=public.control_plane_ingestion_cursors.metadata||excluded.metadata,
  updated_at=now();

