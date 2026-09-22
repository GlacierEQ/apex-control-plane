# APEX Approved Provider-Operation Bridge

## Purpose

The APEX connector layer supports more than evidence retrieval. It can prepare and govern a **specific provider mutation** when attributable Operator source authorizes that action either directly or as a routine constituent of a bounded plan, batch, or action class. The repository remains unable to obtain provider credentials or make network calls. Instead, it validates the action against the recovered authorization scope, binds the constituent operation immutably for idempotency/readback, issues a direct authenticated-host operation plan, and admits a digest-only execution receipt after the host completes the provider action.

> A provider capability is not standing access to act. A validated read receipt is not write authority. Authorization must be attributable to recovered Operator source and must cover the constituent action. A valid explicit-action, plan/batch, or action-class envelope may cover routine constituent actions without manufacturing a fresh per-action approval; destructive actions and material strategy deltas require renewed explicit authority unless the source-bound envelope expressly covers them.

## Core invariants

| Invariant | Enforcement |
| --- | --- |
| Authorization scope | A legacy explicit-action approval binds the full immutable action through `approval_scope_sha256`. A source-bound envelope authorizes only the connector, allowed operation set, target constraints, scope kind/source reference, and destructive/material-delta flags it actually carries; the concrete payload, consequence, evidence references, and idempotency key are then bound to the constituent action for integrity/readback rather than silently treated as separately Operator-approved fields. |
| Catalog allowlist | A request must name a catalogued write operation whose `enabled` setting is `true` and whose `authorization_required` setting remains `true`. |
| Direct authenticated boundary | Repository code never invokes an MCP tool, browser action, `gws` command, or provider API. The task host performs exactly one approved provider action directly. |
| No credential or provider-content retention | Plans, audit records, and JSONL ledgers contain provider identifiers and SHA-256 digests only. Provider credentials, raw input, raw output, and manifest files remain outside Git history. |
| Idempotency | Each request requires an idempotency key. A runtime rejects a key reused with a different immutable action scope and returns a duplicate result without admitting a second execution. |
| Mutation readiness | The request carries mutation evidence evaluated through `epistemic_risk_gate.evaluate_execution`. A `research_required` or `block` result prevents a host execution plan. |
| Completion evidence | A successful provider action requires a provider execution receipt, a terminal readback reference, and verification evidence. The runtime refuses any completion claim with missing evidence. |
| No autonomous execution | Scheduled connector writes remain disabled. There is no background loop, repository-side provider client, or deferred dispatch that can turn a validated plan into an external action. |

## Immutable action and approval scope

An action proposal remains non-authorizing. It becomes an executable host plan only after APEX validates either (a) a legacy exact-action approval or (b) a source-bound authorization envelope whose connector/operation/target constraints cover the proposed routine constituent action. The legacy exact-action digest is retained as a compatibility/idempotency binding, not as a new Operator approval when authority is inherited from a valid envelope.

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

The immutable action binding contains only the connector, operation, target, provider-input digest, stated consequence, sorted evidence references, and idempotency key. For the legacy explicit-action path, the approval reference identifies that exact authorization record. For source-bound authorization, `authorization_envelope.source_ref` identifies the controlling Operator source and the envelope proves only the scope it actually encodes: connector, allowed operation set, target constraints, scope kind, and destructive/material-delta flags. The concrete payload, consequence, evidence references, and idempotency key are accepted as constituent-action data only after that membership check and are then locked by the synthesized exact-action digest for idempotency/readback integrity.

`plan_ref` is a provenance/plan-identity pointer required for `plan_batch`; the runtime does not dereference it as a second approval service. Mechanical membership is enforced by the envelope's operation and target constraints. If the controlling Operator source intends payload-specific authorization rather than a routine action class, use the explicit-action path (or a future narrower envelope contract) instead of pretending the current plan/action-class envelope constrains fields it does not encode.

### Authorization inheritance contract

