-- direct_memory_mcp_plugin_v2
-- Applied live in supabase-backend-ops as migration 20260907082747.
-- Adds the direct Memory federation MCP as a peer-preserving execution surface.

insert into public.connector_registry_v2 (
  connector_key,display_name,connector_class,canonical_role,authority_tier,
  read_enabled,write_enabled,search_enabled,trigger_enabled,audit_enabled,
  health_status,lifecycle_state,authentication_state,owner_scope,owner,
  next_human_gate,freshness_status,canonical_source_ref,metadata
) values (
  'memory.direct_mcp','Memory Federation Direct MCP','direct_mcp_plugin','memory_federation_execution',1,
  true,true,false,true,true,'source_runtime_ready','connected','authenticated',
  'operator','GlacierEQ','none','fresh','supabase-edge://apex-direct-memory-mcp',
  jsonb_build_object(
    'transport','mcp_streamable_http',
    'protocol_version','2025-06-18',
    'smithery_required',false,
    'edge_function','apex-direct-memory-mcp',
    'provider_runtime','memory-federation-dispatcher',
    'tool_count',3,
    'backends',jsonb_build_array('supermemory','mem0','pinecone','qdrant','mem','casebrain','memoryplugin'),
    'peer_authority_preserved',true
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
  metadata=coalesce(connector_registry_v2.metadata,'{}'::jsonb) || excluded.metadata,
  updated_at=now();

update public.connector_registry_v2
set metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
      'plugins',jsonb_build_array('github.direct_mcp','notion.direct_mcp','memory.direct_mcp'),
      'provider_tool_count',24,
      'fabric_tool_count',25,
      'dynamic_child_tool_discovery',true,
      'smithery_required',false
    ),
    updated_at=now()
where connector_key='apex.direct_mcp_fabric';

update public.connector_registry_v2
set metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
      'federation_mcp','memory.direct_mcp',
      'federation_transport','direct',
      'peer_authority_preserved',true,
      'smithery_quota_primary',false
    ),
    updated_at=now()
where connector_key in ('mem.primary','memory.plugin','supermemory');
