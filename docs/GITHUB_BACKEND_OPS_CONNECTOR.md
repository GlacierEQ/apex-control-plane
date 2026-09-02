# GitHub Backend Ops Connector

`github.backend_ops` is the Supabase backend-ops execution system for GitHub. GitHub remains the implementation/source authority. Backend Ops owns operational routing, concurrency control, receipts, circuit state, event intake, and execution state.

## Runtime topology

The production path is now:

```text
caller
  -> apex-github-router
       -> permission-aware route policy
       -> resource lease / compare-before-write / circuit breaker
       -> apex-github-connector
            -> GitHub App + Keymaster
            -> short-lived single-repository installation token
            -> GitHub API
       -> append-only route decision

GitHub webhook
  -> apex-github-webhook
       -> HMAC verification + delivery dedupe
       -> github_webhook_event_queue_v1
       -> apex-github-webhook-worker
       -> apex-github-router
```

The connector function is deliberately an internal execution primitive now. New backend callers should enter through `apex-github-router`.

## Authentication

The gateway composes the existing GitHub App bootstrap and Keymaster path. For each repository operation it resolves the App key only in memory, verifies the live installation, resolves the repository identity, mints a short-lived **single-repository** installation token with only the required permission, performs the call, and revokes the token best-effort.

App keys and installation tokens are never persisted or returned.

## Best-of-world routing

The current GitHub App grants:

- `metadata:read`
- `contents:write`
- `issues:write`
- `actions:write`
- `workflows:write`

It does **not** grant `pull_requests`.

The router therefore uses the strongest available lane instead of pretending every capability belongs to one connector:

- repository/files/issues/actions -> `github.backend_ops`
- PR list/get -> backend Issues API projection when lightweight detail is sufficient
- full PR search/read -> `github.native`
- PR creation -> `github.native:create_pull_request`
- PR review -> `github.native:add_review_to_pr`

`route.plan` exposes that decision before execution. A live probe for `pull.create` selected `github.native:create_pull_request` because the backend App route is not actually authorized.

## Mutation contract

Code mutation is PR-first and now has **two independent correctness checks**.

### Before mutation

`contents.put` through the router requires `expected_before_sha`:

- provide the current blob SHA for an update;
- provide `null` for an intentional create;
- the router reads GitHub immediately before the mutation;
- a mismatch returns HTTP 409 `stale_write_precondition` and the mutation is not sent.

### During mutation

Every router write acquires an atomic resource lease. File writes are locked by repository + branch + path. Two different request IDs cannot mutate the same resource concurrently while a lease is active.

A live lease probe proved:

1. request 1 acquired the resource;
2. request 2 was rejected while request 1 held it;
3. request 2 acquired the same resource after release.

### After mutation

The internal gateway reads deterministic mutations back and verifies the observed result before reporting success. Successful write request IDs are idempotent.

A GitHub success followed by receipt failure is never silently promoted into ordinary success.

There is no merge, delete-file, delete-branch, delete-repository, force-ref, or secret-export operation in the backend execution surface.

## Circuit breaker and retries

The router keeps per-operation circuit state in `github_connector_circuit_v2`.

- reads retry 429/502/503/504 with bounded backoff;
- writes are **not automatically retried**, because a retry after an ambiguous external mutation can duplicate side effects;
- three consecutive retryable failures open that operation circuit for 60 seconds;
- a successful operation resets the circuit.

This keeps transient GitHub failures from turning into request storms.

## Durable evidence

The GitHub lane now has four distinct evidence layers:

- `github_connector_receipts_v1` — gateway execution receipts;
- `github_connector_route_decisions_v2` — append-only route/fallback/retry/precondition decisions;
- `github_webhook_deliveries_v1` — verified webhook delivery metadata + payload hashes;
- `github_webhook_event_results_v1` — append-only results created by webhook-driven refresh work.

`github_connector_operation_leases_v2` holds concurrency state, and `github_connector_circuit_v2` holds temporal failure state.

## Webhook event runtime

A webhook is no longer merely recorded.

After HMAC verification succeeds, `github_webhook_delivery_enqueue_v1` creates one durable event in `github_webhook_event_queue_v1`. The worker claims events atomically using `FOR UPDATE SKIP LOCKED`, preventing duplicate workers from owning the same job.

The worker maps events to bounded refresh work:

