-- Mirror of live migration register_call_e_continuity_connector_v1_1.
-- CALL-E is registered as an advertised, health-unverified voice surface.
-- Readback of a known run is enabled. Planning/execution remain disabled and
-- approval-gated until an explicit user call intent produces provider proof.

insert into public.connector_registry_v2 (
  connector_key, display_name, connector_class, canonical_role, authority_tier,
  read_enabled, write_enabled, sync_enabled, search_enabled, trigger_enabled,
  audit_enabled, destructive_actions_allowed, public_share_allowed,
  health_status, owner_scope, notes, lifecycle_state, authentication_state,
  sensitivity_ceiling, freshness_status, owner, next_human_gate, metadata
) values (
  'call_e', 'CALL-E', 'external_connector', 'source_native_voice_execution', 2,
  true, false, false, false, false,
  true, false, false,
  'unknown', 'operator',
  'CALL-E is exposed to the ChatGPT execution surface. Provider execution is not promoted to verified until an explicit user-authorized plan/run/readback produces a receipt.',
  'advertised', 'unknown',
  'confidential', 'unknown', 'apex-control-plane',
  'explicit_call_intent_then_plan_probe',
  jsonb_build_object(
    'tool_contract', jsonb_build_array('plan_call','run_call','get_call_run'),
    'external_call_requires_approved_plan', true,
    'run_id_required_for_readback', true,
    'registered_for_continuity', true
  )
)
on conflict (connector_key) do update
set display_name = excluded.display_name,
    canonical_role = excluded.canonical_role,
    authority_tier = excluded.authority_tier,
    read_enabled = true,
    write_enabled = false,
    audit_enabled = true,
    destructive_actions_allowed = false,
    public_share_allowed = false,
    health_status = case
      when public.connector_registry_v2.health_status in ('healthy','verified')
        then public.connector_registry_v2.health_status
      else 'unknown'
    end,
    lifecycle_state = case
      when public.connector_registry_v2.lifecycle_state = 'connected'
        then 'connected'
      else 'advertised'
    end,
    metadata = coalesce(public.connector_registry_v2.metadata,'{}'::jsonb) || excluded.metadata,
    owner = 'apex-control-plane',
    next_human_gate = 'explicit_call_intent_then_plan_probe',
    updated_at = now();

insert into public.connector_route_policy_v3 (
  route_key, connector_key, tool_name, capability, mutation_class, policy_version,
  priority, enabled, approval_required, destructive_actions_allowed,
  cache_ttl_seconds, estimated_rpc_units, fallback_group, metadata
) values
(
  'call_e:get_call_run:voice_run_readback:v1', 'call_e', 'get_call_run',
  'voice_run_readback', 'read', 'v1',
  100, true, false, false, 0, 1, 'voice_execution',
  jsonb_build_object('known_run_id_required',true,'provider_receipt_readback',true)
),
(
  'call_e:plan_call:voice_plan:v1', 'call_e', 'plan_call',
  'voice_plan', 'write', 'v1',
  99, false, true, false, 0, 1, 'voice_execution',
  jsonb_build_object('explicit_user_call_intent_required',true,'no_external_call_by_planning_alone',true)
),
(
  'call_e:run_call:voice_external_action:v1', 'call_e', 'run_call',
  'voice_external_action', 'write', 'v1',
  100, false, true, false, 0, 1, 'voice_execution',
  jsonb_build_object(
    'ready_plan_required',true,
    'confirm_token_required',true,
    'terminal_readback_required',true,
    'idempotent_plan_id_required',true
  )
)
on conflict (route_key) do update
set priority = excluded.priority,
    enabled = excluded.enabled,
    approval_required = excluded.approval_required,
    destructive_actions_allowed = false,
    fallback_group = excluded.fallback_group,
    metadata = excluded.metadata,
    updated_at = now();
