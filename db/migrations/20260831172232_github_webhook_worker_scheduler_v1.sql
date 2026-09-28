create extension if not exists pg_cron;

do $$
begin
  if not exists (
    select 1 from vault.secrets where name = 'github_worker_wake_secret_v1'
  ) then
    perform vault.create_secret(
      replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
      'github_worker_wake_secret_v1',
      'Internal wake credential for the GitHub webhook worker; generated and retained only in Supabase Vault.'
    );
  end if;
end;
$$;

create or replace function public.validate_github_worker_wake_secret_v1(p_secret text)
returns boolean
language sql
security definer
set search_path = public, extensions, vault, pg_temp
as $$
  select coalesce(
    exists (
      select 1
      from vault.decrypted_secrets s
      where s.name = 'github_worker_wake_secret_v1'
        and extensions.digest(coalesce(p_secret,''), 'sha256') = extensions.digest(s.decrypted_secret, 'sha256')
    ),
    false
  );
$$;

revoke all on function public.validate_github_worker_wake_secret_v1(text) from public, anon, authenticated;
grant execute on function public.validate_github_worker_wake_secret_v1(text) to service_role;

create or replace function public.resolve_github_worker_wake_secret_v1()
returns text
language sql
security definer
set search_path = public, vault, pg_temp
as $$
  select s.decrypted_secret
  from vault.decrypted_secrets s
  where s.name = 'github_worker_wake_secret_v1'
  order by s.created_at desc
  limit 1;
$$;

revoke all on function public.resolve_github_worker_wake_secret_v1() from public, anon, authenticated;
grant execute on function public.resolve_github_worker_wake_secret_v1() to service_role;

do $$
begin
  if not exists (
    select 1 from cron.job where jobname = 'github-webhook-worker-v1'
  ) then
    perform cron.schedule(
      'github-webhook-worker-v1',
      '* * * * *',
      $cmd$
        select net.http_post(
          url := 'https://dyhprklicgewmrimecey.supabase.co/functions/v1/apex-github-webhook-worker',
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
          timeout_milliseconds := 55000
        );
      $cmd$
    );
  end if;
end;
$$;

comment on function public.validate_github_worker_wake_secret_v1(text) is
  'Constant-content hash comparison against the Vault-held GitHub worker wake secret; callable only by service_role.';
comment on function public.resolve_github_worker_wake_secret_v1() is
  'Internal service-role-only resolver used by verified webhook ingress to wake the queue worker without embedding credentials in source.';
