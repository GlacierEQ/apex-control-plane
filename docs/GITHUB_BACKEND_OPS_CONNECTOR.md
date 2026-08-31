# GitHub Backend Ops Connector

`github.backend_ops` is the Supabase backend-ops execution gateway for GitHub. GitHub remains the implementation/source authority; backend-ops owns operational routing, receipts, health, and execution state.

## Authentication

The gateway composes the existing GitHub App bootstrap and Keymaster path. For each repository operation it resolves the App key only in memory, verifies the live installation, resolves the repository identity, mints a short-lived **single-repository** installation token with only the required permission, performs the call, and revokes the token best-effort. App keys and installation tokens are never persisted or returned.

## Mutation contract

Code mutation is PR-first:

- default-branch file writes are rejected inside the runtime;
- destructive operations are not exposed;
- deterministic writes require readback before success;
- successful write request IDs are idempotent;
- a GitHub success followed by receipt failure is reported as an ambiguous external outcome, never as verified success.

There is no merge, delete-file, delete-branch, delete-repository, force-ref, or secret-export operation.

## Best-of-world composition

The current GitHub App grants `metadata:read`, `contents:write`, `issues:write`, `actions:write`, and `workflows:write`. It does **not** grant the GitHub `pull_requests` permission.

The backend connector therefore does not fake that capability:

- `pulls.list` and `pull.get` use the Issues API and explicitly return `detail_level=issue_projection`;
- backend `pull.create` and `pull.review` routes are disabled;
- full PR search/read, PR creation, and PR reviews route to the already-connected `github.native` connector.

This keeps the GitHub App lane narrow while retaining the richer native connector where it is genuinely stronger.

## Verified runtime surface

End-to-end backend probes verified:

- GitHub App + installation binding;
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
- non-default-branch `contents.put`.

The write probe produced commit `0d5053c5fe484b1c8ab55218d4d1ff529de2e38b`. The gateway compared requested and observed content SHA-256 and reported success only after they matched.

## Durable receipts

`github_connector_receipts_v1` is append-only and records request/correlation IDs, operation, repository, mutation class, outcome, request/response hashes, GitHub request ID, target ref, before/after SHA when available, readback state, duration, and a bounded result summary.

`github_webhook_deliveries_v1` deduplicates by GitHub delivery ID and stores metadata plus payload hash, never raw webhook payload.

## Webhook state

`apex-github-webhook` is deployed with HMAC-SHA256 verification and owner scoping. A live fail-closed probe returned HTTP 503 `webhook_secret_not_bound` and persisted zero delivery rows, which is the intended state until the same webhook secret is bound in Keymaster/backend config and the GitHub App.

## Ephemeral validation harness

The temporary self-test function was retired after the read/write probes and redeployed with JWT verification as a 410-only tombstone. It is not a production execution route.
