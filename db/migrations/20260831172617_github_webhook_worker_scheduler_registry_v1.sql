update public.connector_registry_v2
set metadata = metadata || jsonb_build_object(
      'webhook_wake','apex-github-webhook-wake',
      'webhook_wake_auth','vault_generated_secret',
      'webhook_retry_scheduler','pg_cron_every_minute',
      'webhook_scheduler_job','github-webhook-worker-v1'
    ),
    updated_at=now()
where connector_key='github.backend_ops';

insert into public.connector_capability_matrix_v2(
  connector_key,capability,capability_level,verified,verification_source,risk_level,notes,metadata,updated_at
) values
('github.backend_ops','webhook_wake_auth',5,false,'runtime-required','low','Wake proxy authenticates against a Supabase Vault-held generated credential.',jsonb_build_object('function','apex-github-webhook-wake','vault_secret_name','github_worker_wake_secret_v1'),now()),
('github.backend_ops','webhook_immediate_wake',5,false,'runtime-required','low','Verified delivery trigger best-effort wakes the queue worker immediately after enqueue.',jsonb_build_object('trigger','github_webhook_delivery_enqueue_v1','wake_function','apex-github-webhook-wake'),now()),
('github.backend_ops','webhook_retry_scheduler',5,false,'runtime-required','low','pg_cron recovery wake invokes the authenticated wake proxy every minute for delayed or missed work.',jsonb_build_object('jobname','github-webhook-worker-v1','schedule','* * * * *'),now())
on conflict (connector_key,capability) do update set
  capability_level=excluded.capability_level,
  verified=public.connector_capability_matrix_v2.verified,
  verification_source=case when public.connector_capability_matrix_v2.verified then public.connector_capability_matrix_v2.verification_source else excluded.verification_source end,
  last_verified_at=case when public.connector_capability_matrix_v2.verified then public.connector_capability_matrix_v2.last_verified_at else null end,
  risk_level=excluded.risk_level,
  notes=excluded.notes,
  metadata=public.connector_capability_matrix_v2.metadata || excluded.metadata,
  updated_at=now();