- push -> repository + Actions refresh;
- PR event -> repository + PR projection;
- issue event -> repository + issue refresh;
- workflow/check event -> repository + Actions refresh.

Retryable failures are requeued with backoff; terminal failures are preserved with an error state.

A retained synthetic probe verified the entire queue/worker path: one push event was claimed once and completed `repo.get` plus `actions.runs`, both HTTP 200 through the router.

## Verified runtime surface

End-to-end probes now verify:

- GitHub App and installation binding;
- 1,184 repositories visible to the installation;
- repository metadata;
- file read;
- recursive tree;
- branches;
- commits;
- code search;
- issues;
- PR issue projection;
- Actions run listing;
- non-default-branch `contents.put` with gateway readback;
- native PR fallback planning;
- compare-before-write;
- stale-write rejection;
- atomic resource leasing;
- webhook queue creation;
- webhook worker execution.

The router write probe advanced `connectors/github_backend_ops_runtime_probe.json` only after the preflight SHA matched. A second request with the now-stale SHA was rejected with HTTP 409 and did not land.

## Remaining external dependency

The GitHub App webhook secret is bound through Keymaster/Vault. A controlled signed delivery verified `signature_verified=true`, reached queue status `completed`, rolled its parent delivery to `processed`, and produced successful `repo.get` and `actions.runs` result receipts. Raw webhook payloads and raw secrets are not persisted by the connector plane.

## Migrations

- `20260831154923 github_backend_ops_connector_v1`
- `20260831160850 github_backend_ops_routing_v1`
- `20260831170616 github_backend_ops_router_v2`
- `20260831170915 github_webhook_worker_v1`

## Validation harnesses

Temporary public self-test functions are used only long enough to call JWT-protected functions with the backend service role. After verification they are retired behind JWT and return only HTTP 410. They are not production execution routes.

## High-volume batch and bulk-read plane

Backend Ops now has a durable GitHub batch plane rather than one Edge invocation per GitHub item.

The batch tables are `github_batch_runs_v2`, `github_batch_items_v2`, `github_batch_receipts_v2`, and `github_batch_workers_v2`. Work is claimed with leases, finalized against an explicit quality policy, projected into `github_batch_metrics_v2`, and terminal failures/blocks can be inspected through `github_batch_dlq_v2` and selectively replayed without repeating successful items.

### Bulk-read execution

The initial high-concurrency worker design exposed a real Supabase nested-function limit: worker -> router -> connector fan-out produced Edge `RateLimitError` failures under 100-item workloads.

The production read path therefore changed architecture rather than simply lowering concurrency:

```text
batch queue
  -> apex-github-batch-worker
      -> one apex-github-connector bulk.read call per claim
          -> bounded in-process read concurrency
          -> GitHub App / Keymaster / repo-scoped short-lived tokens
          -> GitHub API
          -> item-level connector receipts
      -> item-level batch QC/finalization

writes
  -> apex-github-router
      -> lease + precondition + circuit + gateway readback
```

`bulk.read` is read-only, accepts at most 50 items per connector call, and rejects operations outside the explicit read allowlist.

The verified 100-item acceptance batch `313f6282-2db9-41e7-b879-d6cc1ee41dad` completed 100/100 on the first attempt with zero retries, zero blocks, zero ambiguous outcomes, and 100/100 QC passed. Item-equivalent latency was 240.20 ms average, p50 221 ms, p95 279 ms, and p99 357 ms.

### Worker truth

Worker state is explicit:

- `github-edge-batch-v2`: online and verified.
- `glacier-desktop-commander`: source-ready but unbound; it is not selected until a live device heartbeat and approved roots are verified.
- `github-key-runner`: offline until a bound runner session exists.

No source-ready or offline lane is silently promoted into an executable route.

## Control-plane health projection

`control_plane_runtime_health_v1` is the service-role-only health projection for the operating plane. It combines registry state, verified capabilities, routes, current GitHub execution evidence, batch backlog/inflight state, worker heartbeats, and webhook queue state.

`control_plane_health_snapshot_v1()` returns a one-call fleet summary and an expanded `github.backend_ops` record.

Health semantics distinguish present state from history. Historical failed benchmark items remain visible as evidence but do not keep a currently successful connector permanently degraded.

After the bulk-read acceptance run, `github.backend_ops` read back as healthy with 104 recent successes, zero recent failures, no batch backlog/inflight work, one live Edge worker, no stale online workers, and no webhook failures.
