create or replace view public.github_batch_dlq_v2 as
select
  i.item_id,i.batch_id,b.batch_key,b.name,i.ordinal,i.operation,i.repository,i.execution_lane,
  i.status,i.attempts,i.max_attempts,i.response_status,i.error_code,i.quality_status,
  i.quality_detail,i.result_summary,i.completed_at
from public.github_batch_items_v2 i
join public.github_batch_runs_v2 b on b.batch_id=i.batch_id
where i.status in ('failed','blocked');

revoke all on public.github_batch_dlq_v2 from public,anon,authenticated;
grant select on public.github_batch_dlq_v2 to service_role;

create or replace view public.github_batch_metrics_v2 as
select
  b.batch_id,b.batch_key,b.name,b.workload_class,b.status,b.total_items,b.succeeded_items,
  b.failed_items,b.blocked_items,b.retry_items,b.max_concurrency,b.target_rps,
  b.created_at,b.started_at,b.completed_at,
  case when b.started_at is not null and b.completed_at is not null
    then extract(epoch from (b.completed_at-b.started_at)) else null end elapsed_seconds,
  case when b.started_at is not null and b.completed_at is not null
         and extract(epoch from (b.completed_at-b.started_at))>0
    then round(b.succeeded_items::numeric/extract(epoch from (b.completed_at-b.started_at)),3)
    else null end effective_items_per_second,
  round(avg(i.duration_ms) filter(where i.duration_ms is not null)::numeric,2) avg_item_ms,
  percentile_cont(0.50) within group(order by i.duration_ms) filter(where i.duration_ms is not null) p50_item_ms,
  percentile_cont(0.95) within group(order by i.duration_ms) filter(where i.duration_ms is not null) p95_item_ms,
  percentile_cont(0.99) within group(order by i.duration_ms) filter(where i.duration_ms is not null) p99_item_ms,
  b.quality_summary
from public.github_batch_runs_v2 b
left join public.github_batch_items_v2 i on i.batch_id=b.batch_id
group by b.batch_id;

revoke all on public.github_batch_metrics_v2 from public,anon,authenticated;
grant select on public.github_batch_metrics_v2 to service_role;

create or replace function public.finalize_github_batch_v2(p_batch_id uuid)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare
  v_batch public.github_batch_runs_v2%rowtype;
  v_total integer; v_succeeded integer; v_failed integer; v_blocked integer; v_retry integer;
  v_unfinished integer; v_qpass integer; v_qfail integer; v_ambiguous integer; v_write_qfail integer;
  v_ratio numeric; v_min_ratio numeric; v_require_write boolean; v_require_no_ambiguous boolean;
  v_quality_ok boolean; v_status text; v_summary jsonb;
begin
  perform pg_advisory_xact_lock(hashtext(p_batch_id::text||':github_batch_finalize'));

  select * into v_batch from public.github_batch_runs_v2 where batch_id=p_batch_id for update;
  if not found then raise exception 'batch_not_found'; end if;

  select count(*),
         count(*) filter(where status='succeeded'),
         count(*) filter(where status='failed'),
         count(*) filter(where status='blocked'),
         count(*) filter(where status='retry'),
         count(*) filter(where status in ('pending','running','retry')),
         count(*) filter(where quality_status='passed'),
         count(*) filter(where quality_status='failed'),
         count(*) filter(where error_code='ambiguous_external_outcome'),
         count(*) filter(where operation in ('branch.create','contents.put','issue.create','issue.comment','pull.comment') and quality_status='failed')
  into v_total,v_succeeded,v_failed,v_blocked,v_retry,v_unfinished,v_qpass,v_qfail,v_ambiguous,v_write_qfail
  from public.github_batch_items_v2 where batch_id=p_batch_id;

  v_ratio := case when v_total=0 then 0 else v_succeeded::numeric/v_total end;
  v_min_ratio := coalesce((v_batch.quality_policy->>'minimum_success_ratio')::numeric,0.98);
  v_require_write := coalesce((v_batch.quality_policy->>'require_write_readback')::boolean,true);
  v_require_no_ambiguous := coalesce((v_batch.quality_policy->>'require_no_ambiguous_outcomes')::boolean,true);
  v_quality_ok := v_ratio>=v_min_ratio
    and (not v_require_write or v_write_qfail=0)
    and (not v_require_no_ambiguous or v_ambiguous=0);

  if v_unfinished>0 then v_status:='running';
  elsif v_quality_ok and v_failed=0 and v_blocked=0 then v_status:='completed';
  elsif not v_quality_ok then v_status:='quality_failed';
  else v_status:='completed_with_errors';
  end if;

  v_summary:=jsonb_build_object(
    'total_items',v_total,'succeeded_items',v_succeeded,'failed_items',v_failed,'blocked_items',v_blocked,
    'retry_items',v_retry,'success_ratio',round(v_ratio,6),'minimum_success_ratio',v_min_ratio,
    'quality_passed_items',v_qpass,'quality_failed_items',v_qfail,
    'ambiguous_outcomes',v_ambiguous,'write_quality_failures',v_write_qfail,'quality_ok',v_quality_ok
  );

  update public.github_batch_runs_v2
  set status=v_status,total_items=v_total,succeeded_items=v_succeeded,failed_items=v_failed,blocked_items=v_blocked,
      retry_items=v_retry,quality_passed_items=v_qpass,quality_failed_items=v_qfail,quality_summary=v_summary,
      completed_at=case when v_unfinished=0 then coalesce(completed_at,now()) else null end,updated_at=now()
  where batch_id=p_batch_id;

  if v_unfinished=0 then
    insert into public.github_batch_receipts_v2(batch_id,receipt_type,outcome,detail)
    select p_batch_id,'quality_finalized',case when v_quality_ok then 'passed' else 'failed' end,v_summary
    where not exists(
      select 1 from public.github_batch_receipts_v2
      where batch_id=p_batch_id and item_id is null and receipt_type='quality_finalized'
    );

    insert into public.github_batch_receipts_v2(batch_id,receipt_type,outcome,detail)
    select p_batch_id,'batch_completed',v_status,v_summary
    where not exists(
      select 1 from public.github_batch_receipts_v2
      where batch_id=p_batch_id and item_id is null and receipt_type='batch_completed'
    );
  end if;

  return jsonb_build_object('batch_id',p_batch_id,'status',v_status,'quality',v_summary);
