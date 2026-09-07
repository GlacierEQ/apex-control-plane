-- connector_runtime_mcp_plugin_v3
-- Applied live in supabase-backend-ops as migration 20260907083331.
-- Exposes enabled non-Smithery connector routes through the governed connector execution runtime as MCP tools.

insert into public.connector_registry_v2 (
  connector_key,display_name,connector_class,canonical_role,authority_tier,
  read_enabled,write_enabled,search_enabled,trigger_enabled,audit_enabled,
  health_status,lifecycle_state,authentication_state,owner_scope,owner,
  next_human_gate,freshness_status,canonical_source_ref,metadata
) values (
  'connector.runtime_mcp',
  'Connector Runtime Direct MCP',
  'direct_mcp_plugin',
  'governed_connector_execution',
  1,
  true,true,true,true,true,
  'source_runtime_ready','connected','authenticated',
  'operator','GlacierEQ','none','fresh',
  'supabase-edge://apex-connector-tool-gateway',
  jsonb_build_object(
    'transport','mcp_streamable_http',
    'protocol_version','2025-06-18',
    'smithery_required',false,
    'edge_function','apex-connector-tool-gateway',
    'edge_function_version',2,
    'route_source','connector_route_policy_v3',
    'execution_queue','connector_execution_jobs_v3',
    'enqueue_rpc','enqueue_connector_execution_job_v3',
    'direct_route_count',77,
    'mcp_tool_count',78,
    'dynamic_route_tool_discovery',true,
    'smithery_routes_excluded',true,
    'approval_policy_preserved',true,
    'idempotency_preserved',true,
    'retry_circuit_receipts_preserved',true
  )
)
on conflict (connector_key) do update set
  display_name=excluded.display_name,
  connector_class=excluded.connector_class,
  canonical_role=excluded.canonical_role,
  authority_tier=excluded.authority_tier,
  read_enabled=excluded.read_enabled,
  write_enabled=excluded.write_enabled,
  search_enabled=excluded.search_enabled,
  trigger_enabled=excluded.trigger_enabled,
  audit_enabled=excluded.audit_enabled,
  health_status=excluded.health_status,
  lifecycle_state=excluded.lifecycle_state,
  authentication_state=excluded.authentication_state,
  owner_scope=excluded.owner_scope,
  owner=excluded.owner,
  next_human_gate=excluded.next_human_gate,
  freshness_status=excluded.freshness_status,
  canonical_source_ref=excluded.canonical_source_ref,
  metadata=excluded.metadata,
  updated_at=now();

update public.connector_registry_v2
set metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
      'plugins',jsonb_build_array(
        'github.direct_mcp',
        'notion.direct_mcp',
        'memory.direct_mcp',
        'connector.runtime_mcp'
      ),
      'plugin_count',4,
      'provider_tool_count',102,
      'fabric_tool_count',103,
      'dynamic_child_tool_discovery',true,
      'smithery_required',false
    ),
    updated_at=now()
where connector_key='apex.direct_mcp_fabric';
