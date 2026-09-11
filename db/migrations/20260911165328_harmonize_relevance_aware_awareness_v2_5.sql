create or replace view public.control_plane_action_source_relevance_v2
with (security_invoker=true) as
select a.id action_id,'COMMUNICATION'::text source_kind,c.id::text source_id,c.source_ref,
       greatest(c.occurred_at,c.created_at) source_at,
       case when c.metadata->>'action_id'=a.id::text
               or c.metadata->>'action_key'=a.action_key
               or (nullif(a.provider_receipt->>'message_id','') is not null and c.source_ref=a.provider_receipt->>'message_id')
               or (nullif(a.provider_receipt->>'thread_id','') is not null and c.provider_thread_ref=a.provider_receipt->>'thread_id')
               or (nullif(a.payload->>'provider_thread_ref','') is not null and c.provider_thread_ref=a.payload->>'provider_thread_ref')
               or public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',c.counterparty,c.subject,c.summary,c.metadata::text))
            then 'HARD' else 'SOFT' end relevance_class,
       case when c.metadata->>'action_id'=a.id::text or c.metadata->>'action_key'=a.action_key then 'EXPLICIT_ACTION_LINK'
            when nullif(a.provider_receipt->>'message_id','') is not null and c.source_ref=a.provider_receipt->>'message_id' then 'PROVIDER_MESSAGE_LINK'
            when nullif(a.provider_receipt->>'thread_id','') is not null and c.provider_thread_ref=a.provider_receipt->>'thread_id' then 'PROVIDER_THREAD_LINK'
            when nullif(a.payload->>'provider_thread_ref','') is not null and c.provider_thread_ref=a.payload->>'provider_thread_ref' then 'PROVIDER_THREAD_LINK'
            when public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',c.counterparty,c.subject,c.summary,c.metadata::text)) then 'TARGET_MATCH'
            else 'CASE_CONTEXT_ONLY' end relevance_reason
from public.control_plane_action_outbox a
join public.control_plane_communications c on (
  (a.case_id is not null and c.case_id=a.case_id)
  or c.metadata->>'action_id'=a.id::text
  or c.metadata->>'action_key'=a.action_key
  or (nullif(a.provider_receipt->>'message_id','') is not null and c.source_ref=a.provider_receipt->>'message_id')
  or (nullif(a.provider_receipt->>'thread_id','') is not null and c.provider_thread_ref=a.provider_receipt->>'thread_id')
  or (nullif(a.payload->>'provider_thread_ref','') is not null and c.provider_thread_ref=a.payload->>'provider_thread_ref')
)
union all
select a.id,'EVENT',e.id::text,e.source_ref,greatest(coalesce(e.observed_at,e.occurred_at),e.created_at),
       case when e.id=a.source_event_id
               or e.payload->>'action_id'=a.id::text
               or e.payload->>'action_key'=a.action_key
               or lower(coalesce(e.payload->>'global_execution_gate','')) in ('true','1','yes')
               or (nullif(a.provider_receipt->>'message_id','') is not null and e.source_ref=a.provider_receipt->>'message_id')
               or public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',e.event_type,e.source_system,e.source_ref,e.actor_ref,e.payload::text,e.state_after::text))
            then 'HARD' else 'SOFT' end,
       case when e.id=a.source_event_id then 'ACTION_SOURCE_EVENT'
            when e.payload->>'action_id'=a.id::text or e.payload->>'action_key'=a.action_key then 'EXPLICIT_ACTION_LINK'
            when lower(coalesce(e.payload->>'global_execution_gate','')) in ('true','1','yes') then 'DECLARED_GLOBAL_EXECUTION_GATE'
            when nullif(a.provider_receipt->>'message_id','') is not null and e.source_ref=a.provider_receipt->>'message_id' then 'PROVIDER_MESSAGE_LINK'
            when public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',e.event_type,e.source_system,e.source_ref,e.actor_ref,e.payload::text,e.state_after::text)) then 'TARGET_MATCH'
            else 'CASE_CONTEXT_ONLY' end
