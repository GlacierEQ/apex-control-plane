-- Harden relevance-aware awareness against substring false positives and
-- connector-resolution races while preserving causal source identities.

create or replace function public.control_plane_action_target_matches_v2(
  p_target_system text,
  p_target_ref text,
  p_text text
)
returns boolean
language sql
immutable
parallel safe
set search_path='pg_catalog','public'
as $$
  with n as (
    select public.control_plane_normalize_awareness_text_v2(p_target_system) as target_system,
           public.control_plane_normalize_awareness_text_v2(p_target_ref) as target_ref,
           public.control_plane_normalize_awareness_text_v2(p_text) as haystack
  )
  select (length(target_system)>=3 and strpos(' '||haystack||' ',' '||target_system||' ')>0)
      or (length(target_ref)>=4 and strpos(' '||haystack||' ',' '||target_ref||' ')>0)
  from n;
$$;

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
       'explicit-link-target-global-gate-v2'::text relevance_model,
       coalesce(hard.newer_hard_sources,'[]'::jsonb) newer_hard_sources,
       coalesce(soft.newer_soft_sources,'[]'::jsonb) newer_soft_sources
from public.control_plane_action_outbox a
left join lateral (
  select r.created_at,r.source_watermark_at,r.execution_valid,r.evaluation
  from public.control_plane_action_awareness_receipts r
  where r.action_id=a.id order by r.created_at desc limit 1
) ar on true
left join lateral (
  select max(s.source_at) latest_source_state_at,
         count(*) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))) newer_source_observations,
         coalesce(jsonb_agg(jsonb_build_object(
           'source_kind',s.source_kind,'source_id',s.source_id,'source_ref',s.source_ref,
           'source_at',s.source_at,'relevance_reason',s.relevance_reason
         ) order by s.source_at desc) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))),'[]'::jsonb) newer_hard_sources
  from public.control_plane_action_source_relevance_v2 s
  where s.action_id=a.id and s.relevance_class='HARD'
) hard on true
left join lateral (
  select max(s.source_at) latest_soft_context_at,
         count(*) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))) newer_soft_context_observations,
         coalesce(jsonb_agg(jsonb_build_object(
           'source_kind',s.source_kind,'source_id',s.source_id,'source_ref',s.source_ref,
           'source_at',s.source_at,'relevance_reason',s.relevance_reason
         ) order by s.source_at desc) filter(where s.source_at>greatest(a.updated_at,coalesce(ar.source_watermark_at,a.updated_at))),'[]'::jsonb) newer_soft_sources
  from public.control_plane_action_source_relevance_v2 s
  where s.action_id=a.id and s.relevance_class='SOFT'
) soft on true
left join lateral (
  select coalesce(jsonb_agg(to_jsonb(x.*) order by x.occurred_at desc),'[]'::jsonb) recent_communications
  from (
    select c.direction,c.channel,c.counterparty,c.subject,c.occurred_at,c.source_system,c.source_ref,c.acknowledgement_state,c.delivery_state,c.summary
    from public.control_plane_communications c
    where a.case_id is not null and c.case_id=a.case_id
    order by c.occurred_at desc limit 12
  ) x
) comm on true;

comment on view public.control_plane_action_awareness_v2 is
'Relevance-aware execution fence. Only HARD source changes block dispatch. Newer HARD/SOFT source identities are preserved for causal readback; unlinked same-case changes remain visible as SOFT context.';

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
      and (i.id::text=a.payload->>'incident_id' or lower(i.connector)=lower(coalesce(nullif(a.payload->>'connector',''),a.target_ref,'')))
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
  return jsonb_build_object('evaluated',v_evaluated,'cancelled_resolved_alerts',v_cancelled,'observed_at',clock_timestamp(),'policy','only structurally decidable internal connector alerts auto-evaluate with incident row lock');
end;
$$;
