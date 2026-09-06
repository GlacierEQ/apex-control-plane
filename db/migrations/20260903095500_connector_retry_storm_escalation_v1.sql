-- Connector retry-storm escalation bridge
-- Mirrors the live supabase-glaciereq repair applied 2026-09-03.
--
-- Purpose:
--   Existing connector incident bridge emitted only OPENED/RESOLVED transitions.
--   Long-running retry storms could therefore worsen silently after the initial alert.
--   This bridge emits idempotent worsening events at material retry milestones and
--   keeps a stable operator-alert action READY until the worsening state is handled.

create or replace function public.control_plane_connector_retry_storm_bridge()
returns trigger
language plpgsql
security definer
set search_path to 'pg_catalog','public'
as $function$
declare
  v_milestone integer;
  v_event_key text;
  v_action_key text;
  v_event_id uuid;
begin
  if new.resolved_at is not null or new.retry_count is null or new.retry_count < 3 then
    return new;
  end if;

  v_milestone := case
    when new.retry_count >= 1000 then 1000
    when new.retry_count >= 100 then 100
    when new.retry_count >= 10 then 10
    else 3
  end;

  v_event_key := 'connector_incident:' || new.id::text || ':retry_storm:' || v_milestone::text;

  insert into public.control_plane_events(
    event_key,event_type,source_system,source_ref,occurred_at,severity,payload
  )
  values(
    v_event_key,
    'CONNECTOR_INCIDENT_RETRY_STORM',
    'apex_connector_incidents',
    new.id::text,
    now(),
    case
      when v_milestone >= 10 or new.incident_type in ('AUTH_FAILED','FAILED') then 'HIGH'
      else 'MEDIUM'
    end,
    jsonb_build_object(
      'connector',new.connector,
      'incident_type',new.incident_type,
      'retry_count',new.retry_count,
      'retry_milestone',v_milestone,
      'last_error',new.last_error,
      'opened_at',new.opened_at,
      'phase','WORSENED',
      'circuit_breaker_recommended',true
    )
  )
  on conflict(event_key) do nothing
  returning id into v_event_id;

  if v_event_id is null then
    return new;
  end if;

  v_action_key := 'operator_alert:connector:' || new.id::text || ':retry_storm';

  insert into public.control_plane_action_outbox(
    action_key,action_type,target_system,target_ref,payload,source_event_id,
    priority,requires_operator_approval,authorization_basis,status
  )
  values(
    v_action_key,
    'OPERATOR_ALERT',
    'operator_alert_router',
    new.connector,
    jsonb_build_object(
      'connector',new.connector,
      'incident_type',new.incident_type,
      'phase','WORSENED',
      'retry_count',new.retry_count,
      'retry_milestone',v_milestone,
      'last_error',new.last_error,
      'incident_id',new.id,
      'opened_at',new.opened_at,
      'circuit_breaker_recommended',true
    ),
    v_event_id,
    case
      when v_milestone >= 10 or new.incident_type in ('AUTH_FAILED','FAILED') then 'P0'
      else 'P1'
    end,
    false,
    'Internal operator escalation generated when connector retries cross a material threshold',
    'READY'
  )
  on conflict(action_key) do update
    set payload = excluded.payload,
        source_event_id = excluded.source_event_id,
        priority = excluded.priority,
        status = 'READY',
        acknowledged_at = null,
        completed_at = null,
        updated_at = now();

  return new;
end;
$function$;

drop trigger if exists trg_control_plane_connector_retry_storm_bridge
  on public.apex_connector_incidents;

create trigger trg_control_plane_connector_retry_storm_bridge
after update of retry_count, last_error, incident_type
on public.apex_connector_incidents
for each row
when (new.resolved_at is null)
execute function public.control_plane_connector_retry_storm_bridge();

-- Backfill the highest currently crossed milestone for already-open incidents.
with current_storms as (
  select
    i.*,
    case
      when i.retry_count >= 1000 then 1000
      when i.retry_count >= 100 then 100
      when i.retry_count >= 10 then 10
      when i.retry_count >= 3 then 3
      else null
    end as milestone
  from public.apex_connector_incidents i
  where i.resolved_at is null
    and i.retry_count >= 3
),
ins as (
  insert into public.control_plane_events(
    event_key,event_type,source_system,source_ref,occurred_at,severity,payload
  )
  select
    'connector_incident:' || s.id::text || ':retry_storm:' || s.milestone::text,
    'CONNECTOR_INCIDENT_RETRY_STORM',
    'apex_connector_incidents',
    s.id::text,
    now(),
    case
      when s.milestone >= 10 or s.incident_type in ('AUTH_FAILED','FAILED') then 'HIGH'
      else 'MEDIUM'
    end,
    jsonb_build_object(
      'connector',s.connector,
      'incident_type',s.incident_type,
      'retry_count',s.retry_count,
      'retry_milestone',s.milestone,
      'last_error',s.last_error,
      'opened_at',s.opened_at,
      'phase','WORSENED',
      'circuit_breaker_recommended',true,
      'backfilled',true
    )
  from current_storms s
  on conflict(event_key) do nothing
  returning id, source_ref, payload
)
insert into public.control_plane_action_outbox(
  action_key,action_type,target_system,target_ref,payload,source_event_id,
  priority,requires_operator_approval,authorization_basis,status
)
select
  'operator_alert:connector:' || i.source_ref || ':retry_storm',
  'OPERATOR_ALERT',
  'operator_alert_router',
  i.payload->>'connector',
  i.payload,
  i.id,
  case
    when coalesce((i.payload->>'retry_milestone')::int,0) >= 10
      or i.payload->>'incident_type' in ('AUTH_FAILED','FAILED') then 'P0'
    else 'P1'
  end,
  false,
  'Internal operator escalation generated from pre-existing connector retry storm',
  'READY'
from ins i
on conflict(action_key) do update
  set payload=excluded.payload,
      source_event_id=excluded.source_event_id,
      priority=excluded.priority,
      status='READY',
      acknowledged_at=null,
      completed_at=null,
      updated_at=now();
