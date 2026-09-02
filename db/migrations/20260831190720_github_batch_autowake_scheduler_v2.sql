create or replace function public.wake_github_batch_worker_v2()
returns trigger
language plpgsql
security definer
set search_path=public,vault,net,pg_temp
as $$
declare
  v_secret text;
begin
  if new.status <> 'queued' then return new; end if;

  begin
    select decrypted_secret into v_secret
    from vault.decrypted_secrets
    where name='github_worker_wake_secret_v1'
    order by created_at desc
    limit 1;

    if v_secret is not null then
      perform net.http_post(
        url := 'https://dyhprklicgewmrimecey.supabase.co/functions/v1/apex-github-batch-wake',
        headers := jsonb_build_object(
          'content-type','application/json',
          'x-apex-worker-secret',v_secret
        ),
        body := jsonb_build_object('limit',100,'max_cycles',4),
        timeout_milliseconds := 60000
      );
    end if;
  exception when others then
    null;
  end;

  v_secret := null;
  return new;
end;
$$;

drop trigger if exists github_batch_run_autowake_v2 on public.github_batch_runs_v2;
create trigger github_batch_run_autowake_v2
after insert on public.github_batch_runs_v2
for each row execute function public.wake_github_batch_worker_v2();

do $$
declare v_jobid bigint;
begin
  for v_jobid in select jobid from cron.job where jobname='github-batch-worker-v2' loop
    perform cron.unschedule(v_jobid);
  end loop;

  perform cron.schedule(
    'github-batch-worker-v2',
    '* * * * *',
    $cmd$
      select net.http_post(
        url := 'https://dyhprklicgewmrimecey.supabase.co/functions/v1/apex-github-batch-wake',
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
        body := '{"limit":100,"max_cycles":4}'::jsonb,
        timeout_milliseconds := 60000
      );
    $cmd$
  );
end;
$$;

comment on function public.wake_github_batch_worker_v2() is
  'Best-effort immediate wake after durable batch creation. Queue durability does not depend on wake delivery.';
