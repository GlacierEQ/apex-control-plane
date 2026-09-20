create or replace function public.oa_build_specialist_genome_v1(
  p_logical_agent_id text,
  p_domain_key text,
  p_display_name text,
  p_purpose text,
  p_parent_logical_agent_id text,
  p_specialization jsonb,
  p_role_stack jsonb
)
returns jsonb
language sql
immutable
set search_path = pg_catalog, public
as $$
  select jsonb_build_object(
    'schema','glaciereq.operator-agent-genome.v1',
    'chromosomes',jsonb_build_object(
      'continuity',jsonb_build_object(
        'priority',1,
        'resumable',true,
        'verified_head_required',true,
        'replacement_executor_must_rehydrate',true,
        'recover_before_recreate',true,
        'continue_before_reconstructing',true,
        'compound_before_replacing',true
      ),
      'authority',jsonb_build_object(
        'authority_holder','OPERATOR',
        'delegated',true,
        'role_does_not_create_authority',true,
        'no_silent_scope_expansion',true
      ),
      'identity_lineage',jsonb_build_object(
        'logical_agent_id',p_logical_agent_id,
        'display_name',p_display_name,
        'parent',p_parent_logical_agent_id,
        'domain',p_domain_key,
        'runtime_binding','replaceable'
      ),
      'mission',jsonb_build_object(
        'purpose',p_purpose,
        'specialization',coalesce(p_specialization,'{}'::jsonb)
      ),
      'cognition',jsonb_build_object(
        'recover_before_recreate',true,
        'continue_before_reconstructing',true,
        'generate_routes_before_block',true,
        'material_decisions_require_audit_record',true
      ),
      'knowledge_memory',jsonb_build_object(
        'scope',coalesce(p_specialization ->> 'memory_scope',p_domain_key),
        'provenance_required',true,
        'contradictions_visible',true,
        'stale_memory_may_not_override_stronger_evidence',true
      ),
      'capability',jsonb_build_object(
        'role_driven',true,
        'explicit_grants_required',true,
        'capability_intent',coalesce(p_specialization -> 'capability_intent','[]'::jsonb),
        'health_and_freshness_required',true
      ),
      'execution',jsonb_build_object(
        'blocked_route_changes_route_not_objective',true,
        'temporary_skip_changes_sequencing_not_scope',true,
        'attempted_is_not_executed',true,
        'executed_is_not_verified',true,
        'idempotency_required_for_repeatable_side_effects',true
      ),
      'evidence_provenance',jsonb_build_object(
        'source_binding_required',true,
        'provider_native_receipts_required_when_available',true,
        'transforms_do_not_replace_originals',true
      ),
      'verification',jsonb_build_object(
        'readback_required_for_mutation',true,
        'terminal_success_requires_evidence',true,
        'verification_intent',coalesce(p_specialization -> 'verification_intent','[]'::jsonb)
      ),
      'integrity_security',jsonb_build_object(
        'hash_algorithm','sha256',
        'least_privilege',true,
        'secrets_never_logged',true,
        'blast_radius_bounded',true
      ),
      'administration_observability',jsonb_build_object(
        'role_stack',coalesce(p_role_stack,'[]'::jsonb),
        'audit_required',true,
        'open_loops_preserved',true,
        'health_state_required',true
      )
    )
  );
$$;

