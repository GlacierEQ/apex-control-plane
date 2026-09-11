-- Relevance-aware dynamic awareness v2.
-- Preserve all source context, but only explicit action links, target matches,
-- provider identity, connector incident identity, or declared global execution
-- gates may block dispatch.

create or replace function public.control_plane_normalize_awareness_text_v2(p_text text)
returns text language sql immutable parallel safe as $$
  select btrim(regexp_replace(lower(coalesce(p_text,'')), '[^a-z0-9]+', ' ', 'g'));
$$;

create or replace function public.control_plane_action_target_matches_v2(
  p_target_system text,p_target_ref text,p_text text
)
returns boolean language sql immutable parallel safe as $$
  with n as (
    select public.control_plane_normalize_awareness_text_v2(p_target_system) target_system,
           public.control_plane_normalize_awareness_text_v2(p_target_ref) target_ref,
           public.control_plane_normalize_awareness_text_v2(p_text) haystack
  )
  select (length(target_system)>=3 and strpos(haystack,target_system)>0)
      or (length(target_ref)>=4 and strpos(haystack,target_ref)>0)
  from n;
$$;

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
where not (e.source_system='control_plane_action_outbox' and e.source_ref=a.id::text)
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
'Action/source relevance graph. HARD sources may stale dispatch; SOFT sources remain visible context. HARD requires explicit action/provider/incident linkage, target identity, or an explicitly declared global execution gate.';

create or replace function public.control_plane_latest_source_watermark_v2(p_action_id uuid)
returns timestamptz language sql stable security definer set search_path='pg_catalog','public' as $$
  select greatest(a.created_at,coalesce((select max(s.source_at) from public.control_plane_action_source_relevance_v2 s where s.action_id=a.id and s.relevance_class='HARD'),a.created_at))
  from public.control_plane_action_outbox a where a.id=p_action_id;
$$;
revoke all on function public.control_plane_latest_source_watermark_v2(uuid) from public,anon,authenticated;
grant execute on function public.control_plane_latest_source_watermark_v2(uuid) to service_role;

create or replace view public.control_plane_action_awareness_v2
with (security_invoker=true) as
select a.id action_id,a.case_id,a.action_key,a.action_type,a.target_system,a.target_ref,a.status,a.priority,
       a.requires_operator_approval,a.authorization_basis,a.attempt_count,a.max_attempts,a.last_attempt_at,
       a.provider_receipt,a.acknowledged_at,a.completed_at,a.created_at,a.updated_at action_state_at,
       hard.latest_source_state_at,coalesce(hard.newer_source_observations,0::bigint) newer_source_observations,
       soft.latest_soft_context_at,coalesce(soft.newer_soft_context_observations,0::bigint) newer_soft_context_observations,
       hard.latest_source_state_at is not null and hard.latest_source_state_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) newer_source_state_exists,
       a.status in ('READY','APPROVED','FAILED','DISPATCHING') and hard.latest_source_state_at is not null and hard.latest_source_state_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) dispatch_reevaluation_required,
       soft.latest_soft_context_at is not null and soft.latest_soft_context_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) newer_soft_context_exists,
       case when a.status in ('READY','APPROVED','FAILED','DISPATCHING') and hard.latest_source_state_at is not null and hard.latest_source_state_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) then 'REEVALUATE_CURRENT_REALITY'
            when ar.execution_valid is false then 'CURRENT_BUT_ACTION_NOT_VALID'
            when soft.latest_soft_context_at is not null and soft.latest_soft_context_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) then 'CURRENT_WITH_NEW_SOFT_CONTEXT'
            else 'CURRENT_WITH_OBSERVED_STATE' end awareness_state,
       coalesce(comm.recent_communications,'[]'::jsonb) recent_communications,
       ar.created_at awareness_evaluated_at,ar.source_watermark_at evaluated_source_watermark_at,
       ar.execution_valid,ar.evaluation latest_evaluation,
       greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at)) awareness_watermark_at,
       'explicit-link-target-global-gate-v2'::text relevance_model
