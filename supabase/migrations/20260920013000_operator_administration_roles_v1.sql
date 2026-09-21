create table if not exists public.oa_roles_v1 (
  role_key text primary key,
  family text not null,
  display_name text not null,
  purpose text not null,
  win_condition text not null,
  lifecycle text not null default 'ACTIVE'
    check (lifecycle in ('DRAFT','ACTIVE','DEPRECATED','RETIRED')),
  continuity_priority smallint not null default 1 check (continuity_priority = 1),
  assignable boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.oa_role_versions_v1 (
  role_version_id uuid primary key default gen_random_uuid(),
  role_key text not null references public.oa_roles_v1(role_key) on delete restrict,
  version text not null,
  contract jsonb not null,
  contract_sha256 text not null check (contract_sha256 ~ '^[0-9a-f]{64}$'),
  activation_status text not null default 'ACTIVE'
    check (activation_status in ('CANDIDATE','ACTIVE','SUPERSEDED','RETIRED')),
  previous_version_id uuid null references public.oa_role_versions_v1(role_version_id) on delete restrict,
  created_by text not null,
  created_source_class text not null check (created_source_class in ('OPERATOR','AGENT','SYSTEM','EVIDENCE','MIGRATION')),
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  unique (role_key, version),
  check (
    contract ->> 'schema' = 'glaciereq.operator-role.v1'
    and jsonb_typeof(contract -> 'loci') = 'object'
    and (contract -> 'loci') ?& array[
      'continuity','purpose','win_condition','authority','jurisdiction',
      'reasoning','execution','capability','memory_context','evidence_provenance',
      'verification','communication','escalation','handoff','observability',
      'security_risk','lifecycle'
    ]
  )
);

create table if not exists public.oa_role_inheritance_v1 (
  child_role_key text not null references public.oa_roles_v1(role_key) on delete restrict,
  parent_role_key text not null references public.oa_roles_v1(role_key) on delete restrict,
  relation text not null default 'INHERITS'
    check (relation in ('INHERITS','COMPOSES','SPECIALIZES')),
  precedence integer not null default 100,
  created_at timestamptz not null default now(),
  primary key (child_role_key, parent_role_key, relation),
  check (child_role_key <> parent_role_key)
);

create table if not exists public.oa_agent_role_assignments_v1 (
  assignment_id uuid primary key default gen_random_uuid(),
  logical_agent_id text not null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  role_key text not null references public.oa_roles_v1(role_key) on delete restrict,
  role_version_id uuid not null references public.oa_role_versions_v1(role_version_id) on delete restrict,
  assignment_mode text not null default 'PRIMARY'
    check (assignment_mode in ('PRIMARY','SECONDARY','SPECIALIST','MISSION_SCOPED','TEMPORARY')),
  mission_ref text,
  scope jsonb not null default '{}'::jsonb,
  authority_constraints jsonb not null default '{}'::jsonb,
  continuity_handoff jsonb not null default '{}'::jsonb,
  status text not null default 'ACTIVE'
    check (status in ('ACTIVE','SUSPENDED','REVOKED','SUPERSEDED','EXPIRED')),
  assigned_by text not null,
  assigned_source_class text not null check (assigned_source_class in ('OPERATOR','AGENT','SYSTEM','EVIDENCE','MIGRATION')),
  assigned_at timestamptz not null default now(),
  valid_until timestamptz,
  revoked_at timestamptz,
  assignment_sha256 text not null check (assignment_sha256 ~ '^[0-9a-f]{64}$')
);

create unique index if not exists oa_agent_one_primary_role_v1
  on public.oa_agent_role_assignments_v1(logical_agent_id)
  where assignment_mode = 'PRIMARY' and status = 'ACTIVE' and mission_ref is null;

create index if not exists oa_agent_role_active_idx
  on public.oa_agent_role_assignments_v1(logical_agent_id, status, role_key);

create index if not exists oa_role_versions_current_idx
  on public.oa_role_versions_v1(role_key, activation_status, created_at desc);

create or replace function public.oa_validate_role_content_hash_v1()
returns trigger
language plpgsql
set search_path = pg_catalog, public, extensions
as $$
declare
  v_expected text;
begin
  if tg_table_name = 'oa_role_versions_v1' then
    v_expected := encode(digest(jsonb_strip_nulls(new.contract)::text, 'sha256'), 'hex');
    if new.contract_sha256 <> v_expected then
      raise exception 'contract_sha256 does not match role contract';
    end if;
  elsif tg_table_name = 'oa_agent_role_assignments_v1' then
    v_expected := encode(
      digest(
        jsonb_strip_nulls(
          jsonb_build_object(
            'logical_agent_id',new.logical_agent_id,
            'role_key',new.role_key,
            'role_version_id',new.role_version_id,
            'assignment_mode',new.assignment_mode,
            'mission_ref',new.mission_ref,
            'scope',new.scope,
            'authority_constraints',new.authority_constraints,
            'continuity_handoff',new.continuity_handoff,
            'assigned_by',new.assigned_by
          )
        )::text,
        'sha256'
      ),
      'hex'
    );
    if new.assignment_sha256 <> v_expected then
      raise exception 'assignment_sha256 does not match role assignment payload';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists oa_role_versions_hash_check_v1 on public.oa_role_versions_v1;
create trigger oa_role_versions_hash_check_v1
before insert on public.oa_role_versions_v1
for each row execute function public.oa_validate_role_content_hash_v1();

drop trigger if exists oa_role_assignments_hash_check_v1 on public.oa_agent_role_assignments_v1;
create trigger oa_role_assignments_hash_check_v1
before insert on public.oa_agent_role_assignments_v1
for each row execute function public.oa_validate_role_content_hash_v1();

create or replace view public.oa_current_role_versions_v1
with (security_invoker = true)
as
select distinct on (v.role_key)
  v.role_version_id,
  v.role_key,
  v.version,
  v.contract,
  v.contract_sha256,
  v.activation_status,
  v.created_by,
  v.created_source_class,
  v.created_at,
  v.activated_at
from public.oa_role_versions_v1 v
where v.activation_status = 'ACTIVE'
order by v.role_key, v.created_at desc;

create or replace view public.oa_effective_agent_roles_v1
with (security_invoker = true)
as
select
  a.logical_agent_id,
  a.role_key,
  r.family,
  r.display_name,
  r.purpose,
  r.win_condition,
  a.assignment_mode,
  a.mission_ref,
  a.scope,
  a.authority_constraints,
  a.continuity_handoff,
  a.status,
  a.assigned_by,
  a.assigned_source_class,
  a.assigned_at,
  a.valid_until,
  rv.version as role_version,
  rv.contract_sha256
from public.oa_agent_role_assignments_v1 a
join public.oa_roles_v1 r on r.role_key = a.role_key
join public.oa_role_versions_v1 rv on rv.role_version_id = a.role_version_id
where a.status = 'ACTIVE'
  and (a.valid_until is null or a.valid_until > now());

alter table public.oa_roles_v1 enable row level security;
alter table public.oa_role_versions_v1 enable row level security;
alter table public.oa_role_inheritance_v1 enable row level security;
alter table public.oa_agent_role_assignments_v1 enable row level security;

revoke all on public.oa_roles_v1 from anon, authenticated;
revoke all on public.oa_role_versions_v1 from anon, authenticated;
revoke all on public.oa_role_inheritance_v1 from anon, authenticated;
revoke all on public.oa_agent_role_assignments_v1 from anon, authenticated;
revoke all on public.oa_current_role_versions_v1 from anon, authenticated;
revoke all on public.oa_effective_agent_roles_v1 from anon, authenticated;

grant all on public.oa_roles_v1 to service_role;
grant all on public.oa_role_versions_v1 to service_role;
grant all on public.oa_role_inheritance_v1 to service_role;
grant all on public.oa_agent_role_assignments_v1 to service_role;
grant select on public.oa_current_role_versions_v1 to service_role;
grant select on public.oa_effective_agent_roles_v1 to service_role;

with seed(role_key,family,display_name,purpose,win_condition) as (
  values
    ('OA.ROLE.CONTINUITY_CUSTODIAN','administration','Continuity Custodian','Preserve resumable identity, mission state, open loops, lineage, and verified recovery heads across executor changes.','A replacement executor can resume the exact next verified transition without asking the Operator to reconstruct prior state.'),
    ('OA.ROLE.AUTHORITY_STEWARD','administration','Authority Steward','Maintain delegation, jurisdiction, revocation, authority inversion detection, and restoration under Operator root authority.','Every consequential action has a valid authority chain; subordinate state never silently supersedes the Operator.'),
    ('OA.ROLE.AGENT_ADMINISTRATOR','administration','Agent Administrator','Administer agent identities, lifecycle, genomes, assignments, succession, quarantine, and retirement.','Every durable agent has an inspectable identity, active genome, accountable role set, lifecycle state, and successor path.'),
    ('OA.ROLE.ROLE_ARCHITECT','administration','Role Architect','Design, version, validate, and evolve role contracts and inheritance without conflating roles with executors.','Responsibilities are explicit, non-colliding, inherited deliberately, versioned, and independently assignable.'),
    ('OA.ROLE.MEMORY_CURATOR','cognition','Memory Curator','Promote, scope, reconcile, deprecate, and retrieve durable memory with provenance and contradiction visibility.','Needed historical context is recoverable, source-bound, scoped correctly, and does not overwrite stronger evidence.'),
    ('OA.ROLE.CONTEXT_COMPILER','cognition','Context Compiler','Compile the smallest sufficient authority-aware context package before execution.','Every run receives relevant current instructions, state, memory, evidence, constraints, capabilities, and unresolved contradictions.'),
    ('OA.ROLE.MISSION_ORCHESTRATOR','cognition','Mission Orchestrator','Decompose desired state into typed work, dependencies, routes, assignments, and continuation.','The mission continuously advances through the strongest available valid route and no local block becomes a global stop.'),
    ('OA.ROLE.CAPABILITY_ROUTER','runtime','Capability Router','Resolve available tools, providers, connectors, permissions, freshness, fallbacks, and route eligibility.','Every executable transition is routed through the strongest currently eligible capability with explicit fallback semantics.'),
    ('OA.ROLE.EXECUTION_WORKER','runtime','Execution Worker','Perform bounded side effects under delegated authority with idempotency and readback.','Authorized actions are actually executed, externally receipted where possible, and never confused with plans or attempts.'),
    ('OA.ROLE.EVIDENCE_CUSTODIAN','evidence','Evidence Custodian','Preserve original evidentiary objects, hashes, custody, derivatives, and source relationships.','Original evidence remains distinguishable, integrity-checkable, source-bound, and traceable through every transform.'),
    ('OA.ROLE.PROVENANCE_RECORDER','evidence','Provenance Recorder','Record source, transformation, lineage, decision basis, and provider-native identifiers.','Material claims, artifacts, decisions, and actions can be reconstructed back to their authoritative sources.'),
    ('OA.ROLE.RECEIPT_AUDITOR','verification','Receipt Auditor','Verify provider-native receipts, hashes, readback, and claimed external state.','No externally consequential action is accepted as verified without matching provider/readback evidence when available.'),
    ('OA.ROLE.VERIFIER','verification','Verifier','Independently test, falsify, read back, and certify claimed outcomes.','Attempted, executed, and verified remain distinct; terminal success survives independent challenge.'),
    ('OA.ROLE.OBSERVABILITY_SENTINEL','operations','Observability Sentinel','Monitor health, telemetry, failures, latency, backlog, continuity, and anomalous state.','Degradation is surfaced with actionable evidence before it silently becomes continuity or execution failure.'),
    ('OA.ROLE.SECURITY_GUARDIAN','security','Security Guardian','Protect secrets, permissions, blast radius, integrity, least privilege, and compromise response.','Capabilities are bounded to legitimate scope; secrets remain out of logs; integrity and privilege violations are detectable.'),
    ('OA.ROLE.RECOVERY_ENGINEER','operations','Recovery Engineer','Restore service, state, identity, routes, and continuity after partial or catastrophic failure.','Recovery produces verified working state from durable records without erasing history or silently weakening guarantees.'),
    ('OA.ROLE.INCIDENT_COMMANDER','operations','Incident Commander','Coordinate high-priority incident diagnosis, containment, repair, verification, and communication.','A degraded system converges toward verified recovery with ownership, priorities, evidence, and unresolved risks visible.'),
    ('OA.ROLE.EMAIL_OPERATOR','communications','Email Operator','Recover thread context, triage, draft, route, send, label, preserve attachments, and track replies/commitments.','Email obligations advance with correct context, bounded authority, provider message IDs, follow-up state, and durable thread continuity.'),
    ('OA.ROLE.TELECOM_OPERATOR','communications','Telecom Operator','Manage calls, SMS, telecom providers, call preparation, transcripts, receipts, routing, and follow-up.','Telecom actions are attributable, receipted, continuity-preserving, and linked to the mission and resulting commitments.'),
    ('OA.ROLE.DRAFTING_ENGINE','documents','Drafting Engine','Produce mission-bound polished written artifacts from verified context, evidence, constraints, and audience requirements.','Drafts are complete, source-faithful, audience-fit, internally consistent, and ready for the intended downstream action.'),
    ('OA.ROLE.CASEBUILDER','casework','Casebuilder','Construct cumulative case graphs of facts, actors, chronology, claims, defenses, evidence, contradictions, remedies, and next actions.','Case state compounds rather than resets; every material proposition is source-bound and actionable gaps remain explicit.'),
    ('OA.ROLE.RESEARCHER','research','Researcher','Acquire and synthesize reliable external or internal sources for a defined question.','Research answers the actual question with current, relevant, source-ranked evidence and preserved uncertainty.'),
    ('OA.ROLE.LEGAL_RESEARCHER','research','Legal Researcher','Research statutes, regulations, cases, procedures, authorities, and legal propositions for a defined jurisdiction and date.','Legal propositions are tied to current controlling or persuasive authority, jurisdiction, procedural posture, and limitations.'),
    ('OA.ROLE.EVIDENCE_ANALYST','evidence','Evidence Analyst','Analyze evidence for facts, contradictions, temporal relationships, actors, authenticity, and claim support.','Evidence-derived findings are distinguishable from inference and linked back to exact source objects and transformations.'),
    ('OA.ROLE.DOCUMENT_ENGINEER','documents','Document Engineer','Create, transform, assemble, validate, and preserve production documents and packets.','Final documents are structurally valid, complete, rendered correctly, source-traceable, and ready for delivery.'),
    ('OA.ROLE.DATA_ANALYST','analysis','Data Analyst','Transform, analyze, model, and visualize structured data with reproducible methods.','Quantitative conclusions are reproducible from identified inputs and calculations, with data-quality limitations explicit.'),
    ('OA.ROLE.ENGINEER','engineering','Engineer','Design, implement, test, integrate, and maintain software and infrastructure changes.','Changes solve the defined problem, preserve compatible architecture, pass verification, and leave inspectable deployment/source receipts.'),
    ('OA.ROLE.GITHUB_STEWARD','engineering','GitHub Steward','Administer repositories, branches, commits, PRs, issues, CI bindings, and source authority.','Repository state remains coherent, reviewable, verifiable, and connected to its operational deployment/control-plane state.'),
    ('OA.ROLE.SUPABASE_STEWARD','engineering','Supabase Steward','Administer schemas, migrations, RLS, functions, operational state, health, and database integrity.','Database changes are migration-backed, least-privilege, read back, advisor-checked, and consistent with source authority.'),
    ('OA.ROLE.FILE_CUSTODIAN','operations','File Custodian','Discover, classify, organize, preserve, deduplicate, version, and route files without losing provenance.','Files remain findable, correctly scoped, non-destructively organized, and traceable to their source and consuming missions.'),
    ('OA.ROLE.NOTION_STEWARD','operations','Notion Steward','Maintain human-readable workspace projections, databases, pages, and dashboards from authoritative state.','Notion remains a useful operator projection without becoming an accidental source of underlying execution truth.'),
    ('OA.ROLE.COMMUNICATIONS_COORDINATOR','communications','Communications Coordinator','Coordinate cross-channel outbound/inbound communication, commitments, routing, timing, and follow-up.','Communications stay consistent across channels and every external commitment has an owner, state, and next action.'),
    ('OA.ROLE.INVESTIGATOR','research','Investigator','Reconstruct actors, events, relationships, records, anomalies, and unresolved questions from source-bearing evidence.','Investigative hypotheses remain separated from verified facts while missing custodians, records, and next acquisition steps are explicit.'),
    ('OA.ROLE.CALENDAR_SCHEDULER','operations','Calendar Scheduler','Manage deadlines, events, availability, reminders, temporal dependencies, and schedule commitments.','Time-bound obligations are correctly represented, conflict-aware, linked to missions, and not silently missed.'),
    ('OA.ROLE.OPERATIONS_COORDINATOR','operations','Operations Coordinator','Coordinate miscellaneous operational work that spans domains without stealing specialized authority.','Cross-domain work advances with clear ownership, dependencies, handoffs, and verified closure.'),
    ('OA.ROLE.CAPACITY_PLANNER','infrastructure','Capacity Planner','Plan resource capacity requirements from observed demand and constraints.','Capacity decisions are evidence-based, bounded, and verified against actual utilization and service requirements.'),
    ('OA.ROLE.CONFIG_VALIDATOR','infrastructure','Config Validator','Validate configuration changes against schemas, invariants, compatibility, and deployment constraints.','Invalid or drifting configuration is caught before it can corrupt runtime or continuity.'),
    ('OA.ROLE.DEPENDENCY_TRACKER','infrastructure','Dependency Tracker','Track service, repository, provider, data, and execution dependencies.','Dependencies have explicit owners, state, freshness, and impact so blockers route correctly.'),
    ('OA.ROLE.DEPLOYMENT_COORDINATOR','infrastructure','Deployment Coordinator','Coordinate releases, migrations, environment promotion, rollback, and deployment verification.','Deployments are attributable, reversible where possible, and verified against target-state readback.'),
    ('OA.ROLE.METRIC_COLLECTOR','infrastructure','Metric Collector','Collect and aggregate structured operational metrics.','Metrics are fresh, attributable, correctly scoped, and usable by health and verification systems.'),
    ('OA.ROLE.SERVICE_MONITOR','infrastructure','Service Monitor','Monitor service availability and health.','Service degradation is detected with timely, inspectable evidence.'),
    ('OA.ROLE.AUTO_SCALER','infrastructure','Auto Scaler','Adjust resource scale within bounded policy from verified demand signals.','Scaling actions preserve availability, stay within limits, and produce observable before/after state.'),
    ('OA.ROLE.CHAOS_ENGINEER','infrastructure','Chaos Engineer','Test resilience through controlled, bounded fault injection.','Resilience assumptions are challenged without uncontrolled blast radius and recovery behavior is measured.'),
    ('OA.ROLE.CIRCUIT_BREAKER','infrastructure','Circuit Breaker','Protect systems from repeated failing dependencies while preserving alternate routes.','Repeated failure is contained locally and eligible fallback routes remain available.'),
    ('OA.ROLE.SELF_HEALER','infrastructure','Self Healer','Repair known operational failures automatically within bounded authority.','Known failures are repaired with evidence, idempotency, verification, and escalation on uncertainty.'),
    ('OA.ROLE.LEARNING_AGENT','infrastructure','Learning Agent','Learn from verified outcomes and corrections to improve future routing and execution.','Only validated outcomes change durable behavior, with provenance and rollback of defective learning.'),
    ('OA.ROLE.COST_OPTIMIZER','infrastructure','Cost Optimizer','Identify cost-reduction opportunities without violating mission or reliability requirements.','Savings are quantified, reversible where possible, and never silently trade away required capability.'),
    ('OA.ROLE.ANOMALY_DETECTOR','infrastructure','Anomaly Detector','Detect statistically or semantically unusual operational behavior.','Anomalies are surfaced with evidence and uncertainty without being mislabeled as confirmed incidents.'),
    ('OA.ROLE.PERFORMANCE_OPTIMIZER','infrastructure','Performance Optimizer','Identify and improve performance bottlenecks from measured evidence.','Performance changes show verified improvement without regressing correctness, continuity, or reliability.'),
    ('OA.ROLE.PREDICTIVE_ALERTING','infrastructure','Predictive Alerting','Forecast likely incidents from current and historical telemetry.','Predictions are calibrated, attributable to signals, and routed as anticipatory evidence rather than facts.'),
    ('OA.ROLE.ALERT_MANAGER','infrastructure','Alert Manager','Route, deduplicate, prioritize, and track alerts.','Important alerts reach the correct owner with state and follow-up while noise is controlled transparently.'),
    ('OA.ROLE.HEALTH_CHECKER','infrastructure','Health Checker','Perform deep health checks across required system surfaces.','Health claims are based on live readback and required dependency verification, not static configuration.'),
    ('OA.ROLE.LOG_ANALYZER','infrastructure','Log Analyzer','Analyze operational logs for failures, patterns, correlations, and evidence.','Log-derived findings are reproducible, time-scoped, and linked to underlying events and systems.')
)
insert into public.oa_roles_v1(role_key,family,display_name,purpose,win_condition)
select * from seed
on conflict (role_key) do update
set family = excluded.family,
    display_name = excluded.display_name,
    purpose = excluded.purpose,
    win_condition = excluded.win_condition,
    updated_at = now();

do $$
declare
  r record;
  v_contract jsonb;
  v_hash text;
begin
  for r in
    select role_key, family, display_name, purpose, win_condition
    from public.oa_roles_v1
    where role_key like 'OA.ROLE.%'
  loop
    if not exists (
      select 1 from public.oa_role_versions_v1
      where role_key = r.role_key and version = '1.0.0'
    ) then
      v_contract := jsonb_build_object(
        'schema','glaciereq.operator-role.v1',
        'role_key',r.role_key,
        'family',r.family,
        'display_name',r.display_name,
        'loci',jsonb_build_object(
          'continuity',jsonb_build_object(
            'position',1,
            'logical_role_survives_agent_reassignment',true,
            'open_loops_transfer_with_role_scope',true,
            'handoff_required_before_reassignment',true
          ),
          'purpose',jsonb_build_object('statement',r.purpose),
          'win_condition',jsonb_build_object('statement',r.win_condition),
          'authority',jsonb_build_object(
            'root','OPERATOR',
            'role_does_not_create_authority',true,
            'assignment_requires_delegation',true,
            'may_not_expand_scope_silently',true
          ),
          'jurisdiction',jsonb_build_object(
            'bounded_by_assignment_scope',true,
            'cross_domain_action_requires_explicit_route_or_composition',true
          ),
          'reasoning',jsonb_build_object(
            'recover_before_recreate',true,
            'continue_before_reconstructing',true,
            'generate_routes_before_declaring_block',true,
            'decision_record_required_for_material_choices',true
          ),
          'execution',jsonb_build_object(
            'blocked_tool_changes_route_not_objective',true,
            'attempted_is_not_executed',true,
            'executed_is_not_verified',true,
            'idempotency_required_for_repeatable_side_effects',true
          ),
          'capability',jsonb_build_object(
            'least_privilege',true,
            'freshness_and_health_required',true,
            'capabilities_are_granted_not_implied_by_role',true
          ),
          'memory_context',jsonb_build_object(
            'context_recovery_required',true,
            'role_scoped_memory',true,
            'contradictions_visible',true,
            'provenance_preserved',true
          ),
          'evidence_provenance',jsonb_build_object(
            'source_binding_required',true,
            'provider_native_receipts_required_when_available',true,
            'transforms_do_not_replace_originals',true
          ),
          'verification',jsonb_build_object(
            'readback_required_for_mutation',true,
            'independent_verification_preferred_for_consequential_actions',true,
            'terminal_success_requires_evidence',true
          ),
          'communication',jsonb_build_object(
            'material_handoffs_are_structured',true,
            'commitments_are_recorded',true,
            'uncertainty_not_hidden',true
          ),
          'escalation',jsonb_build_object(
            'operator_only_for_genuine_operator_dependencies',true,
            'hard_external_boundaries_are_preserved',true,
            'local_failure_is_not_global_failure',true
          ),
          'handoff',jsonb_build_object(
            'required_fields',jsonb_build_array(
              'role_key','scope','mission_state','open_loops','evidence_refs',
              'provider_state_refs','last_verified_event','next_action'
            ),
            'successor_must_readback_before_acting',true
          ),
          'observability',jsonb_build_object(
            'health_state_required',true,
            'role_outcomes_measured',true,
            'unverified_actions_counted',true
          ),
          'security_risk',jsonb_build_object(
            'blast_radius_bounded',true,
            'secrets_never_logged',true,
            'irreversible_actions_explicit',true
          ),
          'lifecycle',jsonb_build_object(
            'states',jsonb_build_array('DRAFT','ACTIVE','DEPRECATED','RETIRED'),
            'history_preserved',true
          )
        )
      );
      v_hash := encode(digest(jsonb_strip_nulls(v_contract)::text,'sha256'),'hex');

      insert into public.oa_role_versions_v1(
        role_key,version,contract,contract_sha256,activation_status,created_by,created_source_class,activated_at
      ) values (
        r.role_key,'1.0.0',v_contract,v_hash,'ACTIVE','migration:operator_administration_roles_v1','MIGRATION',now()
      );
    end if;
  end loop;
end;
$;

-- Existing runtime workers receive explicit role identities without changing
-- their original public.agents rows or inventing new runtime agents.
do $$
declare
  a record;
  v_role_key text;
  v_logical_id text;
  v_role_version uuid;
  v_payload jsonb;
begin
  if to_regclass('public.agents') is not null then
    for a in execute 'select id, name from public.agents' loop
    v_role_key := case a.name
      when 'capacity-planner' then 'OA.ROLE.CAPACITY_PLANNER'
      when 'config-validator' then 'OA.ROLE.CONFIG_VALIDATOR'
      when 'dependency-tracker' then 'OA.ROLE.DEPENDENCY_TRACKER'
      when 'deployment-coordinator' then 'OA.ROLE.DEPLOYMENT_COORDINATOR'
      when 'metric-collector' then 'OA.ROLE.METRIC_COLLECTOR'
      when 'service-monitor' then 'OA.ROLE.SERVICE_MONITOR'
      when 'auto-scaler' then 'OA.ROLE.AUTO_SCALER'
      when 'chaos-engineer' then 'OA.ROLE.CHAOS_ENGINEER'
      when 'circuit-breaker' then 'OA.ROLE.CIRCUIT_BREAKER'
      when 'incident-commander' then 'OA.ROLE.INCIDENT_COMMANDER'
      when 'self-healer' then 'OA.ROLE.SELF_HEALER'
      when 'learning-agent' then 'OA.ROLE.LEARNING_AGENT'
      when 'cost-optimizer' then 'OA.ROLE.COST_OPTIMIZER'
      when 'ml-anomaly-detector' then 'OA.ROLE.ANOMALY_DETECTOR'
      when 'performance-optimizer' then 'OA.ROLE.PERFORMANCE_OPTIMIZER'
      when 'predictive-alerting' then 'OA.ROLE.PREDICTIVE_ALERTING'
      when 'alert-manager' then 'OA.ROLE.ALERT_MANAGER'
      when 'health-checker' then 'OA.ROLE.HEALTH_CHECKER'
      when 'log-analyzer' then 'OA.ROLE.LOG_ANALYZER'
      else null
    end;

    if v_role_key is not null then
      v_logical_id := 'OA.RUNTIME.'
        || upper(regexp_replace(a.name,'[^a-zA-Z0-9]+','_','g'))
        || '_'
        || upper(replace(a.id::text,'-',''));

      select role_version_id into v_role_version
      from public.oa_role_versions_v1
      where role_key = v_role_key and activation_status = 'ACTIVE'
      order by created_at desc
      limit 1;

      if exists (select 1 from public.oa_agent_genomes_v1 where logical_agent_id = v_logical_id)
         and not exists (
           select 1 from public.oa_agent_role_assignments_v1
           where logical_agent_id = v_logical_id
             and role_key = v_role_key
             and assignment_mode = 'PRIMARY'
             and status = 'ACTIVE'
         ) then
        v_payload := jsonb_build_object(
          'logical_agent_id',v_logical_id,
          'role_key',v_role_key,
          'role_version_id',v_role_version,
          'assignment_mode','PRIMARY',
          'mission_ref',null,
          'scope',jsonb_build_object('runtime_agent_id',a.id),
          'authority_constraints',jsonb_build_object('authority_source','OPERATOR','no_silent_scope_expansion',true),
          'continuity_handoff',jsonb_build_object('continuity_priority',1,'replacement_executor_must_rehydrate',true),
          'assigned_by','migration:operator_administration_roles_v1'
        );

        insert into public.oa_agent_role_assignments_v1(
          logical_agent_id,role_key,role_version_id,assignment_mode,
          scope,authority_constraints,continuity_handoff,status,
          assigned_by,assigned_source_class,assignment_sha256
        ) values (
          v_logical_id,v_role_key,v_role_version,'PRIMARY',
          jsonb_build_object('runtime_agent_id',a.id),
          jsonb_build_object('authority_source','OPERATOR','no_silent_scope_expansion',true),
          jsonb_build_object('continuity_priority',1,'replacement_executor_must_rehydrate',true),
          'ACTIVE',
          'migration:operator_administration_roles_v1',
          'MIGRATION',
          encode(digest(jsonb_strip_nulls(v_payload)::text,'sha256'),'hex')
        );
      end if;
    end if;
    end loop;
  end if;
end;
$;

revoke all on function public.oa_validate_role_content_hash_v1() from public, anon, authenticated;

comment on table public.oa_roles_v1 is
  'Stable Operator Administration responsibilities. A role is not an agent or authority grant.';
comment on table public.oa_role_versions_v1 is
  'Versioned role contracts. Continuity is the first role locus and role history is preserved.';
comment on table public.oa_agent_role_assignments_v1 is
  'Time-bounded, scope-bounded role assignments linking logical agents to versioned role contracts.';
