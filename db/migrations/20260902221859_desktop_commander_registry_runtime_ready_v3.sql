insert into public.connector_registry_v2(
  connector_key,display_name,connector_class,canonical_role,authority_tier,
  read_enabled,write_enabled,sync_enabled,search_enabled,trigger_enabled,audit_enabled,
  destructive_actions_allowed,public_share_allowed,
  health_status,last_checked_at,owner_scope,notes,metadata,
  lifecycle_state,authentication_state,canonical_source_ref,approved_roots,
  sensitivity_ceiling,last_successful_probe_at,last_successful_probe_receipt_ref,
  freshness_status,provenance_coverage,idempotency_strategy,error_state,
  owner,next_human_gate,connector_quality,data_quality,updated_at,last_upgraded_at
) values
(
  'desktop_commander.glacier',
  'Glacier Desktop Commander',
  'local_execution_plane',
  'batch_compute_lane',
  3,
  false,false,false,false,false,true,
  false,false,
  'source_runtime_ready',
  now(),
  'operator',
  'UDC source and Supabase bridge runtime are verified. Physical-device execution remains non-selectable until enrollment, approved roots, signed heartbeat, and a read-only claimed-job receipt are observed.',
  jsonb_build_object(
    'repository','GlacierEQ/UDC',
    'source_branch','main',
    'source_merge_commit','07ca4b4bd50d9ec6c368a2579c3032c1648798cf',
    'source_pr',2,
    'worker_id','glacier-desktop-commander',
    'batch_lane','desktop_commander',
    'live_endpoint',false,
    'physical_device_online',false,
    'selection_enabled',false,
    'security_posture','require_device_binding_and_approved_roots_before_activation',
    'source_capabilities',jsonb_build_array(
      'local.read','local.search','local.test','local.build','local.scan','local.edit'
    ),
    'source_validation',jsonb_build_object(
      'action','udc-supabase-bridge-ci',
      'adapter','node-ci',
      'validated_source_sha','8bbf1c7751ec0ebbdcc4f98d6fc48f3adb00c048',
      'action_face_run_id',33686159662,
      'immutable_result_path','results/udc-bridge-ci-20260902-2142.json',
      'result_blob_sha','4726ae19cd00e8b331114d0592ccad03c58cfd86',
      'npm_ci_exit',0,
      'typescript_noemit_exit',0,
      'tests_exit',0,
      'build_exit',0,
      'bridge_policy_tests','passed'
    ),
    'keymaster_admission',jsonb_build_object(
      'bootstrap_ref','kb_4c41dc5c421c4d46af18845906e737fc',
      'repository','GlacierEQ/UDC',
      'receipt_id','79d49324-645e-401d-9137-95fb481ca38f',
      'permissions_ceiling','contents:read',
      'wildcard_added',false
    ),
    'backend_bridge',jsonb_build_object(
      'function','apex-desktop-commander-bridge',
      'version',2,
      'sha256','55c0c92e8bb708a0ef358d301018fe3a78e73734c2a890b87461f64615e6ac3e'
    )
  ),
  'connected',
  'authenticated',
  'github:GlacierEQ/UDC',
  '[]'::jsonb,
  'confidential',
  now(),
  'github-actions:33686159662',
  'fresh',
  jsonb_build_object(
    'status','strong',
    'receipt_ref','github-actions:33686159662',
    'covered_fields',jsonb_build_array(
      'source_repository','source_sha','merge_commit','node_ci_result',
      'edge_runtime_sha','migration_versions','keymaster_admission'
    )
  ),
  jsonb_build_object(
    'status','strong',
    'expression','signed_request_nonce_plus_queue_idempotency_key_plus_exact_sha_ci_receipt',
    'receipt_ref','results/udc-bridge-ci-20260902-2142.json'
  ),
  jsonb_build_object(
    'code',null,
    'status','none',
    'observed_at',now(),
    'receipt_ref','github-actions:33686159662'
  ),
  'GlacierEQ',
  'physical_device_enrollment_then_approved_roots_then_signed_heartbeat_then_read_only_job',
  jsonb_build_object(
    'score',94,
    'status','source_runtime_verified_device_unbound',
    'evidence',jsonb_build_array(
      'UDC main merge read back',
      'public Action Face exact-SHA node-ci passed',
      'Supabase bridge source matches deployed v2 bytes',
      'three applied migrations match source exactly',
      'Keymaster UDC admission is explicit and non-wildcard'
    )
  ),
  jsonb_build_object(
    'score',96,
    'status','strong_source_runtime_evidence',
    'evidence',jsonb_build_array(
      'exact source SHA',
      'immutable private CI result',
      'deployed Edge SHA',
      'migration-ledger parity',
      'append-only backend receipts'
    ),
    'dimensions',jsonb_build_object(
      'lineage',1,'validity',1,'timeliness',1,'uniqueness',1,
      'consistency',1,'completeness',0.85,'duplicate_risk',0
    )
  ),
  now(),
  now()
),
(
  'github.actions.public_runner',
  'GitHub Actions Public Runner',
  'execution_plane',
  'public_actions_execution_face',
  2,
  true,false,false,false,true,true,
  false,false,
  'healthy',
  now(),
  'operator',
  'Public GitHub Actions execution face for GlacierEQ workloads. Private workload repositories remain non-executing and are checked out at exact SHA through short-lived one-repository Keymaster tokens.',
  jsonb_build_object(
    'repository','GlacierEQ/public-actions-runner-host',
    'visibility','public',
    'private_repo_actions_forbidden',true,
    'private_control_plane_workflows_allowed',false,
    'preferred_runner','ubuntu-latest',
    'credential_path','github_oidc_to_keymaster_to_one_repo_installation_token',
    'persist_credentials',false,
    'detailed_receipt_plane','GlacierEQ/llm-runner-teams',
    'sanitized_public_status',true,
    'capacity_observation',jsonb_build_object(
      'state','available_but_constrained',
      'successful_udc_run',33686159662
    ),
    'current_udc_job',jsonb_build_object(
      'job_id','udc-bridge-ci-20260902-2142',
      'action','udc-supabase-bridge-ci',
      'source_repo','GlacierEQ/UDC',
      'source_sha','8bbf1c7751ec0ebbdcc4f98d6fc48f3adb00c048',
      'source_merge_commit','07ca4b4bd50d9ec6c368a2579c3032c1648798cf',
      'queue_commit','ebcdb67c86bcba84a37590fad5f20ff082562224',
      'action_face_run_id',33686159662,
      'run_status','success',
      'immutable_result_path','results/udc-bridge-ci-20260902-2142.json',
      'keymaster_admission_receipt','79d49324-645e-401d-9137-95fb481ca38f'
    )
  ),
  'connected',
  'authenticated',
  'repo:GlacierEQ/public-actions-runner-host',
  '["repo:GlacierEQ/public-actions-runner-host","repo:GlacierEQ/llm-runner-teams","repo:GlacierEQ/*:contents_read_ephemeral"]'::jsonb,
  'internal',
  now(),
  'github-actions:33686159662',
  'fresh',
  jsonb_build_object(
    'status','strong',
    'receipt_ref','results/udc-bridge-ci-20260902-2142.json',
    'covered_fields',jsonb_build_array(
      'execution_repo','job_id','workload_repo','workload_sha','workflow_run_id','token_revocation'
    )
  ),
  jsonb_build_object(
    'status','strong',
    'expression','one_job_id_one_private_claim_one_private_result_exact_source_sha',
    'receipt_ref','job:udc-bridge-ci-20260902-2142'
  ),
  '{}'::jsonb,
  'GlacierEQ',
  'none_for_udc_exact_sha_validation',
  jsonb_build_object(
    'score',99,
    'status','runtime_verified_public_action_face',
    'evidence',jsonb_build_array(
      'public runner exact-SHA checkout verified',
      'OIDC-Keymaster token path verified',
      'node-ci completed successfully',
      'private immutable result published',
      'workload and control tokens revoked'
    )
  ),
  jsonb_build_object(
    'score',98,
    'status','strong',
    'evidence',jsonb_build_array(
      'exact SHA bound','job envelope persisted','public/private boundary explicit'
    ),
    'dimensions',jsonb_build_object(
      'lineage',1,'validity',1,'timeliness',1,'uniqueness',1,
      'consistency',1,'completeness',0.95,'duplicate_risk',0
    )
  ),
  now(),
  now()
)
on conflict(connector_key) do update set
  display_name=excluded.display_name,
  connector_class=excluded.connector_class,
  canonical_role=excluded.canonical_role,
  authority_tier=excluded.authority_tier,
  read_enabled=excluded.read_enabled,
  write_enabled=excluded.write_enabled,
  sync_enabled=excluded.sync_enabled,
  search_enabled=excluded.search_enabled,
  trigger_enabled=excluded.trigger_enabled,
  audit_enabled=excluded.audit_enabled,
  destructive_actions_allowed=excluded.destructive_actions_allowed,
  public_share_allowed=excluded.public_share_allowed,
  health_status=excluded.health_status,
  last_checked_at=excluded.last_checked_at,
  last_upgraded_at=excluded.last_upgraded_at,
  owner_scope=excluded.owner_scope,
  notes=excluded.notes,
  metadata=excluded.metadata,
  lifecycle_state=excluded.lifecycle_state,
  authentication_state=excluded.authentication_state,
  canonical_source_ref=excluded.canonical_source_ref,
  approved_roots=excluded.approved_roots,
  sensitivity_ceiling=excluded.sensitivity_ceiling,
  last_successful_probe_at=excluded.last_successful_probe_at,
  last_successful_probe_receipt_ref=excluded.last_successful_probe_receipt_ref,
  freshness_status=excluded.freshness_status,
  provenance_coverage=excluded.provenance_coverage,
  idempotency_strategy=excluded.idempotency_strategy,
  error_state=excluded.error_state,
  owner=excluded.owner,
  next_human_gate=excluded.next_human_gate,
  connector_quality=excluded.connector_quality,
  data_quality=excluded.data_quality,
  updated_at=excluded.updated_at;

