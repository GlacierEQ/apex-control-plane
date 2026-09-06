insert into public.connector_route_policy_v3(
  route_key,connector_key,tool_name,capability,mutation_class,priority,enabled,
  approval_required,fallback_group,metadata
)
values(
  'github.backend_ops:bulk.read:repository_bulk_read:v6',
  'github.backend_ops','bulk.read','repository_bulk_read','read',12,true,false,'github',
  jsonb_build_object(
    'entrypoint','apex-github-connector',
    'execution_mode','in_process_bulk_read_v3',
    'max_items_per_call',50,
    'preferred_for_workload_class','bulk_read',
    'nested_edge_fanout',false,
    'item_level_receipts',true,
    'verified_batch_id','313f6282-2db9-41e7-b879-d6cc1ee41dad'
  )
)
on conflict(route_key) do update set
  enabled=true,priority=12,metadata=excluded.metadata,updated_at=now();

update public.connector_registry_v2
set metadata=metadata||jsonb_build_object(
  'bulk_read_entrypoint','apex-github-connector',
  'bulk_read_execution_mode','in_process_bulk_read_v3',
  'bulk_read_max_items_per_call',50,
  'bulk_read_nested_edge_fanout',false,
  'bulk_read_verified_batch_id','313f6282-2db9-41e7-b879-d6cc1ee41dad',
  'bulk_read_verified_items',100,
  'bulk_read_first_attempt_success_ratio',1.0,
  'bulk_read_p50_ms',221,
  'bulk_read_p95_ms',279,
  'bulk_read_p99_ms',357,
  'bulk_read_item_equivalent_avg_ms',240.20
),
connector_quality=jsonb_build_object(
  'score',99,
  'status','runtime_verified_bulk_v6',
  'evidence',jsonb_build_array(
    '100_of_100_bulk_read_first_attempt_success',
    'item_level_receipts',
    'zero_ambiguous_outcomes',
    'writes_remain_router_guarded'
  )
),
updated_at=now()
where connector_key='github.backend_ops';

insert into public.connector_capability_matrix_v2(
  connector_key,capability,capability_level,verified,verification_source,last_verified_at,
  risk_level,notes,metadata,updated_at
)
values(
  'github.backend_ops','repository_bulk_read',5,true,
  'runtime:batch:313f6282-2db9-41e7-b879-d6cc1ee41dad',now(),'low',
  'In-process bulk read path eliminates per-item nested Edge fan-out while preserving item-level connector receipts and batch QC.',
  jsonb_build_object(
    'items_verified',100,
    'success_ratio',1.0,
    'first_attempt_only',true,
    'retries',0,
    'p50_ms',221,'p95_ms',279,'p99_ms',357,
    'max_items_per_connector_call',50,
    'nested_edge_fanout',false
  ),now()
)
on conflict(connector_key,capability) do update set
  capability_level=excluded.capability_level,
  verified=excluded.verified,
  verification_source=excluded.verification_source,
  last_verified_at=excluded.last_verified_at,
  risk_level=excluded.risk_level,
  notes=excluded.notes,
  metadata=excluded.metadata,
  updated_at=now();
