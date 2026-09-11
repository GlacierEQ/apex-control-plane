create or replace function public.control_plane_operational_snapshot_v2()
returns jsonb
language sql
security definer
set search_path='public','pg_temp'
as $$
with rows as (
  select * from public.control_plane_runtime_health_v1
),
classified as (
  select *,
    case
      when lifecycle_state='connected'
        and authentication_state='authenticated'
        and (enabled_route_count>0 or authority_tier<=2)
        then 'operational_core'
      when lifecycle_state in ('connected','staging_only')
        then 'integration_working_set'
      else 'estate_backlog'
    end as plane_class
  from rows
),
core as (
  select * from classified where plane_class='operational_core'
),
working as (
  select * from classified where plane_class='integration_working_set'
),
backlog as (
  select * from classified where plane_class='estate_backlog'
)
select jsonb_build_object(
  'observed_at',now(),
  'operational_core',jsonb_build_object(
    'connectors',(select count(*) from core),
    'healthy',(select count(*) from core where effective_health_status='healthy'),
    'degraded',(select count(*) from core where effective_health_status='degraded'),
    'blocked',(select count(*) from core where effective_health_status='blocked'),
    'unknown',(select count(*) from core where effective_health_status='unknown'),
    'verified_capabilities',(select coalesce(sum(verified_capability_count),0) from core),
    'enabled_routes',(select coalesce(sum(enabled_route_count),0) from core),
    'attention',coalesce((
      select jsonb_agg(jsonb_build_object(
        'connector_key',connector_key,
        'status',effective_health_status,
        'registry_health',registry_health_status,
        'authority_tier',authority_tier,
        'routes',enabled_route_count,
        'verified_capabilities',verified_capability_count,
        'next_human_gate',detail->>'next_human_gate'
      ) order by
        case effective_health_status when 'blocked' then 1 when 'degraded' then 2 else 3 end,
        authority_tier,connector_key)
      from core
      where effective_health_status<>'healthy'
    ),'[]'::jsonb)
  ),
  'integration_working_set',jsonb_build_object(
    'connectors',(select count(*) from working),
    'healthy',(select count(*) from working where effective_health_status='healthy'),
    'degraded',(select count(*) from working where effective_health_status='degraded'),
    'blocked',(select count(*) from working where effective_health_status='blocked'),
    'unknown',(select count(*) from working where effective_health_status='unknown')
  ),
  'estate_backlog',jsonb_build_object(
    'connectors',(select count(*) from backlog),
    'blocked',(select count(*) from backlog where effective_health_status='blocked'),
    'degraded',(select count(*) from backlog where effective_health_status='degraded'),
    'unknown',(select count(*) from backlog where effective_health_status='unknown')
  ),
  'github_backend_ops',(
    select jsonb_build_object(
      'status',effective_health_status,
      'recent_success_15m',recent_success_15m,
      'recent_failure_15m',recent_failure_15m,
      'batch_backlog',batch_backlog,
      'batch_inflight',batch_inflight,
      'live_worker_count',live_worker_count,
      'stale_online_worker_count',stale_online_worker_count,
      'source_ready_worker_count',source_ready_worker_count,
      'webhook_pending',webhook_pending,
      'webhook_failed',webhook_failed,
      'verified_capabilities',verified_capability_count,
      'enabled_routes',enabled_route_count,
      'detail',detail
    )
    from classified where connector_key='github.backend_ops'
    limit 1
  ),
  'supabase_core',coalesce((
    select jsonb_agg(jsonb_build_object(
      'connector_key',connector_key,
      'status',effective_health_status,
      'last_checked_at',last_checked_at,
      'verified_capabilities',verified_capability_count,
      'enabled_routes',enabled_route_count
    ) order by connector_key)
    from classified
    where connector_key in ('supabase.backend_ops','supabase.glaciereq')
  ),'[]'::jsonb)
);
$$;

revoke all on function public.control_plane_operational_snapshot_v2() from public,anon,authenticated;
grant execute on function public.control_plane_operational_snapshot_v2() to service_role;

comment on function public.control_plane_operational_snapshot_v2() is
  'Service-role-only prioritized control-plane snapshot separating operational core, active integration work, and estate backlog so dormant projections do not dominate current execution health.';
