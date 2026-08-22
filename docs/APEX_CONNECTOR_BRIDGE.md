# APEX Connector Bridge

## Purpose

The connector bridge allows APEX to admit evidence from authenticated session integrations without copying OAuth tokens, API keys, cookies, or other credentials into this repository. APEX issues or receives structured request and receipt objects; the authenticated external session performs the provider operation and returns a receipt for validation.

> A configured connector is not proof of a live provider. A successful health check is not permission to mutate an external system. A read receipt is evidence, not external-action authority.

## Provider catalog

The active catalog is [`../config/apex_connector_catalog.json`](../config/apex_connector_catalog.json). It declares the provider, profile, operation, data class, and write policy. The initial profiles support repository integrity, evidence intake, current-source review, knowledge continuity, structured-state review, and API verification.

The first enabled operations are read operations only. GitHub, Dropbox, Google Workspace, Notion, Mem, Supabase, and Postman may provide receipt-backed retrieval when their named catalog operation is requested. Connector credentials remain in the authenticated session environment and never appear in repository source, tests, artifacts, workflow logs, audit receipts, or GitHub Actions configuration.

## Read flow

1. APEX builds a non-authorizing request using `src/connector_bridge_contract.py`.
2. The authenticated external bridge performs the catalogued provider read.
3. The bridge returns a receipt containing provider identity, operation, target reference, observation time, source references, and a content digest when material.
4. `src/connector_receipts.py` validates the catalog membership, profile, operation, receipt freshness, target, result state, and digest format.
5. `CaseBrainOrchestrator.admit_connector_read_receipt()` records safe receipt metadata in the existing audit ledger. It stores a target digest rather than provider content.

A failed, malformed, stale, unlisted, or action-claiming read receipt is refused. It does not become a source, recommendation, or external action.

## External action flow

Every external write remains inactive in the initial catalog. This includes repository changes, issue creation, messages, emails, files, documents, database rows, deployments, signature requests, calendar changes, and any other provider mutation.

A later action can be considered only when all of the following records exist:

1. The specific provider operation is active in the versioned catalog and is marked as requiring approval.
2. A request names the provider, operation, target, stated consequence, and evidence receipts.
3. The user has supplied an exact approval record naming the approver, approval time, and approval reference.
4. The authenticated bridge produces an execution receipt identifying the resulting provider object.

The bridge contract rejects generic, targetless, missing, or mismatched approval records. Health probes, prior read receipts, system recommendations, and broad prior instructions are not execution authority.

## Operational limits

Scheduled connector writes remain disabled. The connector bridge does not introduce a background write loop or a direct network client into APEX. Any future background or event-triggered connector operation requires its own reviewed design, operation allowlist, schema validation, durable receipt strategy, and explicit user approval.

## Verification

Run the connector receipt regression suite and the audit-hardening suite:

```bash
python -m pytest -q tests/test_connector_receipts.py
python -m pytest -q tests/test_audit_hardening.py
```

The tests prove that catalogued reads can be admitted as non-authorizing evidence; unknown operations, stale receipts, malformed input, and write operations without active rules and exact approval are refused.

## Authenticated-session operation path

The repository now provides two helpers for live read evidence. `src/session_connector_dispatch.py` maps a validated APEX request to one documented, catalogued provider read plan. It does **not** invoke a provider, load a credential, or authorize an external action. The authenticated task host performs the planned provider read directly through its configured session integration. This separation keeps the host-specific connection boundary outside repository source and prevents a repository process from inheriting the host’s provider credentials.

After the host preserves its provider observation outside the repository, `scripts/admit_session_connector_receipts.py` receives an observation manifest and creates the corresponding read receipts. It reads each observation only to calculate a SHA-256 digest. The receipt ledger stores the connector, operation, profile, target digest, observation time, source-reference count, and content digest; it does not store the provider material. The command then admits each receipt to `CaseBrainOrchestrator` and reports `external_action_authorized: false` for every accepted item.

> The operation plan is evidence-retrieval plumbing, not standing access to act. A host must perform each provider read through its own authenticated connector, and every result remains non-authorizing when APEX admits it.

A host-run admission sequence has this form:

```bash
python scripts/admit_session_connector_receipts.py \
  --manifest /operator-controlled-path/observations.json \
  --receipt-ledger /operator-controlled-path/apex-read-receipts.jsonl \
  --commit-sha <current-protected-main-commit>
```

The manifest is operator-controlled, remains outside Git history, and points to local observation files created by direct authenticated reads. It must name a catalogued connector, read operation, profile, target, RFC3339 observation time, source reference, and the local observation path. Any malformed, stale, unlisted, or action-claiming item is refused.
