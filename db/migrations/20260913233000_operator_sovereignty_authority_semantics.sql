-- Operator sovereignty: routine recoverable work inherits active mission authority.
-- Verification, provenance, idempotency, health observations, and readback remain
-- system responsibilities; separate approval is reserved for consequence-sensitive
-- routes and destructive operations.

alter table public.connector_route_policy_v3
  drop constraint if exists connector_route_policy_v3_mutation_approval_guard;

comment on column public.connector_route_policy_v3.approval_required is
  'Separate operator confirmation is reserved for destructive or consequence-sensitive routes. Bounded recoverable writes may execute under active mission authority. Verification, idempotency, provenance, and readback remain system responsibilities.';

update public.connector_route_policy_v3
set approval_required = false,
    metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
      'authority_mode','active_mission_authority',
      'operator_friction_invariant','routine_recoverable_work_must_not_require_repeat_approval',
      'authority_updated_at', now()
    ),
    updated_at = now()
where enabled = true
  and route_key = any(array[
    'asana:update_tasks:task_update:v1',
    'asana:create_task:case_task_write:v1',
    'box:create_folder:approved_root_create:v1',
    'box:upload_file:control_receipt_upload:v1',
    'github:create_file:repository_file_write:v1',
    'github:update_file:repository_file_write:v1',
    'github.backend_ops:branch.create:branch_create:v1',
    'github.backend_ops:contents.put:repository_file_write:v1',
    'github.backend_ops:issue.comment:issues_write:v1',
    'github.backend_ops:issue.create:issues_write:v1',
    'github.backend_ops:pull.comment:pull_requests_comment:v1',
    'github.backend_ops:workflow.dispatch:actions_dispatch:v1',
    'foundation:github.glaciereq:push_files:repo_write:v1',
    'github.native:add_review_to_pr:pull_requests_review:v1',
    'github.native:create_pull_request:pull_requests_write:v1',
    'google_calendar:create_event:calendar_event_write:v1',
    'google_calendar:create_event:event_write:v1',
    'google_drive:create_file:workspace_file_create:v1',
    'linear:create_issue:case_issue_write:v1',
    'notion:notion-update-page:control_projection_write:v1'
  ]::text[]);

