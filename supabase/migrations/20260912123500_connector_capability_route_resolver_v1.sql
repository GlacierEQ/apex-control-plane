-- GlacierEQ control-plane capability resolver v1
-- Joins route policy/runtime, connector auth/freshness, verified capability matrix,
-- and holographic mesh evidence without transferring source authority.

create or replace function public.resolve_connector_capability_routes_v1(
  p_capability text,
  p_mutation_class text default null,
  p_limit integer default 20
)
returns jsonb
language sql
security definer
set search_path = pg_catalog, public
as $$
with candidate as (
  select
    p.route_key,
    p.connector_key,
    p.tool_name,
    p.capability,
    p.mutation_class,
    p.priority,
    p.approval_required,
    p.policy_version,
    p.fallback_group,
    r.health_status as route_health_status,
    r.circuit_state,
    r.rpc_budget_limit,
    r.rpc_units_reserved,
    r.rpc_units_consumed,
    c.lifecycle_state,
    c.authentication_state,
    c.health_status as connector_health_status,
    c.freshness_status,
    c.last_successful_probe_at,
    c.last_successful_probe_receipt_ref,
    public.connector_execution_route_eligibility_v3(
      p.connector_key,
      p.tool_name,
      p.capability,
      p.route_key
    ) as eligibility,
    coalesce((
      select max(m.capability_level)
      from public.connector_capability_matrix_v2 m
      where m.connector_key = p.connector_key
        and m.capability = p.capability
        and m.verified
    ), 0) as verified_capability_level,
    (select count(*)::int
       from public.capability_mesh_edges_v1 e
      where e.active
        and e.truth_state in ('verified','observed','established')
        and (
          e.source_key in (p.connector_key,p.route_key,p.capability)
          or e.target_key in (p.connector_key,p.route_key,p.capability)
        )) as mesh_evidence_count
  from public.connector_route_policy_v3 p
  join public.connector_route_runtime_v3 r on r.route_key = p.route_key
  join public.connector_registry_v2 c on c.connector_key = p.connector_key
  where p.enabled
    and p.capability = p_capability
    and (p_mutation_class is null or p.mutation_class = p_mutation_class)
), ranked as (
  select *,
    row_number() over (
      order by
        case when coalesce((eligibility->>'eligible')::boolean,false) then 0 else 1 end,
        case when circuit_state = 'closed' then 0 when circuit_state = 'half_open' then 1 else 2 end,
        case when route_health_status = 'healthy' then 0 when route_health_status = 'unknown' then 1 else 2 end,
        priority asc,
        verified_capability_level desc,
        mesh_evidence_count desc,
        route_key asc
    ) as resolver_rank
  from candidate
)
select jsonb_build_object(
  'schema','glaciereq.connector-capability-resolution.v1',
  'capability',p_capability,
  'mutationClass',p_mutation_class,
  'resolvedAt',clock_timestamp(),
  'candidateCount',(select count(*) from candidate),
  'eligibleCount',(select count(*) from candidate where coalesce((eligibility->>'eligible')::boolean,false)),
  'candidates',coalesce((
    select jsonb_agg(jsonb_build_object(
      'rank',resolver_rank,
      'routeKey',route_key,
      'connectorKey',connector_key,
      'toolName',tool_name,
      'capability',capability,
      'mutationClass',mutation_class,
      'priority',priority,
      'approvalRequired',approval_required,
      'policyVersion',policy_version,
      'fallbackGroup',fallback_group,
      'eligibility',eligibility,
      'routeHealth',route_health_status,
      'circuitState',circuit_state,
      'budget',jsonb_build_object('limit',rpc_budget_limit,'reserved',rpc_units_reserved,'consumed',rpc_units_consumed),
      'connectorState',jsonb_build_object(
        'lifecycle',lifecycle_state,
        'authentication',authentication_state,
        'health',connector_health_status,
        'freshness',freshness_status,
        'lastSuccessfulProbeAt',last_successful_probe_at,
        'probeReceipt',last_successful_probe_receipt_ref
      ),
      'verifiedCapabilityLevel',verified_capability_level,
      'meshEvidenceCount',mesh_evidence_count
    ) order by resolver_rank)
    from (select * from ranked order by resolver_rank limit greatest(1,least(coalesce(p_limit,20),100))) q
  ),'[]'::jsonb)
);
$$;

revoke all on function public.resolve_connector_capability_routes_v1(text,text,integer) from public, anon, authenticated;
grant execute on function public.resolve_connector_capability_routes_v1(text,text,integer) to service_role;

comment on function public.resolve_connector_capability_routes_v1(text,text,integer) is
'Fail-closed capability-to-route resolver joining route policy/runtime, connector auth/freshness, verified capability matrix, and holographic mesh evidence. Returns ranked eligible and blocked fallbacks without transferring source authority.';
