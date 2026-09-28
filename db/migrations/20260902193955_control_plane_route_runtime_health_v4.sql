create or replace view public.control_plane_runtime_health_v1
with (security_invoker=true)
as
with capability_rollup as (
  select connector_key,
         count(*) as capability_count,
         count(*) filter(where verified) as verified_capability_count,
         max(last_verified_at) as last_capability_verified_at
  from public.connector_capability_matrix_v2
  group by connector_key
),
route_rollup as (
  select
    p.connector_key,
    count(*) as route_count,
    count(*) filter(where p.enabled) as enabled_route_count,
    count(*) filter(where p.enabled and p.mutation_class='read') as enabled_read_routes,
    count(*) filter(where p.enabled and p.mutation_class='write') as enabled_write_routes,
    count(*) filter(where p.enabled and rt.route_key is not null) as enabled_routes_with_runtime,
    count(*) filter(
      where p.enabled and rt.route_key is not null
        and rt.health_status='healthy'
        and rt.circuit_state='closed'
        and coalesce(rt.consecutive_failures,0)=0
    ) as enabled_healthy_runtime_routes,
    count(*) filter(
      where p.enabled and rt.route_key is not null
        and (
          rt.health_status in ('unhealthy','failed','down')
          or rt.circuit_state in ('open','half_open')
          or coalesce(rt.consecutive_failures,0)>0
        )
    ) as enabled_unhealthy_runtime_routes
  from public.connector_route_policy_v3 p
  left join public.connector_route_runtime_v3 rt using(route_key)
  group by p.connector_key
),
github_receipts as (
  select
    count(*) filter(where created_at >= now()-interval '15 minutes') as recent_receipts_15m,
    count(*) filter(where created_at >= now()-interval '15 minutes' and outcome='succeeded') as recent_success_15m,
    count(*) filter(where created_at >= now()-interval '15 minutes' and outcome in ('failed','rejected')) as recent_failure_15m,
    max(created_at) filter(where outcome='succeeded') as last_execution_success_at,
    max(created_at) filter(where outcome='failed') as last_execution_failure_at
  from public.github_connector_receipts_v1
),
github_batch as (
  select
    count(*) filter(where status in ('pending','retry')) as batch_backlog,
    count(*) filter(where status='running') as batch_inflight,
    count(*) filter(where status='failed' and completed_at >= now()-interval '15 minutes') as batch_failed_recent_15m,
    count(*) filter(where status='failed') as batch_failed_historical,
    max(updated_at) as batch_last_activity_at
  from public.github_batch_items_v2
),
github_webhook as (
  select
    count(*) filter(where status='pending') as webhook_pending,
    count(*) filter(where status='processing') as webhook_processing,
    count(*) filter(where status='failed' and processed_at >= now()-interval '15 minutes') as webhook_failed_recent_15m,
    count(*) filter(where status='failed') as webhook_failed_historical,
    max(updated_at) as webhook_last_activity_at
  from public.github_webhook_event_queue_v1
),
github_workers as (
  select
    count(*) as worker_count,
    count(*) filter(
      where status='online' and last_heartbeat_at is not null
        and last_heartbeat_at >= now()-interval '3 minutes'
    ) as live_worker_count,
    count(*) filter(
      where status='online'
        and (last_heartbeat_at is null or last_heartbeat_at < now()-interval '3 minutes')
    ) as stale_online_worker_count,
    count(*) filter(where status='source_ready') as source_ready_worker_count,
    jsonb_agg(
      jsonb_build_object(
        'worker_id',worker_id,'worker_type',worker_type,'status',status,
        'last_heartbeat_at',last_heartbeat_at,
        'stale',status='online' and (last_heartbeat_at is null or last_heartbeat_at < now()-interval '3 minutes')
      ) order by worker_type,worker_id
    ) as workers
  from public.github_batch_workers_v2
)
select
  r.connector_key,r.display_name,r.connector_class,r.canonical_role,r.authority_tier,
  r.lifecycle_state,r.authentication_state,r.health_status as registry_health_status,
  r.freshness_status,r.last_checked_at,r.last_successful_probe_at,
  coalesce(c.capability_count,0) as capability_count,
  coalesce(c.verified_capability_count,0) as verified_capability_count,
  c.last_capability_verified_at,
  coalesce(rt.route_count,0) as route_count,
  coalesce(rt.enabled_route_count,0) as enabled_route_count,
  coalesce(rt.enabled_read_routes,0) as enabled_read_routes,
  coalesce(rt.enabled_write_routes,0) as enabled_write_routes,
  case when r.connector_key='github.backend_ops' then g.recent_receipts_15m else null end as recent_receipts_15m,
  case when r.connector_key='github.backend_ops' then g.recent_success_15m else null end as recent_success_15m,
  case when r.connector_key='github.backend_ops' then g.recent_failure_15m else null end as recent_failure_15m,
  case when r.connector_key='github.backend_ops' then g.last_execution_success_at else null end as last_execution_success_at,
  case when r.connector_key='github.backend_ops' then g.last_execution_failure_at else null end as last_execution_failure_at,
  case when r.connector_key='github.backend_ops' then b.batch_backlog else null end as batch_backlog,
  case when r.connector_key='github.backend_ops' then b.batch_inflight else null end as batch_inflight,
  case when r.connector_key='github.backend_ops' then b.batch_failed_recent_15m else null end as batch_failed_terminal,
  case when r.connector_key='github.backend_ops' then w.live_worker_count else null end as live_worker_count,
  case when r.connector_key='github.backend_ops' then w.stale_online_worker_count else null end as stale_online_worker_count,
  case when r.connector_key='github.backend_ops' then w.source_ready_worker_count else null end as source_ready_worker_count,
  case when r.connector_key='github.backend_ops' then h.webhook_pending else null end as webhook_pending,
  case when r.connector_key='github.backend_ops' then h.webhook_processing else null end as webhook_processing,
  case when r.connector_key='github.backend_ops' then h.webhook_failed_recent_15m else null end as webhook_failed,
  case when r.connector_key='github.backend_ops' then w.workers else null end as worker_detail,
  case
    when r.lifecycle_state in ('blocked','disabled','retired') then 'blocked'
    when r.authentication_state in ('failed','auth_required','expired','revoked') then 'blocked'
    when r.health_status in ('unhealthy','failed','down') then 'degraded'
    when r.connector_key='github.backend_ops' and coalesce(w.stale_online_worker_count,0)>0 then 'degraded'
    when r.connector_key='github.backend_ops' and coalesce(h.webhook_failed_recent_15m,0)>0 then 'degraded'
    when r.connector_key='github.backend_ops' and coalesce(b.batch_failed_recent_15m,0)>0 then 'degraded'
    when r.connector_key='github.backend_ops'
      and coalesce(g.recent_failure_15m,0)>0 and coalesce(g.recent_success_15m,0)=0 then 'degraded'
    when coalesce(rt.enabled_unhealthy_runtime_routes,0)>0 then 'degraded'
    when r.freshness_status in ('stale','expired') then 'degraded'
    when r.lifecycle_state='connected'
      and r.authentication_state='authenticated'
      and r.health_status in ('healthy','verified','verified_authorization')
      and (
        r.health_status='healthy'
        or (
          coalesce(rt.enabled_route_count,0)>0
          and coalesce(rt.enabled_routes_with_runtime,0)=coalesce(rt.enabled_route_count,0)
          and coalesce(rt.enabled_healthy_runtime_routes,0)=coalesce(rt.enabled_route_count,0)
        )
      ) then 'healthy'
    else 'unknown'
  end as effective_health_status,
  jsonb_build_object(
    'connector_quality',r.connector_quality,
    'data_quality',r.data_quality,
    'next_human_gate',r.next_human_gate,
    'route_runtime',jsonb_build_object(
      'enabled_routes',coalesce(rt.enabled_route_count,0),
      'enabled_routes_with_runtime',coalesce(rt.enabled_routes_with_runtime,0),
      'enabled_healthy_runtime_routes',coalesce(rt.enabled_healthy_runtime_routes,0),
      'enabled_unhealthy_runtime_routes',coalesce(rt.enabled_unhealthy_runtime_routes,0)
    ),
    'github_batch_last_activity_at',case when r.connector_key='github.backend_ops' then b.batch_last_activity_at else null end,
    'github_webhook_last_activity_at',case when r.connector_key='github.backend_ops' then h.webhook_last_activity_at else null end,
    'batch_failed_historical',case when r.connector_key='github.backend_ops' then b.batch_failed_historical else null end,
    'webhook_failed_historical',case when r.connector_key='github.backend_ops' then h.webhook_failed_historical else null end
  ) as detail
