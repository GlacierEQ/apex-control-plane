-- direct_mcp_plugin_fabric_v1
-- Applied live in supabase-backend-ops as migration 20260907082202.
-- Makes GlacierEQ-owned direct MCP routes primary for GitHub and Notion; Smithery is fallback only.

insert into public.connector_registry_v2 (
  connector_key,display_name,connector_class,canonical_role,authority_tier,
  read_enabled,write_enabled,search_enabled,trigger_enabled,audit_enabled,
  health_status,lifecycle_state,authentication_state,owner_scope,owner,
  next_human_gate,freshness_status,canonical_source_ref,metadata
) values
(
  'apex.direct_mcp_fabric','APEX Direct MCP Fabric','mcp_gateway','tool_mesh',1,
  true,true,true,true,true,'source_runtime_ready','connected','authenticated',
  'operator','GlacierEQ','none','fresh','supabase-edge://apex-direct-mcp-fabric',
  jsonb_build_object(
    'transport','mcp_streamable_http','protocol_version','2025-06-18',
    'smithery_required',false,'edge_function','apex-direct-mcp-fabric',
    'plugins',jsonb_build_array('github.direct_mcp','notion.direct_mcp'),'tool_count',22
  )
),
(
  'github.direct_mcp','GitHub Direct MCP','direct_mcp_plugin','implementation_gateway',1,
  true,true,true,true,true,'source_runtime_ready','connected','authenticated',
  'operator','GlacierEQ','none','fresh','supabase-edge://apex-direct-github-mcp',
  jsonb_build_object(
    'transport','mcp_streamable_http','protocol_version','2025-06-18',
    'smithery_required',false,'edge_function','apex-direct-github-mcp',
    'provider_runtime','apex-github-connector','tool_count',18,
    'provider_receipts','github_connector_receipts_v1'
  )
),
(
  'notion.direct_mcp','Notion Direct MCP','direct_mcp_plugin','knowledge',1,
  true,false,true,false,true,'source_runtime_ready','connected','authenticated',
  'operator','GlacierEQ','none','fresh','supabase-edge://apex-direct-notion-mcp',
  jsonb_build_object(
    'transport','mcp_streamable_http','protocol_version','2025-06-18',
    'smithery_required',false,'edge_function','apex-direct-notion-mcp',
    'credential_source','supabase_vault:get_apex_notion_token','tool_count',3
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
      'preferred_mcp','github.direct_mcp',
      'mcp_transport','direct',
      'smithery_role','fallback_only_for_github',
      'smithery_quota_primary',false
    ),
    updated_at=now()
where connector_key in ('github','github.native','github.glaciereq','github.backend_ops');

update public.connector_registry_v2
set metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
      'preferred_mcp','notion.direct_mcp',
      'mcp_transport','direct',
      'smithery_role','fallback_only_for_notion',
      'smithery_quota_primary',false
    ),
    updated_at=now()
where connector_key in ('notion','notion.native');
