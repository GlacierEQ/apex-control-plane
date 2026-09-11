update public.connector_route_policy_v3
set enabled=false,
    metadata=metadata||jsonb_build_object(
      'superseded',true,
      'superseded_by','notion:search:workspace_search:v2',
      'superseded_at',now(),
      'reason','duplicate search route; v2 has verified healthy runtime'
    ),
    updated_at=now()
where route_key='notion:search:workspace_search:v1'
  and exists(
    select 1
    from public.connector_route_policy_v3 p2
    join public.connector_route_runtime_v3 r2 on r2.route_key=p2.route_key
    where p2.route_key='notion:search:workspace_search:v2'
      and p2.enabled=true
      and r2.health_status='healthy'
      and r2.circuit_state='closed'
      and r2.consecutive_failures=0
  );

comment on table public.connector_route_policy_v3 is
  'Connector route policy. Superseded duplicate routes remain as evidence but are disabled from selection.';
