create table if not exists public.continuity_matters_v1(
  matter_id uuid primary key default gen_random_uuid(),
  matter_key text not null unique,
  title text not null,
  matter_type text not null check(matter_type in ('case','project','relationship','operations','personal','other')),
  status text not null default 'active' check(status in ('active','waiting','closed','archived')),
  priority integer not null default 50 check(priority between 0 and 100),
  summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.continuity_entities_v1(
  entity_id uuid primary key default gen_random_uuid(),
  entity_key text not null unique,
  entity_type text not null check(entity_type in ('person','organization','agency','account','system','other')),
  canonical_name text not null,
  emails text[] not null default '{}'::text[],
  phones text[] not null default '{}'::text[],
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.continuity_facts_v1(
  fact_id uuid primary key default gen_random_uuid(),
  matter_id uuid references public.continuity_matters_v1(matter_id) on delete cascade,
  entity_id uuid references public.continuity_entities_v1(entity_id) on delete set null,
  fact_key text not null,
  fact_text text not null,
  epistemic_class text not null check(epistemic_class in (
    'operator_observation','source_verified','external_verified','inference','proposal','unresolved'
  )),
  source_ref text not null,
  source_hash text,
  confidence numeric(5,4) check(confidence is null or (confidence>=0 and confidence<=1)),
  valid_at timestamptz,
  superseded_by uuid references public.continuity_facts_v1(fact_id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_ref,fact_key)
);

create table if not exists public.continuity_events_v1(
  event_id uuid primary key default gen_random_uuid(),
  matter_id uuid references public.continuity_matters_v1(matter_id) on delete cascade,
  event_type text not null check(event_type in (
    'email_sent','email_received','email_delivery_failure',
    'call_planned','call_started','call_completed','call_failed',
    'calendar_event','deadline','filing','record','note','status_change','other'
  )),
  occurred_at timestamptz not null,
  source_system text not null,
  source_ref text not null unique,
  actor_entity_id uuid references public.continuity_entities_v1(entity_id) on delete set null,
  counterpart_entity_ids uuid[] not null default '{}'::uuid[],
  subject text,
  summary text,
  delivery_status text check(delivery_status is null or delivery_status in (
    'planned','sent','delivered','unknown','bounced','failed','completed'
  )),
  content_hash text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.continuity_commitments_v1(
  commitment_id uuid primary key default gen_random_uuid(),
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  source_event_id uuid references public.continuity_events_v1(event_id) on delete set null,
  commitment_type text not null check(commitment_type in (
    'response_deadline','follow_up','delivery_repair','preservation_check',
    'records_check','meeting','call_back','calendar_hold','other'
  )),
  title text not null,
  due_at timestamptz,
  due_precision text not null default 'operator_set' check(due_precision in (
    'exact','source_stated','operator_set','system_suggested','unknown'
  )),
  status text not null default 'open' check(status in ('open','in_progress','waiting','completed','cancelled','superseded')),
  priority integer not null default 50 check(priority between 0 and 100),
  owner text not null default 'operator',
  evidence_required jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.continuity_calendar_bindings_v1(
  binding_id uuid primary key default gen_random_uuid(),
  commitment_id uuid not null unique references public.continuity_commitments_v1(commitment_id) on delete cascade,
  provider text not null,
  account_key text not null,
  calendar_id text not null,
  provider_event_id text,
  sync_state text not null default 'pending' check(sync_state in ('pending','synced','drifted','error','disabled')),
  last_synced_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.continuity_context_packets_v1(
  packet_id uuid primary key default gen_random_uuid(),
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  target_entity_id uuid references public.continuity_entities_v1(entity_id) on delete set null,
  action_channel text not null check(action_channel in ('email','phone','calendar','chat','other')),
  action_purpose text not null,
  snapshot_at timestamptz not null default now(),
  context_json jsonb not null,
  snapshot_hash text not null,
  expires_at timestamptz not null,
  created_by text not null default 'apex-continuity',
  created_at timestamptz not null default now()
);

create table if not exists public.continuity_outbound_actions_v1(
  action_id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  packet_id uuid not null references public.continuity_context_packets_v1(packet_id) on delete restrict,
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  channel text not null check(channel in ('email','phone','calendar','other')),
  target text not null,
  intended_action text not null,
  status text not null default 'planned' check(status in ('planned','approved','executing','sent','completed','failed','cancelled')),
  provider_ref text,
  started_at timestamptz,
  completed_at timestamptz,
  result_json jsonb not null default '{}'::jsonb,
  error_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists continuity_events_matter_time_idx
  on public.continuity_events_v1(matter_id,occurred_at desc);
create index if not exists continuity_commitments_due_idx
  on public.continuity_commitments_v1(status,due_at);
create index if not exists continuity_facts_matter_idx
  on public.continuity_facts_v1(matter_id,epistemic_class,created_at desc);
create index if not exists continuity_packets_matter_idx
  on public.continuity_context_packets_v1(matter_id,snapshot_at desc);

alter table public.continuity_matters_v1 enable row level security;
alter table public.continuity_entities_v1 enable row level security;
alter table public.continuity_facts_v1 enable row level security;
alter table public.continuity_events_v1 enable row level security;
alter table public.continuity_commitments_v1 enable row level security;
alter table public.continuity_calendar_bindings_v1 enable row level security;
alter table public.continuity_context_packets_v1 enable row level security;
alter table public.continuity_outbound_actions_v1 enable row level security;

revoke all on table
  public.continuity_matters_v1,
  public.continuity_entities_v1,
  public.continuity_facts_v1,
  public.continuity_events_v1,
  public.continuity_commitments_v1,
  public.continuity_calendar_bindings_v1,
  public.continuity_context_packets_v1,
  public.continuity_outbound_actions_v1
from public,anon,authenticated;

grant select,insert,update,delete on table
  public.continuity_matters_v1,
  public.continuity_entities_v1,
  public.continuity_facts_v1,
  public.continuity_events_v1,
  public.continuity_commitments_v1,
  public.continuity_calendar_bindings_v1,
  public.continuity_context_packets_v1,
  public.continuity_outbound_actions_v1
to service_role;

create or replace function public.continuity_build_context_packet_v1(
  p_matter_key text,
  p_target_entity_key text,
  p_action_channel text,
  p_action_purpose text,
  p_horizon_days integer default 60
)
returns jsonb
language plpgsql
security definer
set search_path='public','extensions','pg_temp'
as $$
declare
  v_matter public.continuity_matters_v1%rowtype;
  v_target public.continuity_entities_v1%rowtype;
  v_context jsonb;
  v_hash text;
  v_packet uuid;
  v_now timestamptz:=now();
begin
  if p_action_channel not in ('email','phone','calendar','chat','other') then
    raise exception 'invalid_action_channel';
  end if;

  select * into v_matter
  from public.continuity_matters_v1
  where matter_key=p_matter_key and status<>'archived';

  if not found then raise exception 'unknown_matter'; end if;

  if p_target_entity_key is not null then
    select * into v_target
    from public.continuity_entities_v1
    where entity_key=p_target_entity_key;
    if not found then raise exception 'unknown_target_entity'; end if;
  end if;

  select jsonb_build_object(
    'schema','glaciereq.continuity.context.v1',
    'snapshot_at',v_now,
    'matter',jsonb_build_object(
      'matter_id',v_matter.matter_id,
      'matter_key',v_matter.matter_key,
      'title',v_matter.title,
      'matter_type',v_matter.matter_type,
      'status',v_matter.status,
      'priority',v_matter.priority,
      'summary',v_matter.summary,
      'metadata',v_matter.metadata
    ),
    'target',case when p_target_entity_key is null then null else jsonb_build_object(
      'entity_id',v_target.entity_id,
      'entity_key',v_target.entity_key,
      'entity_type',v_target.entity_type,
      'canonical_name',v_target.canonical_name,
      'emails',v_target.emails,
      'phones',v_target.phones,
      'metadata',v_target.metadata
    ) end,
    'facts',coalesce((
      select jsonb_agg(jsonb_build_object(
        'fact_key',f.fact_key,
        'fact_text',f.fact_text,
        'epistemic_class',f.epistemic_class,
        'source_ref',f.source_ref,
        'confidence',f.confidence,
        'valid_at',f.valid_at,
        'metadata',f.metadata
      ) order by
        case f.epistemic_class
          when 'source_verified' then 1
          when 'external_verified' then 2
          when 'operator_observation' then 3
          when 'unresolved' then 4
          when 'inference' then 5
          else 6
        end,
        f.created_at desc
      )
      from public.continuity_facts_v1 f
      where f.matter_id=v_matter.matter_id
        and f.superseded_by is null
    ),'[]'::jsonb),
    'recent_events',coalesce((
      select jsonb_agg(jsonb_build_object(
        'event_id',e.event_id,
        'event_type',e.event_type,
        'occurred_at',e.occurred_at,
        'source_system',e.source_system,
        'source_ref',e.source_ref,
        'subject',e.subject,
        'summary',e.summary,
        'delivery_status',e.delivery_status,
        'metadata',e.metadata
      ) order by e.occurred_at desc)
      from (
        select *
        from public.continuity_events_v1
        where matter_id=v_matter.matter_id
          and occurred_at>=v_now-make_interval(days=>greatest(1,least(coalesce(p_horizon_days,60),365)))
        order by occurred_at desc
        limit 100
      ) e
    ),'[]'::jsonb),
    'open_commitments',coalesce((
      select jsonb_agg(jsonb_build_object(
        'commitment_id',c.commitment_id,
        'commitment_type',c.commitment_type,
        'title',c.title,
        'due_at',c.due_at,
        'due_precision',c.due_precision,
        'status',c.status,
        'priority',c.priority,
        'owner',c.owner,
        'evidence_required',c.evidence_required,
        'metadata',c.metadata
      ) order by c.priority desc,c.due_at nulls last,c.created_at)
      from public.continuity_commitments_v1 c
      where c.matter_id=v_matter.matter_id
        and c.status in ('open','in_progress','waiting')
    ),'[]'::jsonb),
    'delivery_risks',coalesce((
      select jsonb_agg(jsonb_build_object(
        'event_id',e.event_id,
        'occurred_at',e.occurred_at,
        'subject',e.subject,
        'source_ref',e.source_ref,
        'summary',e.summary,
        'metadata',e.metadata
      ) order by e.occurred_at desc)
      from public.continuity_events_v1 e
      where e.matter_id=v_matter.matter_id
        and e.event_type='email_delivery_failure'
    ),'[]'::jsonb),
    'action',jsonb_build_object(
      'channel',p_action_channel,
      'purpose',p_action_purpose,
      'rule','READ THIS PACKET BEFORE SPEAKING OR SENDING; preserve source-vs-observation-vs-inference distinctions; do not claim delivery when delivery_status is bounced/failed/unknown; do not invent deadlines.'
    )
  ) into v_context;

  v_hash:=encode(extensions.digest(convert_to(v_context::text,'UTF8'),'sha256'),'hex');

  insert into public.continuity_context_packets_v1(
    matter_id,target_entity_id,action_channel,action_purpose,
    snapshot_at,context_json,snapshot_hash,expires_at
  ) values (
    v_matter.matter_id,
    case when p_target_entity_key is null then null else v_target.entity_id end,
    p_action_channel,p_action_purpose,v_now,v_context,v_hash,v_now+interval '24 hours'
  )
  returning packet_id into v_packet;

  return jsonb_build_object(
    'packet_id',v_packet,
    'snapshot_hash',v_hash,
    'expires_at',v_now+interval '24 hours',
    'context',v_context
  );
end;
$$;

revoke all on function public.continuity_build_context_packet_v1(text,text,text,text,integer)
  from public,anon,authenticated;
grant execute on function public.continuity_build_context_packet_v1(text,text,text,text,integer)
  to service_role;

create or replace function public.continuity_preflight_outbound_v1(
  p_packet_id uuid,
  p_channel text,
  p_target text
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_packet public.continuity_context_packets_v1%rowtype;
  v_recent_duplicate integer:=0;
  v_unresolved_failures integer:=0;
  v_overdue integer:=0;
begin
  select * into v_packet
  from public.continuity_context_packets_v1
  where packet_id=p_packet_id;

  if not found then raise exception 'unknown_context_packet'; end if;

  if v_packet.expires_at<now() then
    return jsonb_build_object(
      'ready',false,'reason','context_packet_expired',
      'packet_id',p_packet_id,'expired_at',v_packet.expires_at
    );
  end if;

  if p_channel<>v_packet.action_channel then
    return jsonb_build_object(
      'ready',false,'reason','channel_mismatch',
      'packet_channel',v_packet.action_channel,'requested_channel',p_channel
    );
  end if;

  select count(*) into v_recent_duplicate
  from public.continuity_outbound_actions_v1
  where matter_id=v_packet.matter_id
    and channel=p_channel
    and target=p_target
    and created_at>now()-interval '60 minutes'
    and status in ('planned','approved','executing','sent','completed');

  select count(*) into v_unresolved_failures
  from public.continuity_events_v1
  where matter_id=v_packet.matter_id
    and event_type='email_delivery_failure'
    and occurred_at>now()-interval '30 days';

  select count(*) into v_overdue
  from public.continuity_commitments_v1
  where matter_id=v_packet.matter_id
    and status in ('open','in_progress','waiting')
    and due_at is not null
    and due_at<now();

  return jsonb_build_object(
    'ready',v_recent_duplicate=0,
    'reason',case when v_recent_duplicate>0 then 'recent_duplicate_action' else 'ready' end,
    'packet_id',p_packet_id,
    'snapshot_hash',v_packet.snapshot_hash,
    'target',p_target,
    'warnings',jsonb_build_object(
      'recent_duplicate_actions',v_recent_duplicate,
      'unresolved_delivery_failures',v_unresolved_failures,
      'overdue_commitments',v_overdue
    )
  );
end;
$$;

revoke all on function public.continuity_preflight_outbound_v1(uuid,text,text)
  from public,anon,authenticated;
grant execute on function public.continuity_preflight_outbound_v1(uuid,text,text)
  to service_role;

create or replace view public.continuity_unified_timeline_v1 as
select
  e.matter_id,
  e.occurred_at as timeline_at,
  e.event_type as timeline_type,
  e.subject as title,
  e.summary,
  e.source_system,
  e.source_ref,
  e.delivery_status,
  e.metadata
from public.continuity_events_v1 e
union all
select
  c.matter_id,
  c.due_at as timeline_at,
  'commitment:'||c.commitment_type as timeline_type,
  c.title,
  c.status||' / priority '||c.priority::text as summary,
  'continuity' as source_system,
  c.commitment_id::text as source_ref,
  null::text as delivery_status,
  c.metadata
from public.continuity_commitments_v1 c
where c.due_at is not null;

revoke all on public.continuity_unified_timeline_v1 from public,anon,authenticated;
grant select on public.continuity_unified_timeline_v1 to service_role;

