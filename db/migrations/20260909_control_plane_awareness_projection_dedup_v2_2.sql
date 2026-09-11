-- Projection-dedup hardening for relevance-aware awareness V2.
-- A mirrored communication/action/obligation event must not independently create
-- relevance when its source-native record is already represented in the graph.

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
join public.control_plane_communications c on a.case_id is not null and c.case_id=a.case_id

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
join public.control_plane_events e on a.case_id is not null and e.case_id=a.case_id
where (
  e.id=a.source_event_id
  or (
    e.source_system not in ('control_plane_action_outbox','control_plane_obligations')
    and not exists (
      select 1 from public.control_plane_communications c2
      where c2.case_id=e.case_id and c2.source_ref=e.source_ref
    )
  )
)
and not (e.source_system='control_plane_action_outbox' and e.source_ref=a.id::text)

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
join public.control_plane_obligations o on a.case_id is not null and o.case_id=a.case_id

union all

select a.id,'CONNECTOR_INCIDENT',i.id::text,i.connector,greatest(i.updated_at,coalesce(i.resolved_at,i.updated_at)),
       'HARD',case when i.id::text=a.payload->>'incident_id' then 'EXPLICIT_INCIDENT_LINK' else 'CONNECTOR_IDENTITY_MATCH' end
from public.control_plane_action_outbox a
join public.apex_connector_incidents i
  on a.case_id is null and a.action_type='OPERATOR_ALERT'
 and (i.id::text=a.payload->>'incident_id' or lower(i.connector)=lower(coalesce(nullif(a.payload->>'connector',''),a.target_ref,'')));

comment on view public.control_plane_action_source_relevance_v2 is
'Action/source relevance graph. Derived communication/action/obligation event projections are deduplicated against their source tables so projection text cannot manufacture new relevance.';
