create or replace function public.continuity_prepare_outbound_v1(
  p_matter_key text,
  p_target_entity_key text,
  p_channel text,
  p_target text,
  p_action_purpose text,
  p_idempotency_key text
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_packet jsonb;
  v_packet_id uuid;
  v_preflight jsonb;
  v_matter_id uuid;
  v_action public.continuity_outbound_actions_v1%rowtype;
  v_existing public.continuity_outbound_actions_v1%rowtype;
  v_receipt jsonb;
begin
  if coalesce(trim(p_idempotency_key),'')='' then raise exception 'idempotency_key_required'; end if;
  if coalesce(trim(p_target),'')='' then raise exception 'target_required'; end if;

  select matter_id into v_matter_id
  from public.continuity_matters_v1
  where matter_key=p_matter_key and status<>'archived';
  if not found then raise exception 'unknown_matter'; end if;

  select * into v_existing
  from public.continuity_outbound_actions_v1
  where idempotency_key=p_idempotency_key;

  if found then
    return jsonb_build_object(
      'created',false,
      'idempotent_replay',true,
      'action_id',v_existing.action_id,
      'status',v_existing.status,
      'provider_ref',v_existing.provider_ref
    );
  end if;

  v_packet:=public.continuity_build_context_packet_v1(
    p_matter_key,p_target_entity_key,p_channel,p_action_purpose,60
  );
  v_packet_id:=(v_packet->>'packet_id')::uuid;

  v_preflight:=public.continuity_preflight_outbound_v2(
    v_packet_id,p_channel,p_target
  );

  if not coalesce((v_preflight->>'ready')::boolean,false) then
    return jsonb_build_object(
      'created',false,
      'ready',false,
      'reason',v_preflight->>'reason',
      'packet_id',v_packet_id,
      'preflight',v_preflight,
      'context',v_packet->'context'
    );
  end if;

  insert into public.continuity_outbound_actions_v1(
    idempotency_key,packet_id,matter_id,channel,target,intended_action,status
  ) values (
    p_idempotency_key,v_packet_id,v_matter_id,p_channel,p_target,p_action_purpose,'approved'
  )
  returning * into v_action;

  v_receipt:=public.continuity_record_action_receipt_v1(
    v_action.action_id,p_matter_key,v_packet_id,p_channel,'preflight','approved',
    null,jsonb_build_object('preflight',v_preflight)
  );

  return jsonb_build_object(
    'created',true,
    'ready',true,
    'action_id',v_action.action_id,
    'packet_id',v_packet_id,
    'preflight',v_preflight,
    'preflight_receipt',v_receipt,
    'context',v_packet->'context'
  );
end;
$$;

revoke all on function public.continuity_prepare_outbound_v1(
  text,text,text,text,text,text
) from public,anon,authenticated;
grant execute on function public.continuity_prepare_outbound_v1(
  text,text,text,text,text,text
) to service_role;

create or replace function public.continuity_start_outbound_v1(
  p_action_id uuid,
  p_provider_ref text default null,
  p_detail jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_action public.continuity_outbound_actions_v1%rowtype;
  v_matter_key text;
  v_receipt jsonb;
begin
  select * into v_action
  from public.continuity_outbound_actions_v1
  where action_id=p_action_id
  for update;

  if not found then raise exception 'unknown_action'; end if;

  select matter_key into v_matter_key
  from public.continuity_matters_v1
  where matter_id=v_action.matter_id;

  if v_action.status not in ('approved','executing') then
    raise exception 'action_not_startable';
  end if;

  update public.continuity_outbound_actions_v1
  set status='executing',
      provider_ref=coalesce(p_provider_ref,provider_ref),
      started_at=coalesce(started_at,now()),
      updated_at=now()
  where action_id=p_action_id
  returning * into v_action;

  v_receipt:=public.continuity_record_action_receipt_v1(
    v_action.action_id,v_matter_key,v_action.packet_id,v_action.channel,'started','executing',
    v_action.provider_ref,coalesce(p_detail,'{}'::jsonb)
  );

  return jsonb_build_object(
    'action_id',v_action.action_id,'status',v_action.status,
    'provider_ref',v_action.provider_ref,'receipt',v_receipt
  );
end;
$$;

revoke all on function public.continuity_start_outbound_v1(uuid,text,jsonb)
  from public,anon,authenticated;
grant execute on function public.continuity_start_outbound_v1(uuid,text,jsonb)
  to service_role;

create or replace function public.continuity_finish_outbound_v1(
  p_action_id uuid,
  p_terminal_status text,
  p_provider_ref text default null,
  p_result jsonb default '{}'::jsonb,
  p_error jsonb default '{}'::jsonb,
  p_followup_title text default null,
  p_followup_type text default null,
  p_followup_due_at timestamptz default null,
  p_followup_priority integer default 80,
  p_followup_evidence jsonb default '[]'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_action public.continuity_outbound_actions_v1%rowtype;
  v_matter_key text;
  v_receipt_type text;
  v_receipt jsonb;
  v_commitment_id uuid;
  v_event_type text;
  v_event_id uuid;
  v_source_ref text;
begin
  if p_terminal_status not in ('sent','completed','failed','cancelled') then
    raise exception 'invalid_terminal_status';
  end if;

  select * into v_action
  from public.continuity_outbound_actions_v1
  where action_id=p_action_id
  for update;

  if not found then raise exception 'unknown_action'; end if;

  select matter_key into v_matter_key
  from public.continuity_matters_v1
  where matter_id=v_action.matter_id;

  if v_action.status in ('completed','failed','cancelled') then
    return jsonb_build_object(
      'idempotent_replay',true,'action_id',v_action.action_id,'status',v_action.status,
      'provider_ref',v_action.provider_ref
    );
  end if;
  if v_action.status not in ('approved','executing','sent') then
    raise exception 'action_not_finishable';
  end if;

  update public.continuity_outbound_actions_v1
  set status=p_terminal_status,
      provider_ref=coalesce(p_provider_ref,provider_ref),
      result_json=coalesce(p_result,'{}'::jsonb),
      error_json=coalesce(p_error,'{}'::jsonb),
      completed_at=case when p_terminal_status in ('completed','failed','cancelled') then now() else completed_at end,
      updated_at=now()
  where action_id=p_action_id
  returning * into v_action;

  v_receipt_type:=case
    when p_terminal_status='sent' then 'sent'
    when p_terminal_status='completed' then 'completed'
    when p_terminal_status='failed' then 'failed'
    else 'cancelled'
  end;

  v_receipt:=public.continuity_record_action_receipt_v1(
    v_action.action_id,v_matter_key,v_action.packet_id,v_action.channel,v_receipt_type,
    p_terminal_status,v_action.provider_ref,
    jsonb_build_object('result',coalesce(p_result,'{}'::jsonb),'error',coalesce(p_error,'{}'::jsonb))
  );

  v_event_type:=case
    when v_action.channel='email' and p_terminal_status in ('sent','completed') then 'email_sent'
    when v_action.channel='email' and p_terminal_status='failed' then 'email_delivery_failure'
    when v_action.channel='phone' and p_terminal_status='completed' then 'call_completed'
    when v_action.channel='phone' and p_terminal_status='failed' then 'call_failed'
    when v_action.channel='calendar' then 'calendar_event'
    else 'status_change'
  end;

  v_source_ref:=coalesce(v_action.provider_ref,'continuity-action:'||v_action.action_id::text);

  insert into public.continuity_events_v1(
    matter_id,event_type,occurred_at,source_system,source_ref,subject,summary,delivery_status,metadata
  ) values (
    v_action.matter_id,v_event_type,now(),v_action.channel,v_source_ref,
    v_action.intended_action,
    coalesce(p_result->>'summary',p_error->>'message',v_action.intended_action),
    case
      when p_terminal_status='sent' then 'sent'
      when p_terminal_status='completed' then 'completed'
      when p_terminal_status='failed' then 'failed'
      else 'unknown'
    end,
    jsonb_build_object(
      'action_id',v_action.action_id,
      'packet_id',v_action.packet_id,
      'target',v_action.target,
      'provider_ref',v_action.provider_ref,
      'result',coalesce(p_result,'{}'::jsonb),
      'error',coalesce(p_error,'{}'::jsonb)
    )
  )
  on conflict(source_ref) do update set
    summary=excluded.summary,
    delivery_status=excluded.delivery_status,
    metadata=public.continuity_events_v1.metadata||excluded.metadata
  returning event_id into v_event_id;

  if p_followup_title is not null then
    if p_followup_type not in (
      'response_deadline','follow_up','delivery_repair','preservation_check',
      'records_check','meeting','call_back','calendar_hold','other'
    ) then
      raise exception 'invalid_followup_type';
    end if;

    insert into public.continuity_commitments_v1(
      matter_id,source_event_id,commitment_type,title,due_at,due_precision,
      status,priority,evidence_required,metadata
    ) values (
      v_action.matter_id,v_event_id,p_followup_type,p_followup_title,p_followup_due_at,
      case when p_followup_due_at is null then 'unknown' else 'operator_set' end,
      'open',greatest(0,least(coalesce(p_followup_priority,80),100)),
      coalesce(p_followup_evidence,'[]'::jsonb),
      jsonb_build_object('source_action_id',v_action.action_id,'provider_ref',v_action.provider_ref)
    )
    returning commitment_id into v_commitment_id;

    perform public.continuity_record_action_receipt_v1(
      v_action.action_id,v_matter_key,v_action.packet_id,v_action.channel,'followup_created',
      'open',v_action.provider_ref,
      jsonb_build_object('commitment_id',v_commitment_id,'title',p_followup_title,'due_at',p_followup_due_at)
    );
  end if;

  return jsonb_build_object(
    'action_id',v_action.action_id,
    'status',v_action.status,
    'provider_ref',v_action.provider_ref,
    'event_id',v_event_id,
    'receipt',v_receipt,
    'followup_commitment_id',v_commitment_id
  );
end;
$$;

revoke all on function public.continuity_finish_outbound_v1(
  uuid,text,text,jsonb,jsonb,text,text,timestamptz,integer,jsonb
) from public,anon,authenticated;
grant execute on function public.continuity_finish_outbound_v1(
  uuid,text,text,jsonb,jsonb,text,text,timestamptz,integer,jsonb
) to service_role;

insert into public.continuity_control_state_v1(control_key,enabled,state)
values(
  'outbound_transaction_contract',true,
  jsonb_build_object(
    'version',1,
    'prepare','continuity_prepare_outbound_v1',
    'start','continuity_start_outbound_v1',
    'finish','continuity_finish_outbound_v1',
    'channels',jsonb_build_array('email','phone','calendar'),
    'rule','prepare -> preflight receipt -> provider action -> start/finish receipts -> event -> follow-up commitment'
  )
)
on conflict(control_key) do update set
  enabled=true,state=public.continuity_control_state_v1.state||excluded.state,updated_at=now();

