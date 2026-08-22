# APEX Approved Provider-Operation Bridge

## Purpose

The APEX connector layer supports more than evidence retrieval. It can prepare and govern a **specific provider mutation** when the operator has explicitly approved that exact mutation. The repository remains unable to obtain provider credentials or make network calls. Instead, it validates an immutable operation request, issues a direct authenticated-host operation plan, and admits a digest-only execution receipt after the host completes the provider action.

> A provider capability is not standing access to act. A validated read receipt is not a write approval. A generic approval, a prior approval, a recommendation, or a broad instruction cannot authorize a different provider operation, target, payload, consequence, or idempotency key.

## Core invariants

| Invariant | Enforcement |
| --- | --- |
| Exact scope | The approval binds the connector, operation, target, provider-input digest, stated consequence, evidence references, and idempotency key through `approval_scope_sha256`. |
| Catalog allowlist | A request must name a catalogued write operation whose `enabled` setting is `true` and whose `approval_required` setting remains `true`. |
| Direct authenticated boundary | Repository code never invokes an MCP tool, browser action, `gws` command, or provider API. The task host performs exactly one approved provider action directly. |
| No credential or provider-content retention | Plans, audit records, and JSONL ledgers contain provider identifiers and SHA-256 digests only. Provider credentials, raw input, raw output, and manifest files remain outside Git history. |
| Idempotency | Each request requires an idempotency key. A runtime rejects a key reused with a different immutable action scope and returns a duplicate result without admitting a second execution. |
| Mutation readiness | The request carries mutation evidence evaluated through `epistemic_risk_gate.evaluate_execution`. A `research_required` or `block` result prevents a host execution plan. |
| Completion evidence | A successful provider action requires a provider execution receipt, a terminal readback reference, and verification evidence. The runtime refuses any completion claim with missing evidence. |
| No autonomous execution | Scheduled connector writes remain disabled. There is no background loop, repository-side provider client, or deferred dispatch that can turn a validated plan into an external action. |

## Immutable action and approval scope

An action proposal remains non-authorizing. It becomes an executable host plan only after APEX validates a request whose approval scope exactly matches the proposed action.

```json
{
  "schema_version": 1,
  "action_request_id": "uuid",
  "connector": "github",
  "operation": "issue.create",
  "target": {"repository": "GlacierEQ/apex-control-plane"},
  "provider_input": {"title": "...", "body": "..."},
  "consequence": "Creates one named issue visible to repository collaborators.",
  "evidence_refs": ["receipt-github-001"],
  "idempotency_key": "operator-chosen-stable-key",
  "execution_evidence": {
    "epistemic_state": "observed",
    "blast_radius": "local",
    "reversibility": "reversible",
    "source_state_observed": true,
    "dependency_map_observed": true,
    "recovery_checkpoint_verified": true,
    "recovery_procedure_verified": true,
    "dry_run_verified": true,
    "staged_execution": true,
    "novel_operation": false,
    "operator_explicit_irreversible_authorization": false
  },
  "approval": {
    "approved_by": "GlacierEQ",
    "approved_at": "RFC3339 timestamp",
    "approval_reference": "operator-provided reference",
    "approval_scope_sha256": "sha256 of immutable action scope"
  }
}
```

The immutable action scope contains only the connector, operation, target, provider-input digest, stated consequence, sorted evidence references, and idempotency key. The approval reference identifies the user authorization record; the scope digest proves that this record applies to this action and no other action.

## Host execution sequence

| Stage | APEX responsibility | Authenticated host responsibility | Result |
| --- | --- | --- | --- |
| Proposal | Build a non-authorizing proposal and calculate its immutable scope digest. | None. | Reviewable proposal with `external_action_authorized: false`. |
| Approval validation | Verify catalog activation, exact approval scope, evidence references, mutation readiness, and idempotency. | None. | One execution plan with `external_action_authorized: true`. |
| Provider action | None. | Perform exactly the provider operation named in the plan using the active authenticated session. | Provider result retained outside Git history. |
| Readback | None. | Perform the plan’s required terminal readback and preserve a local observation. | Provider object reference and local verification material. |
| Receipt admission | Hash the local execution and readback observations; validate and append safe audit metadata. | Supply the local manifest and observation paths. | Immutable audit receipt with no credentials or provider content. |

The host receives an execution plan only after validation. It must not substitute a different provider tool, target, payload, or operation. A host refusal, provider error, expired approval, missing readback, or mismatched receipt is recorded as a refusal or failure, never rewritten as a completed action.

## Execution receipt

A successful receipt is a record of a provider action that has already occurred, not an authorization to act. It contains the action-request ID, idempotency key, connector, operation, execution time, target digest, provider-input digest, provider-output digest, result-object reference digest, terminal-readback digest, verification state, and source-reference count. Raw provider material, request payloads, and provider credentials never enter the receipt ledger.

The runtime records accepted execution receipts as `admit_connector_execution_receipt` audit entries. These entries may report `external_action_authorized: true` only because the validated action scope carried an exact approval and the receipt proves the one corresponding provider action completed. Read-receipt admission remains permanently non-authorizing.

## Initial operation policy

The code must support catalogued provider operations through direct authenticated plans. A write route is eligible only when its provider operation has been verified against the active host connector inventory and is assigned a provider-specific terminal readback. Destructive or irreversible actions require the stricter mutation-readiness evidence already defined in `epistemic_risk_gate.py`, including explicit irreversible authorization and a preservation checkpoint.

| Provider | Planned execution boundary | Required terminal readback |
| --- | --- | --- |
| GitHub | Authenticated browser/session operation | Read the resulting issue or pull request by returned object ID. |
| Google Workspace | Direct authenticated `gws` command | Read the resulting Drive, Docs, Sheets, or Slides object by returned ID. |
| Notion | Direct authenticated Notion operation | Fetch the resulting page or database object by returned ID. |
| Mem | Direct authenticated MCP operation | Fetch the resulting note or collection by returned ID and expected version. |
| Supabase | Direct authenticated database operation | Run a constrained SELECT that identifies the changed row(s). |
| Postman | Direct authenticated MCP operation | Fetch the resulting workspace, collection, spec, monitor, or other returned object by ID. |
| Dropbox | Direct authenticated MCP operation | Retrieve metadata for the resulting file or folder by returned path or ID. |

Dropbox and Notion are not added to an active mutation allowlist until their provider tool inventories respond reliably during implementation. This is an availability constraint, not an authorization shortcut.

## Planned repository surfaces

The implementation adds validation and audit code only. It does not create a provider client.

| Surface | Responsibility |
| --- | --- |
| `connector_receipts.py` | Validate immutable action scope, exact approval binding, action execution receipts, and safe audit details. |
| `connector_bridge_contract.py` | Build non-authorizing proposals and approval-validated execution requests. |
| `session_connector_dispatch.py` | Map a validated action request to one direct authenticated provider-operation plan without invoking it. |
| `authenticated_session_bridge.py` | Build digest-only execution receipts from host-side action and readback observations. |
| `control_plane_runtime.py` | Admit execution receipts with action-level idempotency and immutable audit records. |
| Operator scripts | Prepare validated plans and admit local receipts. They read local manifests and observations but never call provider tools. |
| Tests | Prove refusal for inactive routes, scope mismatches, expired or generic approvals, unsafe query payloads, failed readiness gates, duplicate requests, provider-content leakage, missing readback, and provider-call attempts. |

## Operating limit

The bridge can make approved operations available; it does not grant ongoing authority. Every mutation still needs its own exact approval record and must be initiated from the current task through an authenticated host session. No scheduled workflow, automation rule, or background runner may consume action requests.
