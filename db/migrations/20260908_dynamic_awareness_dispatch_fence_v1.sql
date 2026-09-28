-- Dynamic awareness dispatch fence
--
-- Source mirror of the verified Supabase runtime change deployed 2026-09-08.
-- The purpose is not to add case-specific rules. It makes current source-bearing
-- reality observable at the action boundary and prevents stale cached intent from
-- being dispatched until an evaluator incorporates the newer state.

create table if not exists public.control_plane_action_awareness_receipts (
  id uuid primary key default gen_random_uuid(),
  action_id uuid not null references public.control_plane_action_outbox(id),
  case_id text,
  evaluator text not null,
  source_watermark_at timestamptz not null,
  execution_valid boolean not null,
  evaluation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_cp_action_awareness_receipts_action_created
  on public.control_plane_action_awareness_receipts(action_id, created_at desc);
create index if not exists idx_cp_action_awareness_receipts_case_source
  on public.control_plane_action_awareness_receipts(case_id, source_watermark_at desc);

alter table public.control_plane_action_awareness_receipts enable row level security;
revoke all on public.control_plane_action_awareness_receipts from public, anon, authenticated;
grant select, insert on public.control_plane_action_awareness_receipts to service_role;

create or replace function public.control_plane_latest_source_watermark_v1(p_action_id uuid)
returns timestamptz
language sql
stable
security definer
set search_path = 'pg_catalog', 'public'
as $$
  select greatest(
    a.created_at,
    coalesce((
      select max(greatest(c.occurred_at, c.created_at))
      from public.control_plane_communications c
      where c.case_id is not distinct from a.case_id
    ), a.created_at),
    coalesce((
      select max(greatest(coalesce(e.observed_at, e.occurred_at), e.created_at))
      from public.control_plane_events e
      where e.case_id is not distinct from a.case_id
        and not (
          e.source_system = 'control_plane_action_outbox'
          and e.source_ref = a.id::text
        )
    ), a.created_at),
    coalesce((
      select max(o.updated_at)
      from public.control_plane_obligations o
      where o.case_id is not distinct from a.case_id
    ), a.created_at)
  )
  from public.control_plane_action_outbox a
  where a.id = p_action_id;
$$;

revoke all on function public.control_plane_latest_source_watermark_v1(uuid)
  from public, anon, authenticated;
grant execute on function public.control_plane_latest_source_watermark_v1(uuid)
  to service_role;

create or replace function public.record_control_plane_action_awareness_v1(
  p_action_id uuid,
  p_evaluator text,
  p_execution_valid boolean,
  p_evaluation jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = 'pg_catalog', 'public'
as $$
declare
  v_action public.control_plane_action_outbox%rowtype;
  v_watermark timestamptz;
  v_id uuid;
begin
  if nullif(btrim(coalesce(p_evaluator, '')), '') is null then
    raise exception 'evaluator identity required';
  end if;

  select *
  into v_action
  from public.control_plane_action_outbox
  where id = p_action_id;

  if not found then
    raise exception 'unknown action id';
  end if;

  v_watermark := public.control_plane_latest_source_watermark_v1(p_action_id);

  insert into public.control_plane_action_awareness_receipts(
    action_id,
    case_id,
    evaluator,
    source_watermark_at,
    execution_valid,
    evaluation
  )
  values(
    p_action_id,
    v_action.case_id,
    btrim(p_evaluator),
    v_watermark,
    p_execution_valid,
    coalesce(p_evaluation, '{}'::jsonb)
  )
  returning id into v_id;

  insert into public.control_plane_receipts(
    case_id,
    receipt_key,
    receipt_type,
    action_id,
    provider,
    provider_ref,
    status,
    payload,
    observed_at
  )
  values(
    v_action.case_id,
    'action-awareness:' || v_id::text,
    'DYNAMIC_AWARENESS_EVALUATION',
    p_action_id,
    'control-plane-awareness',
    v_id::text,
    case when p_execution_valid then 'CURRENT_AND_VALID' else 'CURRENT_NOT_VALID' end,
    jsonb_build_object(
      'evaluator', btrim(p_evaluator),
      'source_watermark_at', v_watermark,
      'execution_valid', p_execution_valid,
      'evaluation', coalesce(p_evaluation, '{}'::jsonb)
    ),
    clock_timestamp()
  );

  return jsonb_build_object(
    'awareness_receipt_id', v_id,
    'action_id', p_action_id,
    'source_watermark_at', v_watermark,
    'execution_valid', p_execution_valid,
    'evaluated_at', clock_timestamp()
  );
end;
$$;

revoke all on function public.record_control_plane_action_awareness_v1(uuid, text, boolean, jsonb)
  from public, anon, authenticated;
grant execute on function public.record_control_plane_action_awareness_v1(uuid, text, boolean, jsonb)
  to service_role;

create or replace view public.control_plane_action_awareness_v1
with (security_invoker = true)
as
select
  a.id as action_id,
  a.case_id,
  a.action_key,
  a.action_type,
  a.target_system,
  a.target_ref,
  a.status,
  a.priority,
  a.requires_operator_approval,
  a.authorization_basis,
  a.attempt_count,
  a.max_attempts,
  a.last_attempt_at,
  a.provider_receipt,
  a.acknowledged_at,
  a.completed_at,
  a.created_at,
  a.updated_at as action_state_at,
  src.latest_source_state_at,
  coalesce(src.newer_source_observations, 0::bigint) as newer_source_observations,
  src.latest_source_state_at is not null
    and src.latest_source_state_at > greatest(
      a.updated_at,
      coalesce(ar.source_watermark_at, a.updated_at)
    ) as newer_source_state_exists,
  case
    when src.latest_source_state_at is not null
      and src.latest_source_state_at > greatest(
        a.updated_at,
        coalesce(ar.source_watermark_at, a.updated_at)
      ) then 'REEVALUATE_CURRENT_REALITY'::text
    when ar.execution_valid is false then 'CURRENT_BUT_ACTION_NOT_VALID'::text
    else 'CURRENT_WITH_OBSERVED_STATE'::text
  end as awareness_state,
  coalesce(comm.recent_communications, '[]'::jsonb) as recent_communications,
  ar.created_at as awareness_evaluated_at,
  ar.source_watermark_at as evaluated_source_watermark_at,
  ar.execution_valid,
  ar.evaluation as latest_evaluation,
  greatest(a.updated_at, coalesce(ar.source_watermark_at, a.updated_at))
    as awareness_watermark_at
from public.control_plane_action_outbox a
left join lateral (
  select
    r.created_at,
    r.source_watermark_at,
    r.execution_valid,
    r.evaluation
  from public.control_plane_action_awareness_receipts r
  where r.action_id = a.id
  order by r.created_at desc
  limit 1
) ar on true
left join lateral (
  select
    max(s.source_at) as latest_source_state_at,
    count(*) filter (
      where s.source_at > greatest(
        a.updated_at,
        coalesce(ar.source_watermark_at, a.updated_at)
      )
    ) as newer_source_observations
  from (
    select greatest(c.occurred_at, c.created_at) as source_at
    from public.control_plane_communications c
    where c.case_id is not distinct from a.case_id

    union all

    select greatest(coalesce(e.observed_at, e.occurred_at), e.created_at) as source_at
    from public.control_plane_events e
    where e.case_id is not distinct from a.case_id
      and not (
        e.source_system = 'control_plane_action_outbox'
        and e.source_ref = a.id::text
      )

    union all

    select o.updated_at as source_at
    from public.control_plane_obligations o
    where o.case_id is not distinct from a.case_id
  ) s
) src on true
left join lateral (
  select coalesce(
    jsonb_agg(to_jsonb(x.*) order by x.occurred_at desc),
    '[]'::jsonb
  ) as recent_communications
  from (
    select
      c.direction,
      c.channel,
      c.counterparty,
      c.subject,
      c.occurred_at,
      c.source_system,
      c.source_ref,
      c.acknowledgement_state,
      c.delivery_state,
      c.summary
    from public.control_plane_communications c
    where c.case_id is not distinct from a.case_id
    order by c.occurred_at desc
    limit 12
  ) x
) comm on true;

comment on view public.control_plane_action_awareness_v1 is
'Live action awareness surface. It exposes whether materially newer source-bearing state exists than the action awareness watermark and supplies recent communication context. It does not encode case-specific workflow rules.';

create or replace function public.get_control_plane_action_awareness_v1(
  p_case_id text default null,
  p_action_id uuid default null,
  p_limit integer default 50
)
returns jsonb
language sql
stable
security definer
set search_path = 'pg_catalog', 'public'
as $$
  select jsonb_build_object(
    'observed_at', clock_timestamp(),
    'case_id', p_case_id,
    'action_id', p_action_id,
    'principle', 'current source-bearing state outranks cached action intent',
    'actions', coalesce(
      jsonb_agg(to_jsonb(q) order by q.priority, q.action_state_at desc),
      '[]'::jsonb
    ),
    'actions_requiring_reevaluation',
      count(*) filter (where q.newer_source_state_exists)
  )
  from (
    select *
    from public.control_plane_action_awareness_v1 v
    where (p_case_id is null or v.case_id = p_case_id)
      and (p_action_id is null or v.action_id = p_action_id)
    order by
      case v.priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end,
      v.action_state_at desc
    limit greatest(1, least(coalesce(p_limit, 50), 200))
  ) q;
$$;

revoke all on function public.get_control_plane_action_awareness_v1(text, uuid, integer)
  from public, anon, authenticated;
grant execute on function public.get_control_plane_action_awareness_v1(text, uuid, integer)
  to service_role;

create or replace function public.claim_control_plane_actions_v1(
  p_worker text,
  p_limit integer default 10,
  p_lease_seconds integer default 300
)
returns setof public.control_plane_action_outbox
language plpgsql
security definer
set search_path = 'pg_catalog', 'public'
as $$
declare
  v_now timestamptz := clock_timestamp();
begin
  if p_worker is null or length(trim(p_worker)) < 3 then
    raise exception 'worker identity required';
  end if;
  if p_limit < 1 or p_limit > 100 then
    raise exception 'limit must be between 1 and 100';
  end if;
  if p_lease_seconds < 30 or p_lease_seconds > 3600 then
    raise exception 'lease seconds must be between 30 and 3600';
  end if;

  return query
  with candidates as (
    select a.id
    from public.control_plane_action_outbox a
    join public.control_plane_action_awareness_v1 aw on aw.action_id = a.id
    where a.status in ('APPROVED', 'FAILED')
      and a.attempt_count < a.max_attempts
      and coalesce(a.next_attempt_at, a.not_before, a.created_at) <= v_now
      and (a.lease_expires_at is null or a.lease_expires_at <= v_now)
      and (not a.requires_operator_approval or a.authorization_basis is not null)
      and aw.newer_source_state_exists is false
      and coalesce(aw.execution_valid, true) is true
    order by
      case a.priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end,
      coalesce(a.next_attempt_at, a.not_before, a.created_at),
      a.created_at
    for update of a skip locked
    limit p_limit
  ), claimed as (
    update public.control_plane_action_outbox a
    set
      status = 'DISPATCHING',
      attempt_count = a.attempt_count + 1,
      last_attempt_at = v_now,
      lease_owner = trim(p_worker),
      lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
      dispatch_generation = a.dispatch_generation + 1,
      last_error = null,
      updated_at = v_now
    from candidates c
    where a.id = c.id
    returning a.*
  )
  select * from claimed;
end;
$$;

create or replace function public.control_plane_begin_authorized_attempt(
  p_action_key text,
  p_provider_plan_ref text default null,
  p_transport text default null
)
returns jsonb
language plpgsql
set search_path = 'public'
as $$
declare
  v_action public.control_plane_action_outbox%rowtype;
  v_aw public.control_plane_action_awareness_v1%rowtype;
  v_attempt integer;
  v_event_id uuid;
begin
  select *
  into v_action
  from public.control_plane_action_outbox
  where action_key = p_action_key
  for update;

  if not found then
    raise exception 'Unknown action_key: %', p_action_key;
  end if;

  if v_action.status in ('SENT', 'ACKNOWLEDGED', 'COMPLETED') then
    return jsonb_build_object(
      'action_key', v_action.action_key,
      'status', v_action.status,
      'idempotent', true,
      'attempt_count', v_action.attempt_count
    );
  end if;

  select *
  into v_aw
  from public.control_plane_action_awareness_v1
  where action_id = v_action.id;

  if v_aw.newer_source_state_exists then
    return jsonb_build_object(
      'action_id', v_action.id,
      'action_key', v_action.action_key,
      'status', v_action.status,
      'dispatch_started', false,
      'awareness_state', 'REEVALUATE_CURRENT_REALITY',
      'latest_source_state_at', v_aw.latest_source_state_at,
      'awareness_watermark_at', v_aw.awareness_watermark_at
    );
  end if;

  if v_aw.execution_valid is false then
    return jsonb_build_object(
      'action_id', v_action.id,
      'action_key', v_action.action_key,
      'status', v_action.status,
      'dispatch_started', false,
      'awareness_state', 'CURRENT_BUT_ACTION_NOT_VALID',
      'latest_evaluation', v_aw.latest_evaluation
    );
  end if;

  if v_action.status not in ('READY', 'APPROVED', 'FAILED') then
    raise exception 'Action % is not attemptable from status %', p_action_key, v_action.status;
  end if;

  if v_action.requires_operator_approval
    and nullif(btrim(coalesce(v_action.authorization_basis, '')), '') is null then
    raise exception 'Action % requires operator approval and has no authorization basis', p_action_key;
  end if;

  v_attempt := v_action.attempt_count + 1;

  update public.control_plane_action_outbox
  set
    status = 'DISPATCHING',
    attempt_count = v_attempt,
    last_attempt_at = now(),
    last_error = null,
    payload = coalesce(payload, '{}'::jsonb) || jsonb_strip_nulls(
      jsonb_build_object(
        'active_provider_plan_ref', p_provider_plan_ref,
        'active_transport', p_transport,
        'attempt_started_at', now()
      )
    ),
    updated_at = now()
  where id = v_action.id;

  insert into public.control_plane_events(
    case_id,
    event_key,
    event_type,
    source_system,
    source_ref,
    actor_ref,
    occurred_at,
    severity,
    state_before,
    state_after,
    payload
  )
  values(
    v_action.case_id,
    'action:' || v_action.id::text || ':attempt:' || v_attempt::text,
    'ACTION_ATTEMPT_STARTED',
    coalesce(p_transport, 'control_plane'),
    p_provider_plan_ref,
    'operator_authorized_execution',
    now(),
    case when v_action.priority = 'P0' then 'HIGH' else 'INFO' end,
    jsonb_build_object('status', v_action.status, 'attempt_count', v_action.attempt_count),
    jsonb_build_object('status', 'DISPATCHING', 'attempt_count', v_attempt),
    jsonb_strip_nulls(jsonb_build_object(
      'action_key', v_action.action_key,
      'provider_plan_ref', p_provider_plan_ref,
      'transport', p_transport
    ))
  )
  on conflict(event_key) do update set observed_at = now()
  returning id into v_event_id;

  update public.apex_case_execution_state
  set
    execution_state = 'TRANSMITTING',
    state_version = state_version + 1,
    last_event_id = v_event_id::text,
    last_event_at = now(),
    next_action_id = v_action.id::text,
    metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
      'active_action_key', v_action.action_key,
      'active_attempt', v_attempt
    ),
    updated_at = now()
  where case_id = v_action.case_id;

  return jsonb_build_object(
    'action_id', v_action.id,
    'action_key', v_action.action_key,
    'case_id', v_action.case_id,
    'status', 'DISPATCHING',
    'dispatch_started', true,
    'attempt_count', v_attempt,
    'event_id', v_event_id,
    'provider_plan_ref', p_provider_plan_ref,
    'awareness_state', 'CURRENT_WITH_OBSERVED_STATE'
  );
end;
$$;

create or replace view public.control_plane_continuity_spine_v1
with (security_invoker = true)
as
select
  now() as observed_at,
  (select to_jsonb(o.*) from public.operator_runtime_context_current_v1 o limit 1)
    as operator_context,
  (select to_jsonb(f.*) from public.control_plane_global_frontier_v1 f limit 1)
    as global_frontier,
  coalesce((
    select jsonb_agg(to_jsonb(c.*) order by c.node_key)
    from public.control_plane_constellation_v1 c
  ), '[]'::jsonb) as constellation,
  coalesce((
    select jsonb_agg(to_jsonb(e.*) order by e.updated_at desc)
    from public.control_plane_epistemic_state_v1 e
  ), '[]'::jsonb) as epistemic_state,
  coalesce((
    select jsonb_agg(
      jsonb_build_object(
        'action_id', a.action_id,
        'case_id', a.case_id,
        'action_key', a.action_key,
        'status', a.status,
        'priority', a.priority,
        'awareness_state', a.awareness_state,
        'newer_source_observations', a.newer_source_observations,
        'latest_source_state_at', a.latest_source_state_at,
        'awareness_watermark_at', a.awareness_watermark_at,
        'execution_valid', a.execution_valid
      )
      order by
        case a.priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end,
        a.action_state_at
    )
    from public.control_plane_action_awareness_v1 a
    where a.status in ('READY', 'APPROVED', 'FAILED', 'DISPATCHING', 'SENT')
  ), '[]'::jsonb) as action_awareness,
  (
    select count(*)
    from public.control_plane_action_awareness_v1 a
    where a.status in ('READY', 'APPROVED', 'FAILED', 'DISPATCHING', 'SENT')
      and (a.newer_source_state_exists or a.execution_valid is false)
  ) as actions_requiring_reevaluation;

comment on table public.control_plane_action_awareness_receipts is
'Append-only receipts showing that an executor evaluated the current source-bearing reality for an action. The evaluator decides validity dynamically; the table does not encode case-specific behavior rules.';
