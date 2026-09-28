-- github_backend_ops_routing_v1
-- Applied live in supabase-backend-ops as migration 20260831160850.
-- Static routing policy only. Runtime verification receipts remain runtime data.

insert into public.github_connector_config_v1 (
  connector_key,owner_login,mode,allow_default_branch_writes,destructive_actions_allowed,
  bootstrap_ref,metadata,updated_at
) values (
  'github.backend_ops','GlacierEQ','pr_first',false,false,
  'kb_4c41dc5c421c4d46af18845906e737fc',
  jsonb_build_object(
    'edge_function','apex-github-connector',
    'webhook_function','apex-github-webhook',
    'auth_model','github_app_single_repository_installation_tokens',
    'token_persisted',false,
    'readback_required_for_code_writes',true
  ),now()
)
on conflict (connector_key) do update set
  owner_login=excluded.owner_login,
  mode='pr_first',
  allow_default_branch_writes=false,
  destructive_actions_allowed=false,
  bootstrap_ref=excluded.bootstrap_ref,
  metadata=public.github_connector_config_v1.metadata || excluded.metadata,
  updated_at=now();

update public.connector_registry_v2
set display_name='GitHub Backend Ops',
    connector_class='source_control_gateway',
    canonical_role='implementation_gateway',
    authority_tier=2,
    read_enabled=true,
    write_enabled=true,
    sync_enabled=true,
    search_enabled=true,
    trigger_enabled=true,
    audit_enabled=true,
    destructive_actions_allowed=false,
    public_share_allowed=false,
    lifecycle_state='connected',
    authentication_state='authenticated',
    canonical_source_ref='github:GlacierEQ',
    approved_roots=jsonb_build_array('repo:GlacierEQ/*'),
    sensitivity_ceiling='confidential',
    owner='GlacierEQ',
    metadata=metadata || jsonb_build_object(
      'mode','pr_first',
      'token_persisted',false,
      'default_branch_writes_allowed',false,
      'destructive_actions_allowed',false,
      'pull_read_mode','issue_projection',
      'full_pull_fallback','github.native',
      'pull_create_fallback','github.native',
      'pull_review_fallback','github.native'
    ),
    updated_at=now()
where connector_key='github.backend_ops';

update public.connector_route_policy_v3
set enabled=false,
    destructive_actions_allowed=false,
    metadata=metadata || jsonb_build_object(
      'disabled_reason','github_app_pull_requests_permission_not_granted',
      'fallback_connector','github.native'
    ),
    updated_at=now()
where connector_key='github.backend_ops'
  and tool_name in ('pull.create','pull.review');

insert into public.connector_route_policy_v3 (
  route_key,connector_key,tool_name,capability,mutation_class,policy_version,priority,enabled,
  approval_required,destructive_actions_allowed,cache_ttl_seconds,estimated_rpc_units,fallback_group,metadata,updated_at
) values
  ('github.native:search_prs:pull_requests_full_read:v1','github.native','search_prs','pull_requests_full_read','read','v1',10,true,false,false,15,3,'github',jsonb_build_object('role','full_fidelity_pr_fallback'),now()),
  ('github.native:get_pr_info:pull_requests_full_read:v1','github.native','get_pr_info','pull_requests_full_read','read','v1',10,true,false,false,15,3,'github',jsonb_build_object('role','full_fidelity_pr_fallback'),now()),
  ('github.native:create_pull_request:pull_requests_write:v1','github.native','create_pull_request','pull_requests_write','write','v1',10,true,true,false,0,5,'github',jsonb_build_object('role','full_fidelity_pr_fallback'),now()),
  ('github.native:add_review_to_pr:pull_requests_review:v1','github.native','add_review_to_pr','pull_requests_review','write','v1',10,true,true,false,0,5,'github',jsonb_build_object('role','full_fidelity_pr_fallback'),now())
on conflict (route_key) do update set
  priority=excluded.priority,
  enabled=excluded.enabled,
  approval_required=excluded.approval_required,
  destructive_actions_allowed=false,
  fallback_group=excluded.fallback_group,
  metadata=public.connector_route_policy_v3.metadata || excluded.metadata,
  updated_at=now();