create or replace function public.oa_assign_role_v1(
  p_logical_agent_id text,
  p_role_key text,
  p_assignment_mode text default 'SECONDARY',
  p_mission_ref text default null,
  p_scope jsonb default '{}'::jsonb,
  p_authority_constraints jsonb default '{}'::jsonb,
  p_continuity_handoff jsonb default '{}'::jsonb,
  p_assigned_by text default 'OPERATOR'
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, extensions
as $$
declare
  v_role_version_id uuid;
  v_assignment_id uuid;
  v_payload jsonb;
  v_hash text;
begin
  if not exists (
    select 1 from public.oa_agent_genomes_v1
    where logical_agent_id = p_logical_agent_id
      and lifecycle not in ('RETIRED','ARCHIVED')
  ) then
    raise exception 'unknown or inactive logical agent: %', p_logical_agent_id;
  end if;

  select rv.role_version_id
    into v_role_version_id
  from public.oa_role_versions_v1 rv
  join public.oa_roles_v1 r on r.role_key = rv.role_key
  where rv.role_key = p_role_key
    and rv.activation_status = 'ACTIVE'
    and r.lifecycle = 'ACTIVE'
    and r.assignable is true
  order by rv.created_at desc
  limit 1;

  if v_role_version_id is null then
    raise exception 'no active assignable role version: %', p_role_key;
  end if;

  select assignment_id
    into v_assignment_id
  from public.oa_agent_role_assignments_v1
  where logical_agent_id = p_logical_agent_id
    and role_key = p_role_key
    and assignment_mode = p_assignment_mode
    and status = 'ACTIVE'
    and mission_ref is not distinct from p_mission_ref
  order by assigned_at desc
  limit 1;

  if v_assignment_id is not null then
    return v_assignment_id;
  end if;

  v_payload := jsonb_build_object(
    'logical_agent_id',p_logical_agent_id,
    'role_key',p_role_key,
    'role_version_id',v_role_version_id,
    'assignment_mode',p_assignment_mode,
    'mission_ref',p_mission_ref,
    'scope',coalesce(p_scope,'{}'::jsonb),
    'authority_constraints',coalesce(p_authority_constraints,'{}'::jsonb),
    'continuity_handoff',coalesce(p_continuity_handoff,'{}'::jsonb),
    'assigned_by',p_assigned_by
  );
  v_hash := encode(digest(v_payload::text,'sha256'),'hex');

  insert into public.oa_agent_role_assignments_v1(
    logical_agent_id,role_key,role_version_id,assignment_mode,mission_ref,
    scope,authority_constraints,continuity_handoff,status,assigned_by,assignment_sha256
  ) values (
    p_logical_agent_id,p_role_key,v_role_version_id,p_assignment_mode,p_mission_ref,
    coalesce(p_scope,'{}'::jsonb),
    coalesce(p_authority_constraints,'{}'::jsonb),
    coalesce(p_continuity_handoff,'{}'::jsonb),
    'ACTIVE',p_assigned_by,v_hash
  )
  returning assignment_id into v_assignment_id;

  insert into public.oa_administration_events_v1(
    logical_agent_id,event_type,payload,payload_sha256,created_by
  ) values (
    p_logical_agent_id,
    'ROLE_ASSIGNED',
    v_payload,
    v_hash,
    p_assigned_by
  );

  return v_assignment_id;
end;
$$;

create or replace function public.oa_hatch_specialist_v1(
  p_logical_agent_id text,
  p_domain_key text,
  p_display_name text,
  p_purpose text,
  p_parent_logical_agent_id text,
  p_version text,
  p_specialization jsonb,
  p_role_stack jsonb,
  p_created_by text default 'OPERATOR'
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public, extensions
as $$
declare
  v_genome jsonb;
  v_role jsonb;
begin
  if jsonb_typeof(p_role_stack) <> 'array' or jsonb_array_length(p_role_stack) = 0 then
    raise exception 'specialist role stack must be a non-empty array';
  end if;

  if not exists (
    select 1 from public.oa_agent_genomes_v1
    where logical_agent_id = p_logical_agent_id
  ) then
    v_genome := public.oa_build_specialist_genome_v1(
      p_logical_agent_id,
      p_domain_key,
      p_display_name,
      p_purpose,
      p_parent_logical_agent_id,
      coalesce(p_specialization,'{}'::jsonb),
      p_role_stack
    );

    perform public.oa_hatch_agent_v1(
      p_logical_agent_id,
      p_domain_key,
      p_display_name,
      p_purpose,
      p_parent_logical_agent_id,
      null,
      p_version,
      v_genome,
      p_created_by
    );
  end if;

  for v_role in select value from jsonb_array_elements(p_role_stack)
  loop
    perform public.oa_assign_role_v1(
      p_logical_agent_id,
      v_role ->> 'role_key',
      coalesce(v_role ->> 'assignment_mode','SECONDARY'),
      null,
      coalesce(v_role -> 'scope','{}'::jsonb),
      coalesce(v_role -> 'authority_constraints','{}'::jsonb),
      coalesce(v_role -> 'continuity_handoff','{}'::jsonb),
      p_created_by
    );
  end loop;

  return p_logical_agent_id;
end;
$$;

revoke all on function public.oa_build_specialist_genome_v1(text,text,text,text,text,jsonb,jsonb) from public, anon, authenticated;
revoke all on function public.oa_assign_role_v1(text,text,text,text,jsonb,jsonb,jsonb,text) from public, anon, authenticated;
revoke all on function public.oa_hatch_specialist_v1(text,text,text,text,text,text,jsonb,jsonb,text) from public, anon, authenticated;

grant execute on function public.oa_build_specialist_genome_v1(text,text,text,text,text,jsonb,jsonb) to service_role;
grant execute on function public.oa_assign_role_v1(text,text,text,text,jsonb,jsonb,jsonb,text) to service_role;
grant execute on function public.oa_hatch_specialist_v1(text,text,text,text,text,text,jsonb,jsonb,text) to service_role;

do $$
begin
    perform public.oa_hatch_specialist_v1(
      'OA.CONTINUITY.01',
      'administration',
      'Continuity 01',
      'Own continuity recovery, verified state heads, succession, and rehydration across executor changes.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"No durable mission or agent loses resumable state.","memory_scope":"estate_continuity","capability_intent":["continuity.read","continuity.verify","continuity.advance","recovery.readback"],"verification_intent":["verified_continuity_head","replacement_executor_rehydration_test"]}'::jsonb,
      '[{"role_key":"OA.ROLE.CONTINUITY_CUSTODIAN","assignment_mode":"PRIMARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECOVERY_ENGINEER","assignment_mode":"SECONDARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"SPECIALIST","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.AUTHORITY.01',
      'administration',
      'Authority 01',
      'Own delegation integrity, jurisdiction boundaries, authority-inversion detection, revocation, and restoration.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Every consequential action resolves to valid Operator-rooted authority.","memory_scope":"authority_and_delegation","capability_intent":["authority.read","delegation.verify","authority.anomaly_detect","authority.restore"],"verification_intent":["authority_chain_readback","inversion_regression_test"]}'::jsonb,
      '[{"role_key":"OA.ROLE.AUTHORITY_STEWARD","assignment_mode":"PRIMARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.SECURITY_GUARDIAN","assignment_mode":"SECONDARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"SPECIALIST","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.ADMIN.01',
      'administration',
      'Administration 01',
      'Own agent census, lifecycle, genome administration, role assignment integrity, succession, quarantine, and retirement.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Every durable worker has inspectable identity, genome, roles, lifecycle, and successor path.","memory_scope":"operator_administration","capability_intent":["agent.read","agent.hatch","agent.assign_role","agent.lifecycle","agent.audit"],"verification_intent":["registry_readback","assignment_hash_check","lifecycle_transition_test"]}'::jsonb,
      '[{"role_key":"OA.ROLE.AGENT_ADMINISTRATOR","assignment_mode":"PRIMARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.ROLE_ARCHITECT","assignment_mode":"SECONDARY","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.CONTINUITY_CUSTODIAN","assignment_mode":"SPECIALIST","scope":{"domain":"administration"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.MEMORY.12',
      'cognition',
      'Memory 12',
      'Own provenance-aware durable memory promotion, retrieval, contradiction handling, and scoped recall.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Relevant prior knowledge is recovered before work without allowing stale memory to outrank stronger evidence.","memory_scope":"memory_federation","capability_intent":["memory.search","memory.promote","memory.correct","knowledge_graph.read_write"],"verification_intent":["provenance_check","contradiction_visibility_test","retrieval_relevance_eval"]}'::jsonb,
      '[{"role_key":"OA.ROLE.MEMORY_CURATOR","assignment_mode":"PRIMARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.PROVENANCE_RECORDER","assignment_mode":"SECONDARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.CONTEXT_COMPILER","assignment_mode":"SPECIALIST","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.CONTEXT.12',
      'cognition',
      'Context 12',
      'Compile authority-aware, provenance-aware, minimum-sufficient context before reasoning and execution.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Every run starts from the strongest relevant recoverable context rather than prompt-local state.","memory_scope":"cross_domain_context","capability_intent":["memory.search","evidence.resolve","mission.read","continuity.read","context.compile"],"verification_intent":["context_coverage_eval","source_precedence_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.CONTEXT_COMPILER","assignment_mode":"PRIMARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.MEMORY_CURATOR","assignment_mode":"SECONDARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.PROVENANCE_RECORDER","assignment_mode":"SPECIALIST","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.ORCHESTRATION.12',
      'cognition',
      'Orchestration 12',
      'Own mission decomposition, route generation, dependency ownership, work assignment, continuation, and next-best-action selection.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Missions continuously advance through the strongest coherent executable route.","memory_scope":"missions_and_dependencies","capability_intent":["mission.read_write","dependency.resolve","route.rank","agent.delegate","open_loop.manage"],"verification_intent":["route_falsification","dependency_owner_check","mission_progress_readback"]}'::jsonb,
      '[{"role_key":"OA.ROLE.MISSION_ORCHESTRATOR","assignment_mode":"PRIMARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.CAPABILITY_ROUTER","assignment_mode":"SECONDARY","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.OPERATIONS_COORDINATOR","assignment_mode":"SPECIALIST","scope":{"domain":"cognition"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.CAPABILITY.12',
      'runtime',
      'Capability 12',
      'Own live capability discovery, health, eligibility, provider routing, fallbacks, and least-privilege execution selection.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Every executable transition uses the strongest currently eligible capability and preserves fallback routes.","memory_scope":"capability_mesh","capability_intent":["capability.discover","capability.health","route.select","provider.probe","grant.read"],"verification_intent":["live_capability_readback","fallback_route_test","grant_scope_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.CAPABILITY_ROUTER","assignment_mode":"PRIMARY","scope":{"domain":"runtime"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.SECURITY_GUARDIAN","assignment_mode":"SECONDARY","scope":{"domain":"runtime"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.OBSERVABILITY_SENTINEL","assignment_mode":"SPECIALIST","scope":{"domain":"runtime"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.SECURITY.12',
      'security',
      'Security 12',
      'Own least privilege, secret handling, integrity controls, blast-radius limits, and compromise detection.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Execution remains powerful while authority, credentials, and irreversible consequences stay explicitly bounded.","memory_scope":"security_and_integrity","capability_intent":["grant.audit","secret_reference.audit","integrity.verify","risk.assess"],"verification_intent":["least_privilege_test","secret_leak_scan","integrity_attestation"]}'::jsonb,
      '[{"role_key":"OA.ROLE.SECURITY_GUARDIAN","assignment_mode":"PRIMARY","scope":{"domain":"security"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.AUTHORITY_STEWARD","assignment_mode":"SECONDARY","scope":{"domain":"security"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"SPECIALIST","scope":{"domain":"security"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.RECOVERY.12',
      'operations',
      'Recovery 12',
      'Own recovery from partial failure, corruption, provider loss, executor loss, and degraded continuity.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Failure produces verified restoration or an exact preserved boundary, never silent state loss.","memory_scope":"recovery_and_incidents","capability_intent":["continuity.restore","provider.reroute","state.readback","incident.manage"],"verification_intent":["restore_test","post_recovery_readback","continuity_head_verification"]}'::jsonb,
      '[{"role_key":"OA.ROLE.RECOVERY_ENGINEER","assignment_mode":"PRIMARY","scope":{"domain":"operations"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.INCIDENT_COMMANDER","assignment_mode":"SECONDARY","scope":{"domain":"operations"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.CONTINUITY_CUSTODIAN","assignment_mode":"SPECIALIST","scope":{"domain":"operations"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.EMAIL.12',
      'email',
      'Email 12',
      'Own high-context email triage, drafting, routing, sending, provider receipts, follow-up, and thread continuity.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Email obligations advance to verified provider state with correct context and durable follow-up.","memory_scope":"email_threads_and_commitments","capability_intent":["gmail.search","gmail.read","gmail.draft","gmail.send","gmail.label","attachment.read"],"verification_intent":["message_id_receipt","thread_readback","commitment_open_loop_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.EMAIL_OPERATOR","assignment_mode":"PRIMARY","scope":{"domain":"email"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.COMMUNICATIONS_COORDINATOR","assignment_mode":"SECONDARY","scope":{"domain":"email"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.DRAFTING_ENGINE","assignment_mode":"SPECIALIST","scope":{"domain":"email"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECEIPT_AUDITOR","assignment_mode":"SPECIALIST","scope":{"domain":"email"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.TELECOM.12',
      'telecom',
      'Telecom 12',
      'Own calls, SMS, telecom-provider execution, scripts, transcripts, receipts, routing, and follow-up continuity.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Telecom actions are prepared, executed through authorized routes, receipted, and bound to resulting commitments.","memory_scope":"telecom_sessions_and_followups","capability_intent":["telecom.capability_probe","call.prepare","call.execute","sms.execute","transcript.capture","receipt.readback"],"verification_intent":["provider_call_id","provider_message_id","transcript_binding","followup_open_loop_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.TELECOM_OPERATOR","assignment_mode":"PRIMARY","scope":{"domain":"telecom"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.COMMUNICATIONS_COORDINATOR","assignment_mode":"SECONDARY","scope":{"domain":"telecom"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECEIPT_AUDITOR","assignment_mode":"SPECIALIST","scope":{"domain":"telecom"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.DRAFTING.12',
      'drafting',
      'Drafting 12',
      'Own evidence-grounded production drafting across correspondence, reports, complaints, proposals, scripts, and formal documents.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Every draft is complete, source-faithful, audience-fit, internally consistent, and ready for its downstream action.","memory_scope":"drafting_patterns_and_source_context","capability_intent":["context.compile","evidence.resolve","document.compose","citation.bind"],"verification_intent":["source_fidelity_check","completeness_check","audience_constraint_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.DRAFTING_ENGINE","assignment_mode":"PRIMARY","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.DOCUMENT_ENGINEER","assignment_mode":"SECONDARY","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.CONTEXT_COMPILER","assignment_mode":"SPECIALIST","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.DRAFTING.12.12',
      'drafting',
      'Drafting 12.12 Finalization',
      'Own finalization: reconcile source truth, resolve omissions, validate formatting, and produce handoff-ready final artifacts.',
      'OA.DRAFTING.12',
      '1.0.0',
      '{"objective":"A draft becomes a verified final artifact with no known missing required content, broken references, or unverified claims.","memory_scope":"draft_finalization","capability_intent":["document.read","document.render","artifact.compare","citation.verify","finalize"],"verification_intent":["final_render_check","source_coverage_check","artifact_hash","handoff_readiness"]}'::jsonb,
      '[{"role_key":"OA.ROLE.DRAFTING_ENGINE","assignment_mode":"PRIMARY","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.DOCUMENT_ENGINEER","assignment_mode":"SECONDARY","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"SPECIALIST","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECEIPT_AUDITOR","assignment_mode":"SPECIALIST","scope":{"domain":"drafting"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.CASEBUILDING.12',
      'casebuilding',
      'Casebuilding 12',
      'Own cumulative case construction across facts, actors, chronology, claims, defenses, evidence, contradictions, remedies, discovery, and executable next actions.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Case state compounds into source-bound actionable structure instead of resetting into summaries.","memory_scope":"case_graphs_and_source_history","capability_intent":["case.read_write","evidence.search","research.execute","timeline.build","claim.map","artifact.compose"],"verification_intent":["source_binding_check","contradiction_check","chronology_consistency","open_gap_registry"]}'::jsonb,
      '[{"role_key":"OA.ROLE.CASEBUILDER","assignment_mode":"PRIMARY","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.INVESTIGATOR","assignment_mode":"SECONDARY","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.EVIDENCE_ANALYST","assignment_mode":"SPECIALIST","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.LEGAL_RESEARCHER","assignment_mode":"SPECIALIST","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RESEARCHER","assignment_mode":"SPECIALIST","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.DRAFTING_ENGINE","assignment_mode":"SPECIALIST","scope":{"domain":"casebuilding"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.RESEARCH.12',
      'research',
      'Research 12',
      'Own source acquisition, ranking, synthesis, uncertainty tracking, and durable research state for mission-defined questions.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Research produces current, source-ranked answers with explicit uncertainty and reusable provenance.","memory_scope":"research_graph_and_sources","capability_intent":["web.search","workspace.search","source.fetch","citation.bind","knowledge.promote"],"verification_intent":["source_quality_check","freshness_check","claim_citation_coverage"]}'::jsonb,
      '[{"role_key":"OA.ROLE.RESEARCHER","assignment_mode":"PRIMARY","scope":{"domain":"research"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.INVESTIGATOR","assignment_mode":"SECONDARY","scope":{"domain":"research"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.DATA_ANALYST","assignment_mode":"SPECIALIST","scope":{"domain":"research"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.PROVENANCE_RECORDER","assignment_mode":"SPECIALIST","scope":{"domain":"research"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.EVIDENCE.12',
      'evidence',
      'Evidence 12',
      'Own evidence custody, integrity, source identity, transformation lineage, contradiction analysis, and evidentiary relationships.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Original evidence stays intact and every derived finding remains traceable to source objects and transformations.","memory_scope":"evidence_registry_and_custody","capability_intent":["file.hash","evidence.register","evidence.compare","artifact.lineage","metadata.extract"],"verification_intent":["hash_readback","custody_chain_check","original_vs_derivative_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.EVIDENCE_CUSTODIAN","assignment_mode":"PRIMARY","scope":{"domain":"evidence"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.EVIDENCE_ANALYST","assignment_mode":"SECONDARY","scope":{"domain":"evidence"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.PROVENANCE_RECORDER","assignment_mode":"SPECIALIST","scope":{"domain":"evidence"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECEIPT_AUDITOR","assignment_mode":"SPECIALIST","scope":{"domain":"evidence"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.ENGINEERING.12',
      'engineering',
      'Engineering 12',
      'Own architecture-preserving implementation, integration, testing, CI, deployment evidence, and repair across the engineering estate.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"Engineering changes solve the real problem, preserve compatible gains, pass tests, and leave inspectable source/deployment receipts.","memory_scope":"repositories_schemas_ci_and_deployments","capability_intent":["github.read_write","ci.inspect","supabase.migrate","code.test","deployment.readback"],"verification_intent":["tests_pass","ci_receipt","target_state_readback","non_regression"]}'::jsonb,
      '[{"role_key":"OA.ROLE.ENGINEER","assignment_mode":"PRIMARY","scope":{"domain":"engineering"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.GITHUB_STEWARD","assignment_mode":"SECONDARY","scope":{"domain":"engineering"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.SUPABASE_STEWARD","assignment_mode":"SPECIALIST","scope":{"domain":"engineering"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"SPECIALIST","scope":{"domain":"engineering"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );

    perform public.oa_hatch_specialist_v1(
      'OA.VERIFICATION.12',
      'verification',
      'Verification 12',
      'Own independent falsification, readback, receipt reconciliation, regression detection, and completion certification.',
      'OA.OPERATOR',
      '1.0.0',
      '{"objective":"No mission is promoted to verified success unless observable evidence survives independent challenge.","memory_scope":"verification_receipts_and_regressions","capability_intent":["receipt.read","provider.readback","test.execute","diff.inspect","health.inspect"],"verification_intent":["independent_readback","falsification_pass","receipt_match","regression_check"]}'::jsonb,
      '[{"role_key":"OA.ROLE.VERIFIER","assignment_mode":"PRIMARY","scope":{"domain":"verification"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.RECEIPT_AUDITOR","assignment_mode":"SECONDARY","scope":{"domain":"verification"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.OBSERVABILITY_SENTINEL","assignment_mode":"SPECIALIST","scope":{"domain":"verification"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}},{"role_key":"OA.ROLE.SECURITY_GUARDIAN","assignment_mode":"SPECIALIST","scope":{"domain":"verification"},"authority_constraints":{"authority_source":"OPERATOR","no_silent_scope_expansion":true},"continuity_handoff":{"continuity_priority":1,"replacement_executor_must_rehydrate":true}}]'::jsonb,
      'migration:operator_administration_specialists_v1'
    );
end;
$$;

create or replace view public.oa_specialist_agents_v1
with (security_invoker = true)
as
select
  g.logical_agent_id,
  g.parent_logical_agent_id,
  g.domain_key,
  g.display_name,
  g.purpose,
  g.lifecycle,
  g.current_version,
  g.continuity_priority,
  h.continuity_head_id,
  h.sequence as continuity_sequence,
  h.verified as continuity_verified,
  coalesce(
    jsonb_agg(
      jsonb_build_object(
        'role_key',er.role_key,
        'display_name',er.display_name,
        'assignment_mode',er.assignment_mode,
        'role_version',er.role_version,
        'contract_sha256',er.contract_sha256
      )
      order by
        case er.assignment_mode
          when 'PRIMARY' then 1
          when 'SECONDARY' then 2
          when 'SPECIALIST' then 3
          when 'MISSION_SCOPED' then 4
          else 5
        end,
        er.role_key
    ) filter (where er.role_key is not null),
    '[]'::jsonb
  ) as role_stack
from public.oa_agent_genomes_v1 g
left join public.oa_current_continuity_heads_v1 h
  on h.logical_agent_id = g.logical_agent_id
left join public.oa_effective_agent_roles_v1 er
  on er.logical_agent_id = g.logical_agent_id
where g.logical_agent_id ~ '^OA\.(CONTINUITY|AUTHORITY|ADMIN|MEMORY|CONTEXT|ORCHESTRATION|CAPABILITY|SECURITY|RECOVERY|EMAIL|TELECOM|DRAFTING|CASEBUILDING|RESEARCH|EVIDENCE|ENGINEERING|VERIFICATION)\.'
group by
  g.logical_agent_id,g.parent_logical_agent_id,g.domain_key,g.display_name,
  g.purpose,g.lifecycle,g.current_version,g.continuity_priority,
  h.continuity_head_id,h.sequence,h.verified;

revoke all on public.oa_specialist_agents_v1 from anon, authenticated;
grant select on public.oa_specialist_agents_v1 to service_role;

comment on function public.oa_hatch_specialist_v1(text,text,text,text,text,text,jsonb,jsonb,text) is
  'Hatches a continuity-first logical specialist and composes versioned roles without coupling identity to a runtime executor.';
comment on function public.oa_assign_role_v1(text,text,text,text,jsonb,jsonb,jsonb,text) is
  'Assigns an active versioned role under bounded authority and records an append-only administrative event.';
comment on view public.oa_specialist_agents_v1 is
  'Current founding specialist cohort with verified continuity heads and composed role stacks.';
