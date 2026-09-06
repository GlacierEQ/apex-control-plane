create table if not exists public.continuity_sync_cursors_v1(
  cursor_id uuid primary key default gen_random_uuid(),
  source_system text not null,
  account_key text not null,
  resource_scope text not null,
  cursor_value text,
  last_observed_at timestamptz,
  last_success_at timestamptz,
  last_error_at timestamptz,
  error_state jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(source_system,account_key,resource_scope)
);

create table if not exists public.continuity_ingest_queue_v1(
  ingest_id uuid primary key default gen_random_uuid(),
  source_system text not null,
  account_key text not null,
  external_id text not null,
  external_type text not null,
  occurred_at timestamptz not null,
  source_ref text not null unique,
  payload_hash text not null,
  payload jsonb not null,
  matter_id uuid references public.continuity_matters_v1(matter_id) on delete set null,
  binding_state text not null default 'unresolved'
    check(binding_state in ('unresolved','bound','ignored','quarantined')),
  processing_state text not null default 'new'
    check(processing_state in ('new','normalized','processed','error')),
  error_state jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  unique(source_system,account_key,external_id)
);

create table if not exists public.continuity_action_receipts_v1(
  receipt_id uuid primary key default gen_random_uuid(),
  action_id uuid references public.continuity_outbound_actions_v1(action_id) on delete set null,
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  packet_id uuid references public.continuity_context_packets_v1(packet_id) on delete set null,
  channel text not null check(channel in ('email','phone','calendar','other')),
  receipt_type text not null check(receipt_type in (
    'preflight','planned','started','provider_accepted','sent','delivered',
    'completed','failed','bounced','callback_required','followup_created',
    'calendar_bound','calendar_updated','cancelled'
  )),
  outcome text not null,
  provider_ref text,
  payload_hash text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.continuity_matter_routes_v1(
  route_id uuid primary key default gen_random_uuid(),
  matter_id uuid not null references public.continuity_matters_v1(matter_id) on delete cascade,
  match_type text not null check(match_type in ('exact','contains','regex','email','phone','external_id')),
  match_value text not null,
  weight integer not null default 50 check(weight between 0 and 100),
  source_system text,
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.continuity_control_state_v1(
  control_key text primary key,
  enabled boolean not null default true,
  state jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists continuity_ingest_binding_idx
  on public.continuity_ingest_queue_v1(binding_state,processing_state,occurred_at desc);
create index if not exists continuity_receipts_matter_idx
  on public.continuity_action_receipts_v1(matter_id,created_at desc);
create index if not exists continuity_routes_lookup_idx
  on public.continuity_matter_routes_v1(enabled,match_type,match_value);
create unique index if not exists continuity_routes_unique_idx
  on public.continuity_matter_routes_v1(
    matter_id,match_type,match_value,coalesce(source_system,'')
  );

alter table public.continuity_sync_cursors_v1 enable row level security;
alter table public.continuity_ingest_queue_v1 enable row level security;
alter table public.continuity_action_receipts_v1 enable row level security;
alter table public.continuity_matter_routes_v1 enable row level security;
alter table public.continuity_control_state_v1 enable row level security;

revoke all on table
  public.continuity_sync_cursors_v1,
  public.continuity_ingest_queue_v1,
  public.continuity_action_receipts_v1,
  public.continuity_matter_routes_v1,
  public.continuity_control_state_v1
from public,anon,authenticated;

grant select,insert,update,delete on table
  public.continuity_sync_cursors_v1,
  public.continuity_ingest_queue_v1,
  public.continuity_matter_routes_v1,
  public.continuity_control_state_v1
to service_role;

grant select,insert on table public.continuity_action_receipts_v1 to service_role;

create or replace function public.continuity_receipts_append_only_v1()
returns trigger
language plpgsql
set search_path='public','pg_temp'
as $$
begin
  raise exception 'continuity_action_receipts_v1 is append-only';
end;
$$;

drop trigger if exists continuity_action_receipts_append_only
  on public.continuity_action_receipts_v1;
create trigger continuity_action_receipts_append_only
before update or delete on public.continuity_action_receipts_v1
for each row execute function public.continuity_receipts_append_only_v1();

create or replace function public.continuity_ingest_external_event_v1(
  p_source_system text,
  p_account_key text,
  p_external_id text,
  p_external_type text,
  p_occurred_at timestamptz,
  p_payload jsonb,
  p_matter_key text default null
)
returns jsonb
language plpgsql
security definer
set search_path='public','extensions','pg_temp'
as $$
declare
  v_source_ref text;
  v_hash text;
  v_matter_id uuid;
  v_ingest public.continuity_ingest_queue_v1%rowtype;
begin
  if coalesce(trim(p_source_system),'')='' then raise exception 'source_system_required'; end if;
  if coalesce(trim(p_account_key),'')='' then raise exception 'account_key_required'; end if;
  if coalesce(trim(p_external_id),'')='' then raise exception 'external_id_required'; end if;
  if jsonb_typeof(coalesce(p_payload,'{}'::jsonb))<>'object' then raise exception 'payload_must_be_object'; end if;

  v_source_ref:=p_source_system||':'||p_account_key||':'||p_external_id;
  v_hash:=encode(extensions.digest(convert_to(coalesce(p_payload,'{}'::jsonb)::text,'UTF8'),'sha256'),'hex');

  if p_matter_key is not null then
    select matter_id into v_matter_id
    from public.continuity_matters_v1
    where matter_key=p_matter_key and status<>'archived';
    if not found then raise exception 'unknown_matter'; end if;
  end if;

  insert into public.continuity_ingest_queue_v1(
    source_system,account_key,external_id,external_type,occurred_at,
    source_ref,payload_hash,payload,matter_id,binding_state,processing_state
  ) values (
    p_source_system,p_account_key,p_external_id,p_external_type,p_occurred_at,
    v_source_ref,v_hash,coalesce(p_payload,'{}'::jsonb),v_matter_id,
    case when v_matter_id is null then 'unresolved' else 'bound' end,
    'new'
  )
  on conflict(source_system,account_key,external_id) do update set
    payload=excluded.payload,
    payload_hash=excluded.payload_hash,
    occurred_at=excluded.occurred_at,
    matter_id=coalesce(public.continuity_ingest_queue_v1.matter_id,excluded.matter_id),
    binding_state=case
      when public.continuity_ingest_queue_v1.matter_id is not null or excluded.matter_id is not null then 'bound'
      else public.continuity_ingest_queue_v1.binding_state
    end
  returning * into v_ingest;

  return jsonb_build_object(
    'ingest_id',v_ingest.ingest_id,
    'source_ref',v_ingest.source_ref,
    'payload_hash',v_ingest.payload_hash,
    'binding_state',v_ingest.binding_state,
    'processing_state',v_ingest.processing_state
  );
end;
$$;

revoke all on function public.continuity_ingest_external_event_v1(
  text,text,text,text,timestamptz,jsonb,text
) from public,anon,authenticated;
grant execute on function public.continuity_ingest_external_event_v1(
  text,text,text,text,timestamptz,jsonb,text
) to service_role;

create or replace function public.continuity_record_action_receipt_v1(
  p_action_id uuid,
  p_matter_key text,
  p_packet_id uuid,
  p_channel text,
  p_receipt_type text,
  p_outcome text,
  p_provider_ref text default null,
  p_detail jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','extensions','pg_temp'
as $$
declare
  v_matter_id uuid;
  v_hash text;
  v_receipt uuid;
begin
  select matter_id into v_matter_id
  from public.continuity_matters_v1
  where matter_key=p_matter_key;
  if not found then raise exception 'unknown_matter'; end if;

  v_hash:=encode(
    extensions.digest(
      convert_to(jsonb_build_object(
        'action_id',p_action_id,
        'packet_id',p_packet_id,
        'channel',p_channel,
        'receipt_type',p_receipt_type,
        'outcome',p_outcome,
        'provider_ref',p_provider_ref,
        'detail',coalesce(p_detail,'{}'::jsonb)
      )::text,'UTF8'),
      'sha256'
    ),
    'hex'
  );

  insert into public.continuity_action_receipts_v1(
    action_id,matter_id,packet_id,channel,receipt_type,outcome,provider_ref,payload_hash,detail
  ) values (
    p_action_id,v_matter_id,p_packet_id,p_channel,p_receipt_type,p_outcome,p_provider_ref,v_hash,
    coalesce(p_detail,'{}'::jsonb)
  )
  returning receipt_id into v_receipt;

  return jsonb_build_object('receipt_id',v_receipt,'payload_hash',v_hash);
end;
$$;

revoke all on function public.continuity_record_action_receipt_v1(
  uuid,text,uuid,text,text,text,text,jsonb
) from public,anon,authenticated;
grant execute on function public.continuity_record_action_receipt_v1(
  uuid,text,uuid,text,text,text,text,jsonb
) to service_role;

create or replace function public.continuity_preflight_outbound_v2(
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
  v_matter_updated timestamptz;
  v_latest_fact timestamptz;
  v_latest_event timestamptz;
  v_latest_commitment timestamptz;
  v_recent_duplicate integer:=0;
  v_unresolved_failures integer:=0;
  v_overdue integer:=0;
  v_target_bounced integer:=0;
  v_stale boolean:=false;
  v_block_reason text:=null;
begin
  select * into v_packet
  from public.continuity_context_packets_v1
  where packet_id=p_packet_id;

  if not found then raise exception 'unknown_context_packet'; end if;

  if v_packet.expires_at<now() then
    return jsonb_build_object('ready',false,'reason','context_packet_expired','packet_id',p_packet_id);
  end if;

  if p_channel<>v_packet.action_channel then
    return jsonb_build_object('ready',false,'reason','channel_mismatch','packet_channel',v_packet.action_channel,'requested_channel',p_channel);
  end if;

  select updated_at into v_matter_updated
  from public.continuity_matters_v1 where matter_id=v_packet.matter_id;

  select max(created_at) into v_latest_fact
  from public.continuity_facts_v1
  where matter_id=v_packet.matter_id and superseded_by is null;

  select max(created_at) into v_latest_event
  from public.continuity_events_v1
  where matter_id=v_packet.matter_id;

  select max(updated_at) into v_latest_commitment
  from public.continuity_commitments_v1
  where matter_id=v_packet.matter_id;

  v_stale :=
    greatest(
      coalesce(v_matter_updated,'epoch'::timestamptz),
      coalesce(v_latest_fact,'epoch'::timestamptz),
      coalesce(v_latest_event,'epoch'::timestamptz),
      coalesce(v_latest_commitment,'epoch'::timestamptz)
    ) > v_packet.snapshot_at;

  select count(*) into v_recent_duplicate
  from public.continuity_outbound_actions_v1
  where matter_id=v_packet.matter_id
    and channel=p_channel
    and lower(target)=lower(p_target)
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
    and due_at is not null and due_at<now();

  if p_channel='email' then
    select count(*) into v_target_bounced
    from public.continuity_events_v1
    where matter_id=v_packet.matter_id
      and event_type='email_delivery_failure'
      and lower(coalesce(metadata->>'failed_recipient',''))=lower(p_target)
      and occurred_at>now()-interval '30 days';
  end if;

  if v_stale then v_block_reason:='context_packet_stale';
  elsif v_recent_duplicate>0 then v_block_reason:='recent_duplicate_action';
  elsif v_target_bounced>0 and lower(v_packet.action_purpose) not like '%repair%' then
    v_block_reason:='target_has_unrepaired_delivery_failure';
  end if;

  return jsonb_build_object(
    'ready',v_block_reason is null,
    'reason',coalesce(v_block_reason,'ready'),
    'packet_id',p_packet_id,
    'snapshot_hash',v_packet.snapshot_hash,
    'target',p_target,
    'warnings',jsonb_build_object(
      'context_stale',v_stale,
      'recent_duplicate_actions',v_recent_duplicate,
      'unresolved_delivery_failures',v_unresolved_failures,
      'target_bounced_recently',v_target_bounced,
      'overdue_commitments',v_overdue
    )
  );
end;
$$;

revoke all on function public.continuity_preflight_outbound_v2(uuid,text,text)
  from public,anon,authenticated;
grant execute on function public.continuity_preflight_outbound_v2(uuid,text,text)
  to service_role;

create or replace view public.continuity_attention_queue_v1 as
with delivery as (
  select
    e.matter_id,
    'delivery_failure'::text as attention_type,
    100 as priority,
    e.occurred_at as attention_at,
    e.subject as title,
    e.source_ref,
    jsonb_build_object(
      'summary',e.summary,
      'failed_recipient',e.metadata->>'failed_recipient',
      'smtp_status',e.metadata->>'smtp_status'
    ) as detail
  from public.continuity_events_v1 e
  where e.event_type='email_delivery_failure'
    and not exists(
      select 1 from public.continuity_commitments_v1 c
      where c.matter_id=e.matter_id
        and c.commitment_type='delivery_repair'
        and c.source_event_id=e.event_id
        and c.status='completed'
    )
),
overdue as (
  select
    c.matter_id,
    'overdue_commitment'::text as attention_type,
    c.priority,
    c.due_at as attention_at,
    c.title,
    c.commitment_id::text as source_ref,
    jsonb_build_object(
      'commitment_type',c.commitment_type,
      'status',c.status,
      'due_precision',c.due_precision,
      'evidence_required',c.evidence_required
    ) as detail
  from public.continuity_commitments_v1 c
  where c.status in ('open','in_progress','waiting')
    and c.due_at is not null
    and c.due_at<now()
),
unbound as (
  select
    q.matter_id,
    'unbound_ingest'::text as attention_type,
    90 as priority,
    q.occurred_at as attention_at,
    q.external_type||' from '||q.source_system as title,
    q.source_ref,
    jsonb_build_object(
      'account_key',q.account_key,
      'payload_hash',q.payload_hash,
      'external_id',q.external_id
    ) as detail
  from public.continuity_ingest_queue_v1 q
  where q.binding_state='unresolved'
    and q.processing_state<>'processed'
),
calendar_drift as (
  select
    c.matter_id,
    'calendar_binding_'||b.sync_state as attention_type,
    c.priority,
    coalesce(c.due_at,b.updated_at) as attention_at,
    c.title,
    b.binding_id::text as source_ref,
    jsonb_build_object(
      'provider',b.provider,
      'account_key',b.account_key,
      'provider_event_id',b.provider_event_id,
      'sync_state',b.sync_state
    ) as detail
  from public.continuity_calendar_bindings_v1 b
  join public.continuity_commitments_v1 c on c.commitment_id=b.commitment_id
  where b.sync_state in ('drifted','error')
)
select * from delivery
union all select * from overdue
union all select * from unbound
union all select * from calendar_drift;

revoke all on public.continuity_attention_queue_v1 from public,anon,authenticated;
grant select on public.continuity_attention_queue_v1 to service_role;

create or replace view public.continuity_actionable_matters_v1 as
select
  m.matter_id,
  m.matter_key,
  m.title,
  m.priority,
  m.status,
  count(a.source_ref) as attention_count,
  max(a.priority) as max_attention_priority,
  min(a.attention_at) as oldest_attention_at,
  coalesce(jsonb_agg(
    jsonb_build_object(
      'attention_type',a.attention_type,
      'priority',a.priority,
      'attention_at',a.attention_at,
      'title',a.title,
      'source_ref',a.source_ref,
      'detail',a.detail
    ) order by a.priority desc,a.attention_at
  ) filter(where a.source_ref is not null),'[]'::jsonb) as attention
from public.continuity_matters_v1 m
left join public.continuity_attention_queue_v1 a on a.matter_id=m.matter_id
where m.status in ('active','waiting')
group by m.matter_id,m.matter_key,m.title,m.priority,m.status;

revoke all on public.continuity_actionable_matters_v1 from public,anon,authenticated;
grant select on public.continuity_actionable_matters_v1 to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values
('continuity_loop',true,jsonb_build_object(
  'version',2,
  'channels',jsonb_build_array('email','phone','calendar'),
  'context_packet_ttl_hours',24,
  'duplicate_window_minutes',60,
  'preflight_function','continuity_preflight_outbound_v2',
  'attention_view','continuity_attention_queue_v1',
  'action_rule','No outbound email/call/calendar mutation without a fresh matter-bound context packet and preflight receipt.',
  'post_action_rule','Every provider action must be written back as an event and append-only receipt; every promise/date becomes a commitment and calendar binding.',
  'status','active'
))
on conflict(control_key) do update set
  enabled=excluded.enabled,
  state=public.continuity_control_state_v1.state||excluded.state,
  updated_at=now();