insert into public.connector_capability_matrix_v2(
  connector_key,capability,capability_level,verified,verification_source,
  risk_level,notes,metadata,last_verified_at,updated_at
) values
(
  'desktop_commander.glacier','local_batch_worker_source',3,true,
  'github-actions:33686159662','high',
  'UDC source, TypeScript, policy tests, and build are verified at an exact private source SHA. Physical-device execution is a separate unverified capability.',
  jsonb_build_object(
    'worker_id','glacier-desktop-commander',
    'selection_enabled',false,
    'source_sha','8bbf1c7751ec0ebbdcc4f98d6fc48f3adb00c048'
  ),
  now(),now()
),
(
  'desktop_commander.glacier','signed_local_agent_bridge',4,true,
  'supabase-runtime-parity+github-actions:33686159662','high',
  'Signed Ed25519 outbound local-agent bridge and backend replay controls are source/runtime verified; physical device enrollment is still pending.',
  jsonb_build_object(
    'function','apex-desktop-commander-bridge',
    'version',2,
    'sha256','55c0c92e8bb708a0ef358d301018fe3a78e73734c2a890b87461f64615e6ac3e'
  ),
  now(),now()
),
(
  'desktop_commander.glacier','approved_root_enforcement',4,true,
  'github-actions:33686159662','high',
  'Remote bridge policy requires backend-approved roots and rejects path escape.',
  jsonb_build_object('selection_enabled',false),
  now(),now()
),
(
  'desktop_commander.glacier','compare_before_write',4,true,
  'github-actions:33686159662','high',
  'Remote write_file and edit_block require expected_before_sha before execution.',
  jsonb_build_object('operations',jsonb_build_array('write_file','edit_block')),
  now(),now()
),
(
  'desktop_commander.glacier','physical_device_execution',4,false,
  'runtime-required','high',
  'Physical UDC device has not yet enrolled, heartbeated, or completed a claimed Backend Ops job.',
  jsonb_build_object(
    'selection_enabled',false,
    'next_gate','physical_device_enrollment_then_approved_roots_then_signed_heartbeat_then_read_only_job'
  ),
  null,now()
),
(
  'github.actions.public_runner','exact_sha_private_workload',5,true,
  'github-actions:33686159662','medium',
  'Public Action Face successfully checked out and bound a private UDC workload to an exact source SHA.',
  jsonb_build_object('source_repo','GlacierEQ/UDC','source_sha','8bbf1c7751ec0ebbdcc4f98d6fc48f3adb00c048'),
  now(),now()
),
(
  'github.actions.public_runner','oidc_keymaster_one_repo_token',5,true,
  'github-actions:33686159662','medium',
  'GitHub OIDC to Keymaster minted one-repository workload and control tokens and revoked them after use.',
  jsonb_build_object('persist_credentials',false,'keymaster_admission_receipt','79d49324-645e-401d-9137-95fb481ca38f'),
  now(),now()
),
(
  'github.actions.public_runner','immutable_private_result',5,true,
  'github-actions:33686159662','low',
  'Detailed private workload result was published to the non-executing private control plane and bound to immutable claim/provenance.',
  jsonb_build_object('result_path','results/udc-bridge-ci-20260902-2142.json'),
  now(),now()
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