Routine constituent actions inherit authority only from an independently resolved Operator source record whose verified scope covers the connector, operation/action class, target constraints, provider-input constraints, and consequence constraints; no action request can manufacture that source record. Concrete provider input, consequence, evidence references, and idempotency are bound into the action digest after scope validation; that digest is an idempotency/readback binding, not a new approval. A strategy-changing action outside the verified scope requires a new Operator source record; a caller-supplied material-strategy flag cannot expand or prove authority.

## Host execution sequence

| Stage | APEX responsibility | Authenticated host responsibility | Result |
| --- | --- | --- | --- |
| Proposal | Build a non-authorizing proposal and calculate its immutable scope digest. | None. | Reviewable proposal with `external_action_authorized: false`. |
| Authorization validation | Verify catalog activation, attributable source-bound authorization (explicit action, plan/batch, or action class), membership under the envelope's encoded connector/operation/target constraints, evidence references, mutation readiness, and idempotency. | None. | One execution plan with `external_action_authorized: true`. |
| Provider action | None. | Perform exactly the provider operation named in the plan using the active authenticated session. | Provider result retained outside Git history. |
| Readback | None. | Perform the plan’s required terminal readback and preserve a local observation. | Provider object reference and local verification material. |
| Receipt admission | Hash the local execution and readback observations; validate and append safe audit metadata. | Supply the local manifest and observation paths. | Immutable audit receipt with no credentials or provider content. |

The host receives an execution plan only after validation. It must not substitute a different provider tool, target, payload, or operation. A host refusal, provider error, out-of-scope or stale authorization, missing readback, or mismatched receipt must surface as a refusal or failure and may never be rewritten as a completed action. Accepted execution receipts are durably audited by `control_plane_runtime.py`; pre-admission validation failures raise to the caller and are persisted only when the calling host/runtime explicitly records that failed attempt.

## Execution receipt

A successful receipt is a record of a provider action that has already occurred, not an authorization to act. It contains the action-request ID, idempotency key, connector, operation, execution time, target digest, provider-input digest, provider-output digest, result-object reference digest, terminal-readback digest, verification state, and source-reference count. Raw provider material, request payloads, and provider credentials never enter the receipt ledger.

The runtime records accepted execution receipts as `admit_connector_execution_receipt` audit entries. These entries may report `external_action_authorized: true` only because the validated action was covered by attributable Operator authority and the receipt proves the one corresponding provider action completed. That authority may be an exact explicit action or a source-bound plan/batch/action-class envelope covering the routine constituent action. Read-receipt admission remains permanently non-authorizing.

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
| `connector_receipts.py` / `authorization_compat.py` / `source_bound_authorization.py` | Validate immutable action binding, source-bound authorization membership, legacy exact-action compatibility, action execution receipts, and safe audit details. |
| `connector_bridge_contract.py` | Build non-authorizing proposals and authorization-validated execution requests. |
| `session_connector_dispatch.py` | Map a validated action request to one direct authenticated provider-operation plan without invoking it. |
| `authenticated_session_bridge.py` | Build digest-only execution receipts from host-side action and readback observations. |
| `control_plane_runtime.py` | Revalidate exact-action or source-bound authorization through the compatibility adapter, then admit execution receipts with action-level idempotency and immutable audit records. |
| Operator scripts | Prepare validated plans and admit local receipts. They read local manifests and observations but never call provider tools. |
| Tests | Prove plan/batch/action-class inheritance for routine constituents and refusal for inactive routes, out-of-scope actions, destructive/material deltas without renewed authority, unsafe query payloads, failed readiness gates, duplicate requests, provider-content leakage, missing readback, and provider-call attempts. |

## Operating limit

The bridge can make approved operations available; it does not grant ongoing authority. Every mutation still needs attributable source-bound Operator authority covering the action and must be initiated from the current task through an authenticated host session. Routine constituent actions may inherit a valid explicit-action, plan/batch, or action-class authorization; they do not require a newly manufactured per-action approval. Destructive operations are derived from catalog/risk evidence and require an independently resolved source scope that allows them. Strategy-changing actions outside the verified source scope require a new Operator source record; a caller-supplied `material_strategy_delta` flag cannot expand or prove authority. No scheduled workflow, automation rule, or background runner may consume action requests.
