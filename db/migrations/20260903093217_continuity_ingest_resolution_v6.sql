create or replace function public.continuity_ingest_and_resolve_v1(
  p_source_system text,
  p_account_key text,
  p_external_id text,
  p_external_type text,
  p_occurred_at timestamptz,
  p_payload jsonb,
  p_subject text default null,
  p_body text default null,
  p_addresses text[] default '{}'::text[],
  p_phones text[] default '{}'::text[],
  p_external_ids text[] default '{}'::text[]
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_resolution jsonb;
  v_matter_key text:=null;
  v_ingest jsonb;
  v_ingest_id uuid;
begin
  v_resolution:=public.continuity_resolve_matter_v1(
    p_source_system,p_subject,p_body,
    coalesce(p_addresses,'{}'::text[]),
    coalesce(p_phones,'{}'::text[]),
    coalesce(p_external_ids,'{}'::text[])
  );

  if coalesce((v_resolution->>'auto_bind')::boolean,false) then
    v_matter_key:=v_resolution->>'matter_key';
  end if;

  v_ingest:=public.continuity_ingest_external_event_v1(
    p_source_system,p_account_key,p_external_id,p_external_type,p_occurred_at,
    coalesce(p_payload,'{}'::jsonb),v_matter_key
  );

  v_ingest_id:=(v_ingest->>'ingest_id')::uuid;

  update public.continuity_ingest_queue_v1
  set metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
        'resolution',v_resolution,
        'routing_subject_present',p_subject is not null,
        'routing_addresses_count',coalesce(array_length(p_addresses,1),0),
        'routing_phones_count',coalesce(array_length(p_phones,1),0),
        'routing_external_ids_count',coalesce(array_length(p_external_ids,1),0)
      )
  where ingest_id=v_ingest_id;

  return jsonb_build_object(
    'ingest',v_ingest,
    'resolution',v_resolution,
    'bound',v_matter_key is not null,
    'matter_key',v_matter_key
  );
end;
$$;

revoke all on function public.continuity_ingest_and_resolve_v1(
  text,text,text,text,timestamptz,jsonb,text,text,text[],text[],text[]
) from public,anon,authenticated;
grant execute on function public.continuity_ingest_and_resolve_v1(
  text,text,text,text,timestamptz,jsonb,text,text,text[],text[],text[]
) to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'ingest_resolution_contract',true,
  jsonb_build_object(
    'version',1,
    'function','continuity_ingest_and_resolve_v1',
    'resolver','continuity_resolve_matter_v1',
    'ambiguous_policy','leave_unresolved',
    'weak_signal_policy','leave_unresolved',
    'rule','Provider events are ingested idempotently; only high-confidence resolver output binds a matter automatically.'
  )
)
on conflict(control_key) do update set
  enabled=true,
  state=public.continuity_control_state_v1.state||excluded.state,
  updated_at=now();