end;
$$;

create or replace function public.cancel_github_batch_v2(p_batch_id uuid,p_reason text default 'operator_cancelled')
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare v_count integer;
begin
  perform pg_advisory_xact_lock(hashtext(p_batch_id::text||':github_batch_cancel'));

  update public.github_batch_items_v2
  set status='cancelled',lease_owner=null,lease_expires_at=null,completed_at=now(),updated_at=now(),
      error_code='batch_cancelled',quality_status='not_applicable',
      quality_detail=quality_detail||jsonb_build_object('cancel_reason',p_reason)
  where batch_id=p_batch_id and status in ('pending','retry');
  get diagnostics v_count=row_count;

  update public.github_batch_runs_v2
  set status='cancelled',completed_at=now(),updated_at=now(),
      metadata=metadata||jsonb_build_object('cancel_reason',p_reason,'cancelled_at',now())
  where batch_id=p_batch_id and status not in ('completed','completed_with_errors','quality_failed','cancelled');

  insert into public.github_batch_receipts_v2(batch_id,receipt_type,outcome,detail)
  select p_batch_id,'batch_cancelled','cancelled',jsonb_build_object('reason',p_reason,'items_cancelled',v_count)
  where exists(select 1 from public.github_batch_runs_v2 where batch_id=p_batch_id)
    and not exists(select 1 from public.github_batch_receipts_v2 where batch_id=p_batch_id and item_id is null and receipt_type='batch_cancelled');

  return jsonb_build_object('batch_id',p_batch_id,'status','cancelled','items_cancelled',v_count);
end;
$$;

create or replace function public.replay_github_batch_failures_v2(
  p_source_batch_id uuid,p_new_batch_key text,p_name text default null
)
returns jsonb
language plpgsql
security definer
set search_path='public','pg_temp'
as $$
declare v_source public.github_batch_runs_v2%rowtype; v_items jsonb;
begin
  select * into v_source from public.github_batch_runs_v2 where batch_id=p_source_batch_id;
  if not found then raise exception 'source_batch_not_found'; end if;

  select jsonb_agg(
    jsonb_strip_nulls(jsonb_build_object(
      'operation',operation,'repository',repository,'args',arguments,'full_fidelity',full_fidelity,
      'expected_before_sha',expected_before_sha,'execution_lane',execution_lane,
      'max_attempts',max_attempts,'priority',priority
    )) order by ordinal
  )
  into v_items
  from public.github_batch_items_v2
  where batch_id=p_source_batch_id and status in ('failed','blocked');

  if v_items is null or jsonb_array_length(v_items)=0 then
    return jsonb_build_object('created',false,'reason','no_failed_or_blocked_items');
  end if;

  return public.create_github_batch_v2(
    p_new_batch_key,coalesce(p_name,v_source.name||' replay'),v_source.workload_class,v_items,
    v_source.priority,v_source.max_concurrency,v_source.target_rps,v_source.claim_size,
    v_source.quality_policy,
    v_source.metadata||jsonb_build_object('replay_of_batch_id',p_source_batch_id,'replay_created_at',now())
  );
end;
$$;

revoke all on function public.cancel_github_batch_v2(uuid,text) from public,anon,authenticated;
revoke all on function public.replay_github_batch_failures_v2(uuid,text,text) from public,anon,authenticated;
grant execute on function public.cancel_github_batch_v2(uuid,text) to service_role;
grant execute on function public.replay_github_batch_failures_v2(uuid,text,text) to service_role;

comment on view public.github_batch_dlq_v2 is 'Terminal GitHub batch failures/blocks for inspection and replay.';
comment on view public.github_batch_metrics_v2 is 'Batch throughput and latency percentile projection.';
