do $$
declare
  v_jobid bigint;
begin
  for v_jobid in select jobid from cron.job where jobname='github-webhook-worker-v1' loop
    perform cron.unschedule(v_jobid);
  end loop;

  perform cron.schedule(
    'github-webhook-worker-v1',
    '* * * * *',
    $cmd$
      select net.http_post(
        url := 'https://dyhprklicgewmrimecey.supabase.co/functions/v1/apex-github-webhook-wake',
        headers := jsonb_build_object(
          'content-type','application/json',
          'x-apex-worker-secret',(
            select decrypted_secret
            from vault.decrypted_secrets
            where name='github_worker_wake_secret_v1'
            order by created_at desc
            limit 1
          )
        ),
        body := '{"limit":25}'::jsonb,
        timeout_milliseconds := 60000
      );
    $cmd$
  );
end;
$$;

create or replace function public.enqueue_github_webhook_delivery_v1()
returns trigger
language plpgsql
security definer
set search_path = public, vault, net, pg_temp
as $$
declare
  v_secret text;
begin
  if not new.signature_verified then
    return new;
  end if;

  insert into public.github_webhook_event_queue_v1 (
    delivery_id,event_type,action,repository,status,metadata
  ) values (
    new.delivery_id,new.event_type,new.action,new.repository,'pending',
    jsonb_build_object(
      'delivery_payload_sha256',new.payload_sha256,
      'sender_login',new.sender_login,
      'delivery_metadata',new.metadata
    )
  ) on conflict (delivery_id) do nothing;

  begin
    select decrypted_secret into v_secret
    from vault.decrypted_secrets
    where name='github_worker_wake_secret_v1'
    order by created_at desc
    limit 1;

    if v_secret is not null then
      perform net.http_post(
        url := 'https://dyhprklicgewmrimecey.supabase.co/functions/v1/apex-github-webhook-wake',
        headers := jsonb_build_object(
          'content-type','application/json',
          'x-apex-worker-secret',v_secret
        ),
        body := '{"limit":10}'::jsonb,
        timeout_milliseconds := 60000
      );
    end if;
  exception when others then
    -- Queue durability outranks wake delivery. Cron provides recovery.
    null;
  end;

  v_secret := null;
  return new;
end;
$$;

revoke all on function public.enqueue_github_webhook_delivery_v1() from public, anon, authenticated;
grant execute on function public.enqueue_github_webhook_delivery_v1() to service_role;

comment on function public.enqueue_github_webhook_delivery_v1() is
  'Queues HMAC-verified GitHub deliveries and best-effort wakes the worker immediately; cron retries pending work every minute.';
