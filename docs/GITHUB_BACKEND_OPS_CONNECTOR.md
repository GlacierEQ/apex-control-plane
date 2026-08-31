# GitHub Backend Ops Connector

## What this is

`github.backend_ops` is the Supabase backend-ops execution gateway for GitHub. GitHub remains the implementation/source authority; the gateway performs bounded GitHub App operations and writes durable execution evidence back to backend-ops.

## Authentication model

The connector composes the existing verified GitHub App bootstrap and Keymaster path:

1. resolve the GitHub App private-key reference inside backend-ops;
2. normalize the key only in memory;
3. mint a short-lived App JWT;
4. verify the live installation binding;
5. resolve the target repository identity;
6. mint a **single-repository installation token** with only the permission needed for the requested operation;
7. execute the operation;
8. revoke the installation token best-effort;
9. never persist or return the App key or installation token.

## PR-first mutation

The connector contains no destructive API surface.

Code mutations are intentionally limited to:

- create a non-default branch;
- create/update a file on a non-default branch;
- read the file back;
- compare SHA-256 of desired and observed content;
- create a pull request.

A file write that targets the repository default branch is rejected inside the execution function itself.

There is no merge, delete-file, delete-branch, delete-repository, force-ref, or secret-export operation.

## Read surface

`repo.get`, `contents.get`, `tree.list`, `branches.list`, `commits.list`, `code.search`, `issues.list`, `issue.get`, `pulls.list`, `pull.get`, and `actions.runs`.

## Write/trigger surface

`branch.create`, `contents.put`, `issue.create`, `issue.comment`, `pull.create`, `pull.comment`, `pull.review`, and `workflow.dispatch`.

Every successful write uses a caller-supplied request ID for idempotency. Where GitHub exposes deterministic readback, the connector verifies the mutation before reporting success. Workflow dispatch is reported only as accepted by GitHub; downstream workflow completion is never self-certified.

## Receipts

`github_connector_receipts_v1` is append-only and records:

- request/correlation IDs;
- operation and repository;
- mutation class and outcome;
- request/response SHA-256;
- GitHub request ID;
- target ref;
- before/after SHA where available;
- readback verification;
- duration and bounded result summary.

Successful write request IDs are unique, making retries replay-safe.

## Webhooks

`apex-github-webhook` is deployed as an HMAC-SHA256 ingress. It verifies `X-Hub-Signature-256`, deduplicates on `X-GitHub-Delivery`, restricts repository ownership to the configured GitHub owner, and stores metadata + payload hash only.

The raw webhook payload is not persisted.

The webhook ingress remains fail-closed until a webhook secret reference is bound in `github_connector_config_v1` and the same secret is configured on the GitHub App webhook.

## Runtime truth

The edge functions and schema are deployed in `supabase-backend-ops`. Runtime operation capabilities remain marked unprobed until an authenticated end-to-end call produces a receipt. Deployment/source readback is not promoted into a false runtime-success claim.