from public.control_plane_action_outbox a
join public.control_plane_events e on (
  (a.case_id is not null and e.case_id=a.case_id)
  or e.id=a.source_event_id
  or e.payload->>'action_id'=a.id::text
  or e.payload->>'action_key'=a.action_key
  or lower(coalesce(e.payload->>'global_execution_gate','')) in ('true','1','yes')
  or (nullif(a.provider_receipt->>'message_id','') is not null and e.source_ref=a.provider_receipt->>'message_id')
)
where not (e.source_system='control_plane_action_outbox' and e.source_ref=a.id::text)
  and (
    e.id=a.source_event_id
    or e.payload->>'action_id'=a.id::text
    or e.payload->>'action_key'=a.action_key
    or lower(coalesce(e.payload->>'global_execution_gate','')) in ('true','1','yes')
    or (nullif(a.provider_receipt->>'message_id','') is not null and e.source_ref=a.provider_receipt->>'message_id')
    or public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',e.event_type,e.source_system,e.source_ref,e.actor_ref,e.payload::text,e.state_after::text))
    or (
      e.source_system not in ('control_plane_action_outbox','control_plane_obligations')
      and not exists (
        select 1 from public.control_plane_communications c2
        where c2.case_id is not distinct from e.case_id
          and c2.source_system=e.source_system
          and c2.source_ref=e.source_ref
      )
    )
  )
union all
select a.id,'OBLIGATION',o.id::text,o.obligation_key,o.updated_at,
       case when o.id=a.source_obligation_id
               or o.metadata->>'source_action_key'=a.action_key
               or o.metadata->>'action_key'=a.action_key
               or lower(coalesce(o.metadata->>'global_execution_gate','')) in ('true','1','yes')
               or public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',o.obligation_key,o.obligation_type,o.title,o.description,o.owner_ref,o.metadata::text))
            then 'HARD' else 'SOFT' end,
       case when o.id=a.source_obligation_id then 'ACTION_SOURCE_OBLIGATION'
            when o.metadata->>'source_action_key'=a.action_key or o.metadata->>'action_key'=a.action_key then 'EXPLICIT_ACTION_LINK'
            when lower(coalesce(o.metadata->>'global_execution_gate','')) in ('true','1','yes') then 'DECLARED_GLOBAL_EXECUTION_GATE'
            when public.control_plane_action_target_matches_v2(a.target_system,a.target_ref,concat_ws(' ',o.obligation_key,o.obligation_type,o.title,o.description,o.owner_ref,o.metadata::text)) then 'TARGET_MATCH'
            else 'CASE_CONTEXT_ONLY' end
from public.control_plane_action_outbox a
join public.control_plane_obligations o on (
  (a.case_id is not null and o.case_id=a.case_id)
  or o.id=a.source_obligation_id
  or o.metadata->>'source_action_key'=a.action_key
  or o.metadata->>'action_key'=a.action_key
  or lower(coalesce(o.metadata->>'global_execution_gate','')) in ('true','1','yes')
)
union all
select a.id,'CONNECTOR_INCIDENT',i.id::text,i.connector,greatest(i.updated_at,coalesce(i.resolved_at,i.updated_at)),
       'HARD',case when i.id::text=a.payload->>'incident_id' then 'EXPLICIT_INCIDENT_LINK' else 'CONNECTOR_IDENTITY_MATCH' end
from public.control_plane_action_outbox a
join public.apex_connector_incidents i
  on a.case_id is null and a.action_type='OPERATOR_ALERT'
 and (
   i.id::text=a.payload->>'incident_id'
   or (
     coalesce(nullif(a.payload->>'incident_id',''),'')=''
     and lower(i.connector)=lower(coalesce(nullif(a.payload->>'connector',''),a.target_ref,''))
   )
 );

comment on view public.control_plane_action_source_relevance_v2 is
'Action/source relevance graph. Explicit action/provider links and declared global gates cross case boundaries; ordinary context remains case-scoped. HARD rows survive projection dedup, and dedup requires matching source system plus source ref.';

