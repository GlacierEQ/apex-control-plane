update public.connector_registry_v2
set metadata = metadata || jsonb_build_object(
      'execution_entrypoint','apex-github-router',
      'router_contract_version',2,
      'internal_gateway','apex-github-connector',
      'webhook_worker','apex-github-webhook-worker',
      'resource_leases','required_for_router_writes',
      'compare_before_write','required_for_router_contents_put',
      'circuit_breaker','enabled',
      'webhook_event_queue','enabled',
      'full_pull_fallback','github.native'
    ),
    updated_at=now()
where connector_key='github.backend_ops';

update public.connector_route_policy_v3
set metadata = metadata || jsonb_build_object(
      'entrypoint','apex-github-router',
      'internal_gateway','apex-github-connector',
      'router_contract_version',2,
      'lease_enforced',case when mutation_class='write' then true else false end,
      'circuit_breaker',true
    ),
    updated_at=now()
where connector_key='github.backend_ops';

insert into public.connector_route_policy_v3(
  route_key,connector_key,tool_name,capability,mutation_class,policy_version,priority,enabled,
  approval_required,destructive_actions_allowed,cache_ttl_seconds,estimated_rpc_units,fallback_group,metadata,updated_at
) values (
  'github.backend_ops:route.plan:permission_aware_routing:v2',
  'github.backend_ops','route.plan','permission_aware_routing','read','v2',5,true,false,false,5,1,'github',
  jsonb_build_object('entrypoint','apex-github-router','execution',false,'purpose','route_resolution'),now()
)
on conflict (route_key) do update set
  priority=excluded.priority,
  enabled=true,
  approval_required=false,
  destructive_actions_allowed=false,
  cache_ttl_seconds=excluded.cache_ttl_seconds,
  estimated_rpc_units=excluded.estimated_rpc_units,
  metadata=public.connector_route_policy_v3.metadata || excluded.metadata,
  updated_at=now();

insert into public.connector_capability_matrix_v2(
  connector_key,capability,capability_level,verified,verification_source,risk_level,notes,metadata,updated_at
) values
('github.backend_ops','permission_aware_routing',5,false,'runtime-required','low','Router resolves the strongest enabled GitHub lane from connector_route_policy_v3.',jsonb_build_object('entrypoint','apex-github-router','fallback_connector','github.native'),now()),
('github.backend_ops','atomic_resource_leases',5,false,'runtime-required','low','Router writes acquire atomic resource leases before external mutation.',jsonb_build_object('table','github_connector_operation_leases_v2','rpc','acquire_github_connector_lease_v2'),now()),
('github.backend_ops','compare_before_write',5,false,'runtime-required','low','Router contents.put requires expected_before_sha and compares live state before mutation.',jsonb_build_object('precondition','expected_before_sha'),now()),
('github.backend_ops','stale_write_rejection',5,false,'runtime-required','low','Stale compare-before-write state is rejected before the write reaches GitHub.',jsonb_build_object('status',409),now()),
('github.backend_ops','operation_circuit_breaker',5,false,'runtime-required','low','Per-operation circuit breaker protects GitHub from repeated transient-failure storms.',jsonb_build_object('table','github_connector_circuit_v2','threshold',3,'open_seconds',60),now()),
('github.backend_ops','webhook_event_queue',5,false,'runtime-required','low','HMAC-verified deliveries enqueue exactly one durable event.',jsonb_build_object('table','github_webhook_event_queue_v1','trigger','github_webhook_delivery_enqueue_v1'),now()),
('github.backend_ops','webhook_event_worker',5,false,'runtime-required','low','Worker atomically claims webhook events and executes bounded refreshes through the GitHub router.',jsonb_build_object('function','apex-github-webhook-worker','result_table','github_webhook_event_results_v1'),now())
on conflict (connector_key,capability) do update set
  capability_level=excluded.capability_level,
  verified=public.connector_capability_matrix_v2.verified,
  verification_source=case when public.connector_capability_matrix_v2.verified then public.connector_capability_matrix_v2.verification_source else excluded.verification_source end,
  last_verified_at=case when public.connector_capability_matrix_v2.verified then public.connector_capability_matrix_v2.last_verified_at else null end,
  risk_level=excluded.risk_level,
  notes=excluded.notes,
  metadata=public.connector_capability_matrix_v2.metadata || excluded.metadata,
  updated_at=now();
