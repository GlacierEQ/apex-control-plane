create or replace function public.finish_github_webhook_event_v1(
  p_event_id uuid,
  p_status text,
  p_last_error text default null,
  p_metadata jsonb default '{}'::jsonb,
  p_retry_after_seconds integer default null
)
returns boolean
language plpgsql
security definer
set search_path to 'public','pg_temp'
as $$
declare
  v_delivery_id text;
  v_found boolean := false;
  v_parent_status text;
begin
  if p_status not in ('completed','failed','ignored','pending') then
    raise exception 'invalid event status';
  end if;

  update public.github_webhook_event_queue_v1
  set status = p_status,
      last_error = p_last_error,
      available_at = case
        when p_status = 'pending' and p_retry_after_seconds is not null
          then now() + make_interval(secs => greatest(1, least(p_retry_after_seconds, 3600)))
        else available_at
      end,
      locked_at = null,
      processed_at = case when p_status in ('completed','failed','ignored') then now() else null end,
      metadata = metadata || coalesce(p_metadata,'{}'::jsonb),
      updated_at = now()
  where event_id = p_event_id
  returning delivery_id into v_delivery_id;

  v_found := found;

  if v_found and v_delivery_id is not null and p_status in ('completed','failed','ignored') then
    v_parent_status := case p_status
      when 'completed' then 'processed'
      when 'ignored' then 'ignored'
      else 'failed'
    end;

    update public.github_webhook_deliveries_v1
    set processing_status = v_parent_status,
        processed_at = now(),
        metadata = metadata || jsonb_build_object(
          'queue_terminal_status', p_status,
          'queue_terminal_event_id', p_event_id,
          'queue_terminal_at', now()
        )
    where delivery_id = v_delivery_id;
  end if;

  return v_found;
end;
$$;

update public.github_webhook_deliveries_v1 d
set processing_status = case q.status when 'completed' then 'processed' when 'ignored' then 'ignored' else 'failed' end,
    processed_at = q.processed_at,
    metadata = d.metadata || jsonb_build_object(
      'queue_terminal_status', q.status,
      'queue_terminal_event_id', q.event_id,
      'queue_terminal_at', q.processed_at,
      'rollup_backfilled', true
    )
from public.github_webhook_event_queue_v1 q
where q.delivery_id = d.delivery_id
  and q.status in ('completed','failed','ignored')
  and d.processing_status in ('received','accepted');