create or replace function public.connector_execution_route_eligibility_v3(
  p_connector_key text,
  p_tool_name text,
  p_capability text,
  p_route_key text default null::text
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
  v_now timestamptz := clock_timestamp();
  v_registry public.connector_registry_v2%rowtype;
  v_policy public.connector_route_policy_v3%rowtype;
  v_probe_fresh boolean;
begin
  select * into v_registry
  from public.connector_registry_v2
  where connector_key=p_connector_key;
  if not found then
    return jsonb_build_object('eligible',false,'reason','connector_not_registered');
  end if;

  if v_registry.lifecycle_state <> 'connected' then
    return jsonb_build_object('eligible',false,'reason','connector_not_connected','lifecycle',v_registry.lifecycle_state);
  end if;
  if v_registry.authentication_state <> 'authenticated' then
    return jsonb_build_object('eligible',false,'reason','connector_not_authenticated','authentication',v_registry.authentication_state);
  end if;

  select * into v_policy
  from public.connector_route_policy_v3
  where connector_key=p_connector_key
    and tool_name=p_tool_name
    and capability=p_capability
    and enabled
    and (p_route_key is null or route_key=p_route_key)
  order by priority asc, updated_at desc, route_key asc
  limit 1;
  if not found then
    return jsonb_build_object('eligible',false,'reason','route_not_registered_or_enabled');
  end if;

  if v_policy.mutation_class='read' and not v_registry.read_enabled then
    return jsonb_build_object('eligible',false,'reason','connector_read_disabled','routeKey',v_policy.route_key);
  elsif v_policy.mutation_class='write' and not v_registry.write_enabled then
    return jsonb_build_object('eligible',false,'reason','connector_write_disabled','routeKey',v_policy.route_key);
  elsif v_policy.mutation_class='destructive' and (
    not v_registry.write_enabled
    or not v_registry.destructive_actions_allowed
    or not v_policy.destructive_actions_allowed
  ) then
    return jsonb_build_object('eligible',false,'reason','destructive_action_disabled','routeKey',v_policy.route_key);
  end if;

  v_probe_fresh := (
    v_registry.freshness_status='fresh'
    and v_registry.last_successful_probe_at is not null
    and v_registry.freshness_sla_seconds is not null
    and v_registry.freshness_sla_seconds > 0
    and v_registry.last_successful_probe_at + make_interval(secs=>v_registry.freshness_sla_seconds) > v_now
  );

  return jsonb_build_object(
    'eligible',true,
    'reason','eligible',
    'routeKey',v_policy.route_key,
    'mutationClass',v_policy.mutation_class,
    'healthObservation',v_registry.health_status,
    'probeFresh',v_probe_fresh,
    'probeReceipt',v_registry.last_successful_probe_receipt_ref,
    'freshUntil',case
      when v_registry.last_successful_probe_at is not null and v_registry.freshness_sla_seconds is not null
      then v_registry.last_successful_probe_at + make_interval(secs=>v_registry.freshness_sla_seconds)
      else null
    end
  );
end;
$function$;

comment on function public.connector_execution_route_eligibility_v3(text,text,text,text) is
  'Checks executable identity, authentication, enabled route, and capability boundaries. Health and probe freshness are observability signals, not permission gates; provider execution and verification establish current reality.';

create or replace function public.enqueue_connector_execution_job_v3(
  p_connector_key text,
  p_tool_name text,
  p_capability text,
  p_arguments jsonb,
  p_logical_scope text default null::text,
  p_priority integer default 50,
  p_idempotency_key text default null::text,
  p_approval_required boolean default false,
  p_notion_request_id text default null::text,
  p_linear_issue_id text default null::text
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'public', 'extensions'
as $function$
declare
  v_now timestamptz := clock_timestamp();
  v_policy public.connector_route_policy_v3%rowtype;
  v_payload_hash text;
  v_idempotency_key text;
  v_job public.connector_execution_jobs_v3%rowtype;
  v_inserted boolean := false;
begin
  if p_connector_key is null or p_connector_key !~ '^[a-z0-9][a-z0-9._:-]{1,127}$' then raise exception 'invalid connector_key'; end if;
  if p_tool_name is null or p_tool_name !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$' then raise exception 'invalid tool_name'; end if;
  if p_capability is null or p_capability !~ '^[a-z0-9][a-z0-9._:-]{2,127}$' then raise exception 'invalid capability'; end if;
  if p_arguments is null then raise exception 'arguments are required'; end if;
  if p_priority < 0 or p_priority > 100 then raise exception 'priority must be between 0 and 100'; end if;

  select p.* into v_policy
  from public.connector_route_policy_v3 p
  join public.connector_registry_v2 c on c.connector_key=p.connector_key
  where p.connector_key=p_connector_key
    and p.tool_name=p_tool_name
    and p.capability=p_capability
    and p.enabled
    and (
      (p.mutation_class='read' and c.read_enabled)
      or (p.mutation_class='write' and c.write_enabled)
      or (p.mutation_class='destructive' and c.write_enabled and c.destructive_actions_allowed and p.destructive_actions_allowed)
    )
  order by p.priority asc, p.updated_at desc, p.route_key asc
  limit 1;

  if not found then
    return jsonb_build_object('enqueued',false,'reason','no_registered_route');
  end if;

  v_payload_hash := encode(extensions.digest(convert_to(p_arguments::text,'UTF8'),'sha256'),'hex');
  v_idempotency_key := coalesce(
    nullif(trim(p_idempotency_key),''),
    encode(extensions.digest(convert_to(
      p_connector_key || E'\n' || p_tool_name || E'\n' || p_capability || E'\n' || coalesce(p_logical_scope,'') || E'\n' || p_arguments::text,
      'UTF8'
    ),'sha256'),'hex')
  );

  if length(v_idempotency_key) > 512 then raise exception 'idempotency_key too long'; end if;

  insert into public.connector_execution_jobs_v3 (
    idempotency_key, connector_key, tool_name, capability, arguments,
    logical_scope, notion_request_id, linear_issue_id, status, priority,
    approval_required, run_after, payload_hash, route_key, policy_version,
    estimated_rpc_units, created_at, updated_at
  ) values (
    v_idempotency_key, p_connector_key, p_tool_name, p_capability, p_arguments,
    p_logical_scope, p_notion_request_id, p_linear_issue_id, 'queued', p_priority,
    (p_approval_required or v_policy.approval_required),
    v_now, v_payload_hash, v_policy.route_key, v_policy.policy_version,
    v_policy.estimated_rpc_units, v_now, v_now
  )
  on conflict (idempotency_key) do nothing
  returning * into v_job;

  if found then
    v_inserted := true;
  else
    select * into v_job
    from public.connector_execution_jobs_v3
    where idempotency_key=v_idempotency_key;

    if v_job.payload_hash <> v_payload_hash
       or v_job.connector_key <> p_connector_key
       or v_job.tool_name <> p_tool_name
       or v_job.capability <> p_capability then
      return jsonb_build_object(
        'enqueued',false,
        'reason','idempotency_conflict',
        'jobId',v_job.id,
        'status',v_job.status
      );
    end if;
  end if;

  return jsonb_build_object(
    'enqueued',true,
    'created',v_inserted,
    'jobId',v_job.id,
    'correlationId',v_job.correlation_id,
    'status',v_job.status,
    'approvalRequired',v_job.approval_required,
    'authorityMode',case when v_job.approval_required then 'scoped_consequence_authority' else 'active_mission_authority' end,
    'payloadHash',v_job.payload_hash,
    'idempotencyKey',v_job.idempotency_key,
    'routeKey',v_job.route_key,
    'policyVersion',v_job.policy_version
  );
end;
$function$;

comment on function public.enqueue_connector_execution_job_v3(text,text,text,jsonb,text,integer,text,boolean,text,text) is
  'Queues registered connector work. Bounded recoverable writes inherit route mission authority; only route-scoped consequence policy or an explicit caller escalation requires separate approval.';