from public.control_plane_action_outbox a
left join lateral (select r.created_at,r.source_watermark_at,r.execution_valid,r.evaluation from public.control_plane_action_awareness_receipts r where r.action_id=a.id order by r.created_at desc limit 1) ar on true
left join lateral (select max(s.source_at) latest_source_state_at,count(*) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))) newer_source_observations from public.control_plane_action_source_relevance_v2 s where s.action_id=a.id and s.relevance_class='HARD') hard on true
left join lateral (select max(s.source_at) latest_soft_context_at,count(*) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))) newer_soft_context_observations from public.control_plane_action_source_relevance_v2 s where s.action_id=a.id and s.relevance_class='SOFT') soft on true
left join lateral (select coalesce(jsonb_agg(to_jsonb(x.*) order by x.occurred_at desc),'[]'::jsonb) recent_communications from (select c.direction,c.channel,c.counterparty,c.subject,c.occurred_at,c.source_system,c.source_ref,c.acknowledgement_state,c.delivery_state,c.summary from public.control_plane_communications c where a.case_id is not null and c.case_id=a.case_id order by c.occurred_at desc limit 12) x) comm on true;

comment on view public.control_plane_action_awareness_v2 is
'Relevance-aware execution fence. Only HARD source changes block dispatch. Unlinked same-case changes remain visible as SOFT context instead of silently invalidating parallel work.';

create or replace function public.get_control_plane_action_awareness_v2(p_case_id text default null,p_action_id uuid default null,p_limit integer default 50)
returns jsonb language sql stable security definer set search_path='pg_catalog','public' as $$
  select jsonb_build_object('observed_at',clock_timestamp(),'case_id',p_case_id,'action_id',p_action_id,
    'principle','current relevant source-bearing state outranks cached action intent; unrelated context remains visible without blocking',
    'relevance_model','explicit-link-target-global-gate-v2',
    'actions',coalesce(jsonb_agg(to_jsonb(q) order by q.priority,q.action_state_at desc),'[]'::jsonb),
    'actions_requiring_reevaluation',count(*) filter(where q.dispatch_reevaluation_required),
    'actions_with_new_soft_context',count(*) filter(where q.newer_soft_context_exists))
  from (select * from public.control_plane_action_awareness_v2 v where (p_case_id is null or v.case_id=p_case_id) and (p_action_id is null or v.action_id=p_action_id)
        order by case v.priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end,v.action_state_at desc limit greatest(1,least(coalesce(p_limit,50),200))) q;
$$;
revoke all on function public.get_control_plane_action_awareness_v2(text,uuid,integer) from public,anon,authenticated;
grant execute on function public.get_control_plane_action_awareness_v2(text,uuid,integer) to service_role;

