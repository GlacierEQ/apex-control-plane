# GitHub Backend Ops — Autonomous Webhook Wake

This document extends `GITHUB_BACKEND_OPS_CONNECTOR.md` with the production wake/retry path for the durable GitHub webhook queue.

## Topology

```text
HMAC-verified delivery
  -> github_webhook_delivery_enqueue_v1
       -> durable github_webhook_event_queue_v1 row
       -> best-effort immediate pg_net wake
            -> apex-github-webhook-wake
                 -> Vault credential validation
                 -> JWT-protected apex-github-webhook-worker

pg_cron every minute
  -> apex-github-webhook-wake
       -> apex-github-webhook-worker
       -> claim pending/retry work with FOR UPDATE SKIP LOCKED
```

The queue remains authoritative for durability. Immediate wake is only an acceleration path. If it fails, the event remains pending and the cron wake recovers it.

## Wake authentication

`apex-github-webhook-wake` intentionally uses custom authentication because `pg_cron` cannot provide the Supabase Edge Function JWT used by the protected worker.

The wake credential is generated inside Supabase Vault by migration. It is not embedded in Edge Function source, GitHub source, migration plaintext, or ChatGPT-visible output.

The public wake surface accepts only a bounded worker wake request. It validates the supplied `x-apex-worker-secret` through the service-role-only `validate_github_worker_wake_secret_v1` RPC, then calls the JWT-protected worker with the Supabase service role available inside the Edge runtime.

The resolver RPC `resolve_github_worker_wake_secret_v1` is service-role-only and exists for internal runtime composition; callers without service-role database authority cannot execute it.

## Scheduling

`github-webhook-worker-v1` runs every minute through `pg_cron` and calls the wake proxy with the Vault-held credential. The scheduled call uses `pg_net`, so the database transaction is not blocked on worker completion.

## Verified runtime behavior

The wake path was exercised end-to-end:

- request without `x-apex-worker-secret` -> HTTP 401 `worker_wake_auth_required`;
- Vault-authenticated wake -> HTTP 200 and worker response HTTP 200;
- verified-style synthetic delivery -> queue row created and immediately awakened;
- wake response claimed exactly one event and the worker completed it as `ignored` because the event was a `ping` with no refresh work;
- the cron recovery job independently ran successfully at 2026-08-31 17:24:00 UTC and reached the authenticated wake path with no leftover work.

Synthetic proof rows are explicitly marked as synthetic and retained where append-only evidence contracts prevent deletion.

## Migrations

- `20260831172232_github_webhook_worker_scheduler_v1.sql`
- `20260831172331_github_webhook_worker_wake_v1.sql`
- `20260831172617_github_webhook_worker_scheduler_registry_v1.sql`

These migrations are rebuild-safe: they create structural capability declarations as unverified on a fresh installation while preserving verified runtime evidence when replayed over an already-probed system.

## Remaining external dependency

The worker wake path is complete. The only external webhook dependency remains the GitHub App webhook signing secret itself. `apex-github-webhook` continues to fail closed until the same signing secret is bound in backend configuration/Keymaster and the GitHub App webhook configuration.