create or replace function public.reconcile_control_plane_internal_awareness_v2()
returns jsonb
language plpgsql
security definer
set search_path='pg_catalog','public'
as $$
declare
  r record;
  v_valid boolean;
  v_receipt jsonb;
  v_evaluated integer:=0;
  v_cancelled integer:=0;
  v_resolved_at timestamptz;
  v_incident_updated_at timestamptz;
begin
  for r in
    select a.id action_id,a.action_key,a.status,a.payload,a.target_ref,i.id incident_id
    from public.control_plane_action_outbox a
    join public.control_plane_action_awareness_v2 aw on aw.action_id=a.id
    join public.apex_connector_incidents i on a.action_type='OPERATOR_ALERT' and a.case_id is null
      and (
        i.id::text=a.payload->>'incident_id'
        or (
          coalesce(nullif(a.payload->>'incident_id',''),'')=''
          and lower(i.connector)=lower(coalesce(nullif(a.payload->>'connector',''),a.target_ref,''))
        )
      )
    where a.status in ('READY','APPROVED','FAILED') and aw.dispatch_reevaluation_required
    order by i.updated_at desc
  loop
    select i.resolved_at,i.updated_at
      into v_resolved_at,v_incident_updated_at
    from public.apex_connector_incidents i
    where i.id=r.incident_id
    for update;
    if not found then continue; end if;

    v_valid:=v_resolved_at is null;
    v_receipt:=public.record_control_plane_action_awareness_v1(
      r.action_id,'control-plane-internal-awareness-v2',v_valid,
      jsonb_build_object(
        'decision_basis','STRUCTURAL_CONNECTOR_INCIDENT_STATE',
        'incident_id',r.incident_id,
        'incident_updated_at',v_incident_updated_at,
        'incident_resolved_at',v_resolved_at,
        'incident_state_locked_during_evaluation',true,
        'no_substantive_domain_judgment',true
      )
    );
    v_evaluated:=v_evaluated+1;
    if not v_valid then
      update public.control_plane_action_outbox
      set status='CANCELLED',last_error='awareness v2: source connector incident resolved before dispatch',lease_owner=null,lease_expires_at=null,updated_at=clock_timestamp()
      where id=r.action_id and status in ('READY','APPROVED','FAILED');
      if found then
        v_cancelled:=v_cancelled+1;
        insert into public.control_plane_events(case_id,event_key,event_type,source_system,source_ref,actor_ref,occurred_at,severity,state_before,state_after,payload)
        values(null,'awareness-v2:auto-cancel:'||r.action_id::text,'ACTION_CANCELLED_SOURCE_INVALIDATED','control-plane-awareness',r.incident_id::text,'control-plane-internal-awareness-v2',clock_timestamp(),'INFO',jsonb_build_object('status',r.status),jsonb_build_object('status','CANCELLED'),jsonb_build_object('action_key',r.action_key,'incident_resolved_at',v_resolved_at,'awareness_receipt',v_receipt,'incident_state_locked_during_evaluation',true,'no_substantive_domain_judgment',true))
        on conflict(event_key) do nothing;
      end if;
    end if;
  end loop;
  return jsonb_build_object('evaluated',v_evaluated,'cancelled_resolved_alerts',v_cancelled,'observed_at',clock_timestamp(),'policy','only structurally decidable internal connector alerts auto-evaluate with exact-incident preference and row lock');
end;
$$;

revoke all on function public.record_control_plane_action_awareness_v1(uuid,text,boolean,jsonb) from public,anon,authenticated;
revoke all on function public.claim_control_plane_actions_v1(text,integer,integer) from public,anon,authenticated;
revoke all on function public.get_control_plane_action_awareness_v2(text,uuid,integer) from public,anon,authenticated;
revoke all on function public.reconcile_control_plane_internal_awareness_v2() from public,anon,authenticated;
grant execute on function public.record_control_plane_action_awareness_v1(uuid,text,boolean,jsonb) to service_role;
grant execute on function public.claim_control_plane_actions_v1(text,integer,integer) to service_role;
grant execute on function public.get_control_plane_action_awareness_v2(text,uuid,integer) to service_role;
grant execute on function public.reconcile_control_plane_internal_awareness_v2() to service_role;