-- Preserve the v1 publication interface, but bind its watermark to V2 HARD relevance.
create or replace function public.record_control_plane_action_awareness_v1(p_action_id uuid,p_evaluator text,p_execution_valid boolean,p_evaluation jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare v_action public.control_plane_action_outbox%rowtype; v_watermark timestamptz; v_id uuid;
begin
  if nullif(btrim(coalesce(p_evaluator,'')),'') is null then raise exception 'evaluator identity required'; end if;
  select * into v_action from public.control_plane_action_outbox where id=p_action_id;
  if not found then raise exception 'unknown action id'; end if;
  v_watermark:=public.control_plane_latest_source_watermark_v2(p_action_id);
  insert into public.control_plane_action_awareness_receipts(action_id,case_id,evaluator,source_watermark_at,execution_valid,evaluation)
  values(p_action_id,v_action.case_id,btrim(p_evaluator),v_watermark,p_execution_valid,coalesce(p_evaluation,'{}'::jsonb)||jsonb_build_object('relevance_model','explicit-link-target-global-gate-v2')) returning id into v_id;
  insert into public.control_plane_receipts(case_id,receipt_key,receipt_type,action_id,provider,provider_ref,status,payload,observed_at)
  values(v_action.case_id,'action-awareness:'||v_id::text,'DYNAMIC_AWARENESS_EVALUATION',p_action_id,'control-plane-awareness',v_id::text,
         case when p_execution_valid then 'CURRENT_AND_VALID' else 'CURRENT_NOT_VALID' end,
         jsonb_build_object('evaluator',btrim(p_evaluator),'source_watermark_at',v_watermark,'execution_valid',p_execution_valid,'relevance_model','explicit-link-target-global-gate-v2','evaluation',coalesce(p_evaluation,'{}'::jsonb)),clock_timestamp());
  return jsonb_build_object('awareness_receipt_id',v_id,'action_id',p_action_id,'source_watermark_at',v_watermark,'execution_valid',p_execution_valid,'relevance_model','explicit-link-target-global-gate-v2','evaluated_at',clock_timestamp());
end; $$;

create or replace function public.claim_control_plane_actions_v1(p_worker text,p_limit integer default 10,p_lease_seconds integer default 300)
returns setof public.control_plane_action_outbox language plpgsql security definer set search_path='pg_catalog','public' as $$
declare v_now timestamptz:=clock_timestamp();
begin
  if p_worker is null or length(trim(p_worker))<3 then raise exception 'worker identity required'; end if;
  if p_limit<1 or p_limit>100 then raise exception 'limit must be between 1 and 100'; end if;
  if p_lease_seconds<30 or p_lease_seconds>3600 then raise exception 'lease seconds must be between 30 and 3600'; end if;
  return query with candidates as (
    select a.id from public.control_plane_action_outbox a join public.control_plane_action_awareness_v2 aw on aw.action_id=a.id
    where (a.status in ('APPROVED','FAILED') or (a.status='READY' and not a.requires_operator_approval))
      and a.attempt_count<a.max_attempts and coalesce(a.next_attempt_at,a.not_before,a.created_at)<=v_now
      and (a.lease_expires_at is null or a.lease_expires_at<=v_now)
      and (not a.requires_operator_approval or a.authorization_basis is not null)
      and aw.dispatch_reevaluation_required is false and coalesce(aw.execution_valid,true) is true
    order by case a.priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end,coalesce(a.next_attempt_at,a.not_before,a.created_at),a.created_at
    for update of a skip locked limit p_limit
  ), claimed as (
    update public.control_plane_action_outbox a set status='DISPATCHING',attempt_count=a.attempt_count+1,last_attempt_at=v_now,lease_owner=trim(p_worker),
      lease_expires_at=v_now+make_interval(secs=>p_lease_seconds),dispatch_generation=a.dispatch_generation+1,last_error=null,updated_at=v_now
    from candidates c where a.id=c.id returning a.*
  ) select * from claimed;
end; $$;

create or replace function public.control_plane_begin_authorized_attempt(p_action_key text,p_provider_plan_ref text default null,p_transport text default null)
returns jsonb language plpgsql set search_path='public' as $$
declare v_action public.control_plane_action_outbox%rowtype; v_aw public.control_plane_action_awareness_v2%rowtype; v_attempt integer; v_event_id uuid;
begin
  select * into v_action from public.control_plane_action_outbox where action_key=p_action_key for update;
  if not found then raise exception 'Unknown action_key: %',p_action_key; end if;
  if v_action.status in ('SENT','ACKNOWLEDGED','COMPLETED') then return jsonb_build_object('action_key',v_action.action_key,'status',v_action.status,'idempotent',true,'attempt_count',v_action.attempt_count); end if;
  select * into v_aw from public.control_plane_action_awareness_v2 where action_id=v_action.id;
  if v_aw.dispatch_reevaluation_required then return jsonb_build_object('action_id',v_action.id,'action_key',v_action.action_key,'status',v_action.status,'dispatch_started',false,'awareness_state','REEVALUATE_CURRENT_REALITY','latest_source_state_at',v_aw.latest_source_state_at,'awareness_watermark_at',v_aw.awareness_watermark_at,'relevance_model',v_aw.relevance_model); end if;
  if v_aw.execution_valid is false then return jsonb_build_object('action_id',v_action.id,'action_key',v_action.action_key,'status',v_action.status,'dispatch_started',false,'awareness_state','CURRENT_BUT_ACTION_NOT_VALID','latest_evaluation',v_aw.latest_evaluation,'relevance_model',v_aw.relevance_model); end if;
  if v_action.status not in ('READY','APPROVED','FAILED') then raise exception 'Action % is not attemptable from status %',p_action_key,v_action.status; end if;
  if v_action.requires_operator_approval and nullif(btrim(coalesce(v_action.authorization_basis,'')),'') is null then raise exception 'Action % requires operator approval and has no authorization basis',p_action_key; end if;
  v_attempt:=v_action.attempt_count+1;
  update public.control_plane_action_outbox set status='DISPATCHING',attempt_count=v_attempt,last_attempt_at=now(),last_error=null,
    payload=coalesce(payload,'{}'::jsonb)||jsonb_strip_nulls(jsonb_build_object('active_provider_plan_ref',p_provider_plan_ref,'active_transport',p_transport,'attempt_started_at',now())),updated_at=now() where id=v_action.id;
  insert into public.control_plane_events(case_id,event_key,event_type,source_system,source_ref,actor_ref,occurred_at,severity,state_before,state_after,payload)
  values(v_action.case_id,'action:'||v_action.id::text||':attempt:'||v_attempt::text,'ACTION_ATTEMPT_STARTED',coalesce(p_transport,'control_plane'),p_provider_plan_ref,'operator_authorized_execution',now(),case when v_action.priority='P0' then 'HIGH' else 'INFO' end,
    jsonb_build_object('status',v_action.status,'attempt_count',v_action.attempt_count),jsonb_build_object('status','DISPATCHING','attempt_count',v_attempt),jsonb_strip_nulls(jsonb_build_object('action_key',v_action.action_key,'provider_plan_ref',p_provider_plan_ref,'transport',p_transport,'awareness_relevance_model',v_aw.relevance_model)))
  on conflict(event_key) do update set observed_at=now() returning id into v_event_id;
  update public.apex_case_execution_state set execution_state='TRANSMITTING',state_version=state_version+1,last_event_id=v_event_id::text,last_event_at=now(),next_action_id=v_action.id::text,
    metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('active_action_key',v_action.action_key,'active_attempt',v_attempt,'awareness_relevance_model',v_aw.relevance_model),updated_at=now() where case_id=v_action.case_id;
  return jsonb_build_object('action_id',v_action.id,'action_key',v_action.action_key,'case_id',v_action.case_id,'status','DISPATCHING','dispatch_started',true,'attempt_count',v_attempt,'event_id',v_event_id,'provider_plan_ref',p_provider_plan_ref,'awareness_state',v_aw.awareness_state,'relevance_model',v_aw.relevance_model,'newer_soft_context_exists',v_aw.newer_soft_context_exists);
end; $$;

create or replace function public.reconcile_control_plane_internal_awareness_v2()
returns jsonb language plpgsql security definer set search_path='pg_catalog','public' as $$
declare r record; v_valid boolean; v_receipt jsonb; v_evaluated integer:=0; v_cancelled integer:=0;
begin
  for r in select a.id action_id,a.action_key,a.status,a.payload,a.target_ref,i.id incident_id,i.connector,i.resolved_at,i.updated_at
    from public.control_plane_action_outbox a join public.control_plane_action_awareness_v2 aw on aw.action_id=a.id
    join public.apex_connector_incidents i on a.action_type='OPERATOR_ALERT' and a.case_id is null
      and (i.id::text=a.payload->>'incident_id' or lower(i.connector)=lower(coalesce(nullif(a.payload->>'connector',''),a.target_ref,'')))
    where a.status in ('READY','APPROVED','FAILED') and aw.dispatch_reevaluation_required order by i.updated_at desc
  loop
    v_valid:=r.resolved_at is null;
    v_receipt:=public.record_control_plane_action_awareness_v1(r.action_id,'control-plane-internal-awareness-v2',v_valid,
      jsonb_build_object('decision_basis','STRUCTURAL_CONNECTOR_INCIDENT_STATE','incident_id',r.incident_id,'connector',r.connector,'incident_updated_at',r.updated_at,'incident_resolved_at',r.resolved_at,'no_substantive_domain_judgment',true));
    v_evaluated:=v_evaluated+1;
    if not v_valid then
      update public.control_plane_action_outbox set status='CANCELLED',last_error='awareness v2: source connector incident resolved before dispatch',lease_owner=null,lease_expires_at=null,updated_at=clock_timestamp()
      where id=r.action_id and status in ('READY','APPROVED','FAILED');
      if found then
        v_cancelled:=v_cancelled+1;
        insert into public.control_plane_events(case_id,event_key,event_type,source_system,source_ref,actor_ref,occurred_at,severity,state_before,state_after,payload)
        values(null,'awareness-v2:auto-cancel:'||r.action_id::text,'ACTION_CANCELLED_SOURCE_INVALIDATED','control-plane-awareness',r.incident_id::text,'control-plane-internal-awareness-v2',clock_timestamp(),'INFO',jsonb_build_object('status',r.status),jsonb_build_object('status','CANCELLED'),jsonb_build_object('action_key',r.action_key,'connector',r.connector,'incident_resolved_at',r.resolved_at,'awareness_receipt',v_receipt,'no_substantive_domain_judgment',true))
        on conflict(event_key) do nothing;
      end if;
    end if;
  end loop;
  return jsonb_build_object('evaluated',v_evaluated,'cancelled_resolved_alerts',v_cancelled,'observed_at',clock_timestamp(),'policy','only structurally decidable internal connector alerts auto-evaluate');
end; $$;
revoke all on function public.reconcile_control_plane_internal_awareness_v2() from public,anon,authenticated;
grant execute on function public.reconcile_control_plane_internal_awareness_v2() to service_role;

do $$ declare v_jobid bigint; begin
  select jobid into v_jobid from cron.job where jobname='control-plane-awareness-reconcile-v2' limit 1;
  if v_jobid is not null then perform cron.unschedule(v_jobid); end if;
  perform cron.schedule('control-plane-awareness-reconcile-v2','* * * * *','select public.reconcile_control_plane_internal_awareness_v2();');
end $$;