from public.connector_registry_v2 r
left join capability_rollup c using(connector_key)
left join route_rollup rt using(connector_key)
cross join github_receipts g
cross join github_batch b
cross join github_webhook h
cross join github_workers w;

revoke all on public.control_plane_runtime_health_v1 from public,anon,authenticated;
grant select on public.control_plane_runtime_health_v1 to service_role;

create or replace function public.control_plane_operational_snapshot_v2()
returns jsonb
language sql
security definer
set search_path='public','pg_temp'
as $$
with rows as (select * from public.control_plane_runtime_health_v1),
classified as (
  select *,
    case
      when lifecycle_state='connected'
        and authentication_state='authenticated'
        and enabled_route_count>0
        then 'operational_core'
      when lifecycle_state in ('connected','staging_only')
        then 'integration_working_set'
      else 'estate_backlog'
    end as plane_class
  from rows
),
core as (select * from classified where plane_class='operational_core'),
working as (select * from classified where plane_class='integration_working_set'),
backlog as (select * from classified where plane_class='estate_backlog')
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
        'connector_key',connector_key,'status',effective_health_status,
        'registry_health',registry_health_status,'authority_tier',authority_tier,
        'routes',enabled_route_count,'verified_capabilities',verified_capability_count,
        'next_human_gate',detail->>'next_human_gate','route_runtime',detail->'route_runtime'
      ) order by
        case effective_health_status when 'blocked' then 1 when 'degraded' then 2 else 3 end,
        authority_tier,connector_key)
      from core where effective_health_status<>'healthy'
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
      'status',effective_health_status,'recent_success_15m',recent_success_15m,
      'recent_failure_15m',recent_failure_15m,'batch_backlog',batch_backlog,
      'batch_inflight',batch_inflight,'live_worker_count',live_worker_count,
      'stale_online_worker_count',stale_online_worker_count,
      'source_ready_worker_count',source_ready_worker_count,'webhook_pending',webhook_pending,
      'webhook_failed',webhook_failed,'verified_capabilities',verified_capability_count,
      'enabled_routes',enabled_route_count,'detail',detail
    ) from classified where connector_key='github.backend_ops' limit 1
  ),
  'supabase_core',coalesce((
    select jsonb_agg(jsonb_build_object(
      'connector_key',connector_key,'status',effective_health_status,
      'last_checked_at',last_checked_at,'verified_capabilities',verified_capability_count,
      'enabled_routes',enabled_route_count,'route_runtime',detail->'route_runtime'
    ) order by connector_key)
    from classified where connector_key in ('supabase.backend_ops','supabase.glaciereq')
  ),'[]'::jsonb)
);
$$;

revoke all on function public.control_plane_operational_snapshot_v2() from public,anon,authenticated;
grant execute on function public.control_plane_operational_snapshot_v2() to service_role;
