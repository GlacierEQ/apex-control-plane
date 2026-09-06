-- Casebuilder4000 control event -> existing continuity kernel bridge.
-- This is intentionally one-way at ingestion time:
-- Casebuilder control events become continuity ingest items; the existing
-- continuity processors decide timeline projection and legal execution reducers
-- only react to their already-recognized provider event types.

alter table public.legal_case_control_receipts_v1
  drop constraint if exists legal_case_control_receipts_v1_receipt_type_check;

alter table public.legal_case_control_receipts_v1
  add constraint legal_case_control_receipts_v1_receipt_type_check
  check (
    receipt_type in (
      'event_ingested',
      'event_idempotent_replay',
      'health_upserted',
      'continuity_mirrored',
      'continuity_mirror_failed'
    )
  );

create or replace function public.legal_case_control_to_continuity_v1()
returns trigger
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_resolution jsonb;
  v_matter_key text;
  v_ingest jsonb;
  v_ingest_id uuid;
begin
  v_resolution := public.continuity_canonical_matter_v1(
    new.case_id,
    'casebuilder4000'
  );

  if coalesce((v_resolution->>'resolved')::boolean,false) then
    v_matter_key := nullif(v_resolution->>'matter_key','');
  else
    v_matter_key := null;
  end if;

  v_ingest := public.continuity_ingest_external_event_v1(
    'casebuilder4000',
    'local-control-plane',
    new.event_id,
    new.event_type,
    new.occurred_at,
    jsonb_build_object(
      'schema','casebuilder4000.control-event-continuity.v1',
      'control_event_id',new.event_id,
      'case_id',new.case_id,
      'event_type',new.event_type,
      'source',new.source,
      'correlation_id',new.correlation_id,
      'causation_id',new.causation_id,
      'idempotency_key',new.idempotency_key,
      'payload',new.payload,
      'casebuilder_received_at',new.received_at
    ),
    v_matter_key
  );

  v_ingest_id := nullif(v_ingest->>'ingest_id','')::uuid;

  if v_ingest_id is not null then
    update public.continuity_ingest_queue_v1
    set metadata =
      coalesce(metadata,'{}'::jsonb)
      || jsonb_build_object(
        'casebuilder_control_event_id',new.event_id,
        'casebuilder_case_id',new.case_id,
        'casebuilder_correlation_id',new.correlation_id,
        'casebuilder_causation_id',new.causation_id,
        'casebuilder_idempotency_key',new.idempotency_key,
        'casebuilder_matter_resolution',v_resolution,
        'bridge','legal_case_control_to_continuity_v1'
      )
    where ingest_id=v_ingest_id;
  end if;

  insert into public.legal_case_control_receipts_v1(
    case_id,
    event_id,
    receipt_type,
    outcome,
    detail
  ) values (
    new.case_id,
    new.event_id,
    'continuity_mirrored',
    'succeeded',
    jsonb_build_object(
      'ingest',v_ingest,
      'matter_resolution',v_resolution,
      'matter_key',v_matter_key,
      'source_system','casebuilder4000'
    )
  );

  return new;
exception when others then
  insert into public.legal_case_control_receipts_v1(
    case_id,
    event_id,
    receipt_type,
    outcome,
    detail
  ) values (
    new.case_id,
    new.event_id,
    'continuity_mirror_failed',
    'rejected',
    jsonb_build_object(
      'sqlstate',sqlstate,
      'message',sqlerrm,
      'source_system','casebuilder4000'
    )
  );

  insert into public.legal_control_deadletter_v1(
    matter_key,
    event_key,
    source_system,
    source_ref,
    failure_class,
    failure_detail,
    payload
  ) values (
    v_matter_key,
    'casebuilder:'||new.event_id,
    'casebuilder4000',
    'casebuilder:'||new.event_id,
    'casebuilder_continuity_mirror_failure',
    jsonb_build_object(
      'sqlstate',sqlstate,
      'message',sqlerrm
    ),
    jsonb_build_object(
      'case_id',new.case_id,
      'event_type',new.event_type,
      'correlation_id',new.correlation_id,
      'causation_id',new.causation_id,
      'payload',new.payload
    )
  );

  return new;
end;
$$;

revoke all on function public.legal_case_control_to_continuity_v1()
  from public,anon,authenticated;
grant execute on function public.legal_case_control_to_continuity_v1()
  to service_role;

drop trigger if exists legal_case_control_to_continuity_v1_trg
  on public.legal_case_control_events_v1;

create trigger legal_case_control_to_continuity_v1_trg
after insert on public.legal_case_control_events_v1
for each row
execute function public.legal_case_control_to_continuity_v1();

comment on function public.legal_case_control_to_continuity_v1() is
  'Mirrors Casebuilder4000 control events into the existing continuity ingest kernel using canonical matter resolution. It does not directly transition legal execution state.';
