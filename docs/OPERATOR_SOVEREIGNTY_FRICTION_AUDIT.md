# Operator Sovereignty Friction Audit

**Status:** active defect map  
**Purpose:** identify control-plane behavior that makes the Operator serve the system instead of the system serving the Operator.  
**Primary invariant:** **Operator states intent; system absorbs complexity.**

## Governing rule

The system exists to convert Operator intent into the strongest coherent verified outcome with minimum Operator burden.

A control is defective when it makes the Operator repeatedly perform internal system work such as generating approval IDs, selecting pillars, restating already-authorized intent, manually routing tools, creating governance artifacts, reviewing routine reversible changes, or satisfying proof machinery before ordinary work can begin.

Verification, provenance, receipts, idempotency, exact-target checks, rollback preparation, and provider readback are valuable **when they are performed by the system**. They must not become an operator-facing permission ritual.

### Correct authority model

1. **Inherited authorization — automatic**
   - reads, retrieval, analysis, local computation;
   - reversible file/repository edits within the requested objective;
   - routine commits and branches;
   - internal indexes, registries, memory notes, case organization, document generation;
   - reversible/idempotent database updates within known schemas;
   - tests, builds, verification, receipts, provider readback.
   - The Operator's task authorizes these implementation steps.

2. **Automatic but internally guarded**
   - production deployments, merges, provider mutations, external synchronization, larger state transitions when safely reversible and clearly inside the requested objective.
   - The system owns exact-target checks, snapshots, rollback, idempotency, verification, and readback.

3. **Explicit final confirmation — consequence-specific only**
   - irreversible deletion or destructive overwrite without reliable rollback;
   - legal filing, service, court/law-enforcement contact, evidence release;
   - credential/security authority changes;
   - financial or other materially irreversible action;
   - publication/send to a third party when not already explicitly authorized by the Operator's request;
   - scope expansion beyond the Operator-defined objective.

A user's explicit instruction to perform the consequential action is itself authority for the action to the extent allowed by the execution environment; internal metadata must not manufacture an additional ritual confirmation.

## Audit coverage

This audit used organization-wide GitHub default-branch indexed searches across the GlacierEQ estate and deep reads of runtime-authoritative GlacierEQ-authored control-plane repositories. Hundreds of repositories were enumerated. Imported/upstream/vendor repositories were excluded from architectural conclusions unless wired into GlacierEQ execution.

This is not a byte-for-byte audit of every historical branch, generated artifact, or imported dependency. It is a control-plane audit of the code and contracts capable of shaping the Operator experience. The evidence is sufficient to establish a systemic pattern rather than an isolated defect.

## P0 — active authority inversions

### P0-1 — `computer-user`: mutation is incorrectly equated with repeated human approval

**Affected paths**
- `GlacierEQ/computer-user/runtime/tool_policy.py`
- `GlacierEQ/computer-user/config/tool_system.json`
- `GlacierEQ/computer-user/scripts/ci/verify_tool_system.py`
- `GlacierEQ/computer-user/computer_user/mcp_server.py`
- `GlacierEQ/computer-user/connector_hub.py`
- `GlacierEQ/computer-user/docs/KERNEL_SERVICE.md`
- `GlacierEQ/computer-user/MASTER_TOOL_BELT.md`

**Defect**
- Runtime classifies `WRITE`, `DELETE`, `EXTERNAL_SEND`, and `ADMIN` together as mutation classes and denies them unless `approved=True`.
- CI requires every non-read tool to carry `approval_required=True`.
- Routine `github.push_files` is approval-gated.
- Case workspace folder creation/organization blocks unless `human_approved=True`.
- MCP plumbing exposes `approved` as a caller-facing parameter, leaking governance into the interface.
- Even without a policy graph, known mutations still require explicit approval.

**Why wrong**
The Operator's original task is treated as insufficient authority for the implementation steps needed to accomplish that task. The system makes the Operator re-authorize its own mechanics.

**Required direction**
Replace blanket mutation approval with consequence-specific authority inheritance. Preserve exact target, idempotency, schema/account scope, verification, receipts, and destructive boundaries. Routine reversible writes inside an Operator-authorized objective should execute without a second prompt.

### P0-2 — `apex-control-plane`: verification/continuity has become permission to begin work

**Affected paths**
- `src/apex_strong_boot.py`
- `src/operator_fidelity_preflight.py`
- `src/strict_frontier_preflight.py`
- `recovery_gate.py`
- `config/apex_runtime_policy.json`
- `config/outcome_fidelity_policy.json`

**Defect**
- Strong boot will not create the runtime kernel until strict-frontier authority plus multiple sealed startup validations pass.
- Missing boot/continuity/fidelity receipts become blocking continuation states.
- `recovery_gate.py` blocks when a request is stale, unapproved, or lacks rollback readiness.
- Runtime policy globally sets `fail_closed=true` and requires startup gates before execution.

**Why wrong**
These mechanisms were created to preserve Operator intent, but they can prevent Operator intent from executing. Verification has been promoted from a reliability service into permission machinery.

**Required direction**
Convert recoverable continuity/provenance/proof gaps into autonomous reconstruction and uncertainty telemetry. Fail closed only where integrity, security, irreversibility, or scope expansion makes continuation unsafe. Missing context should trigger recovery-before-action, not permission paralysis.

### P0-3 — `apex-control-plane`: all connector writes require exact approval

**Affected paths**
- `src/connector_receipts.py`
- `config/apex_connector_catalog.json`
- connector gateway/router projections derived from the same model

**Defect**
The catalog validator requires every write operation to have `approval_required=true`, including routine operations such as:
- GitHub issue/PR creation;
- Google document create/update;
- Mem note/collection create/update;
- Supabase row insert/update;
- Postman collection/spec/monitor create/update.

**Why wrong**
Ordinary knowledge/state maintenance becomes a repeated approval ceremony instead of implementation work performed under inherited task authority.

**Required direction**
Make approval consequence-specific. Keep idempotency and terminal readback mandatory. Routine reversible writes inherit authority from the active Operator mission.

### P0-4 — Public Action Face: approval is assigned by pillar instead of consequence

**Affected paths**
- `GlacierEQ/public-actions-runner-host/scripts/action_face_plan.py`
- `GlacierEQ/public-actions-runner-host/config/pillar-actions.json`
- `GlacierEQ/public-actions-runner-host/scripts/apex_pillar_runner.py`
- `GlacierEQ/llm-runner-teams/docs/dispatch-guide.md`

**Defect**
Pillars G and I require approval IDs as a class. That means low-risk/internal work such as case-matrix updates, email archive ingestion, docket synchronization, brief preparation, or asset analysis can inherit the same approval ceremony as an actual filing/submission.

The dispatch guide additionally makes an operator/connector create job IDs, approval records, pillar metadata, and public job envelopes.

**Why wrong**
Organizational taxonomy controls authority. Internal routing metadata leaks into the user experience.

**Required direction**
Keep the hardened shared Action Face, OIDC, Keymaster, exact-SHA checkout, scoped tokens, private receipts, and token revocation. Remove pillar-wide user approval. The system should synthesize job IDs, pillars, source refs, claims, and approval records. Only the actual consequential action should surface for confirmation.

## P1 — high-friction secondary control planes

### P1-1 — `mega-mcp`: every write defaults to approval and GitHub ceremony

**Affected path:** `GlacierEQ/mega-mcp/src/policy/engine.ts`

Default behavior requires approval for writes and destructive actions and routes GitHub writes through branch + PR. Direct writes to main/master are forbidden.

**Required direction:** preserve branch/PR rollback paths as a risk-control option, not a universal operator chore. Low-risk reversible tested changes should be able to progress automatically inside standing authority.

### P1-2 — `mega-skills`: read-only mission firewall and universal epistemic gates

**Affected paths**
- `GlacierEQ/mega-skills/scripts/firewall.py`
- `skills/epistemic-gate/SKILL.md`
- `skills/quality-gate/SKILL.md`

The mission firewall requires `human_control=required`, fixes the execution mode to read-only, and forbids external mutation/network/deploy/merge through the normal mission runner. The epistemic gate describes one ladder as an immutable gate across all operations and denies operational action below a universal threshold.

**Why wrong**
Evidence burden should be claim- and consequence-specific. A universal proof ladder can become proof theater and a global tax on progress.

**Required direction:** quality/epistemic checks become hidden verification services. They may block a claim from being promoted as verified, but should not stop unrelated reversible execution.

### P1-3 — `aspen-grove-connectors`: all writes/execute routes are gated

**Affected path:** `foundation/ROUTE_POLICIES.md` and its seeded route-policy projections.

GitHub, Supabase, case-ops SQL, and Smithery mutation/execute routes are modeled as gated with approval required.

**Required direction:** preserve route identity/account scope/readback; inherit routine mutation authority from the active mission.

### P1-4 — `Pro-apex-fs-commander`: strong high-stakes evidence gate is useful, broad human review is not

**Affected paths**
- `apex_runtime/approval_gate.py`
- `apex/secret_policy.md`

The signed Ed25519 approval contract is appropriate for true high-stakes evidence publication/share/overwrite/external sync. It should remain for those consequences.

The broader policy that all PRs receive human review and auto-merge always requires manual approval is excessive for low-risk reversible maintenance.

**Required direction:** preserve cryptographic scope-binding for actual high-risk evidence actions; hide route-plan/signature/approval-object mechanics from the Operator.

### P1-5 — `colossus-gateway`: platform-level blast tiers are too coarse

**Affected path:** `APEX_SYSTEM_MAP.md`

Entire services such as GitHub, Notion, and Supabase are assigned T3/manual-approval treatment.

**Why wrong**
Risk attaches to the consequence, not the brand/platform. Editing a README is not equivalent to deleting a repository merely because both happen on GitHub.

**Required direction:** classify operations by reversibility, blast radius, external consequence, and rollback—not provider name.

## P2 — duplicated governance engines

Independent action/approval/firewall systems exist in:
- `computer-user`;
- `apex-control-plane`;
- `apex-core`;
- `mega-skills`;
- `mega-mcp`;
- `Pro-apex-fs-commander`;
- `aspen-grove-connectors`;
- Public Action Face / `llm-runner-teams`;
- Colossus-era blast-tier policy.

This duplication creates policy drift and contradictory execution behavior.

`apex-core/firewall.py` illustrates the risk: its default policy permits READ/WRITE/EXECUTE, its strict policy permits only READ, and `create_default_firewall()` registers both. A caller using `enforce_strictest()` would effectively reduce the system to read-only. Current organization-wide search did not find an external caller of `enforce_strictest()`, so this is presently a latent footgun rather than a proved live blocker.

**Required direction:** do not invent another policy engine. Converge existing execution surfaces toward one common authority principle while preserving specialized safety at the consequence boundary.

## Existing code that already expresses the correct model

### `AKOS/contracts/EXECUTION_FIRST_OPERATOR_CONTRACT.md`
This active contract already says:
- no repeated permission request when standing authority covers the action;
- no gate/receipt/CI/registry may redefine the Operator objective;
- standing authority may authorize recoverable objective-preserving work;
- `computer-user` should execute writes, sends, creates, updates, and uploads when authorized by task/standing authority;
- explicit approval remains for irreversible external actions, legal filings/service/publication/contact, repository/branch deletion, destructive overwrite, or history rewrite.

This is the strongest existing authority model and the clearest evidence that current blanket approval behavior is implementation drift.

### `the-tower-of-babel/docs/RESOURCE_MEMORY_PREFLIGHT.md`
Correctly states that reconstruction/orientation is **not permission machinery**. Missing or disputed memory lowers certainty and changes routing but does not create a global execution veto.

### `apex-cli/NON_DESTRUCTIVE_RULES.md`
Correctly states: **Fail-closed for integrity only.** Permanent delete of operator configuration/evidence requires explicit approval; ordinary work does not.

### `openclaw/OPENCLAW_CONFIG.json`
Demonstrates controlled execution with audit/rate limits while `require_human_approval_for` is empty.

### `AEON-777/BRAIN/UNIFIED_CASE_BRAIN.md`
Correctly retains human approval for actual legal consequences such as filing, service, court contact, and evidence release. This is consequence-specific rather than mutation-wide.

## What must NOT be removed

The anti-friction correction must preserve invisible safety that helps the Operator:
- exact target and scope binding;
- idempotency and duplicate-send suppression;
- source preservation and evidence integrity;
- credential isolation;
- short-lived least-privilege tokens;
- exact-SHA execution binding;
- rollback/snapshot preparation where material;
- tests and adversarial verification;
- provider-native readback;
- receipts when material to proof;
- final confirmation for genuinely irreversible/high-impact consequences.

These should happen automatically behind the interface.

## Root cause

The estate repeatedly conflated four different concepts:

```text
mutation != risk != authority != verification
```

A mutation can be low-risk and already authorized. A read can be sensitive. Verification can increase confidence without granting authority. Authority can come from the Operator's mission instruction rather than a second boolean or approval artifact.

The resulting anti-pattern is:

```text
Operator intent
  -> governance object
  -> route/pillar
  -> approval boolean / approval ID
  -> preflight
  -> receipt prerequisite
  -> gate
  -> execution
```

The intended model is:

```text
Operator intent
  -> recover relevant state
  -> system derives route + internal authority metadata
  -> execute strongest in-scope reversible work
  -> verify + read back + preserve receipts internally
  -> ask Operator only when an unresolved consequential choice truly belongs to the Operator
```

## Remediation order

1. **Fix `computer-user` authority inheritance first.** It is the execution kernel and currently turns ordinary mutation into repeated confirmation.
2. **Make APEX boot/preflight nonblocking for recoverable gaps.** Recovery/uncertainty should route work, not globally veto it.
3. **Replace blanket connector-write approvals with consequence-specific rules.** Keep idempotency/readback.
4. **Remove pillar-wide G/I approval semantics.** Keep final confirmation for filing/service/publication/external legal actions themselves.
5. **Hide dispatch metadata.** Job ID, pillar, source ref, approval object, route plan, signatures, and receipt wiring are system-owned plumbing.
6. **Relax broad PR/write ceremony in `mega-mcp`, FS Commander, Aspen, and Colossus-era policy.** Risk/reversibility controls should decide automation level.
7. **Demote universal epistemic/quality gates into evidence services.** They constrain claims, not the Operator's ability to make progress.
8. **Retire or neutralize duplicate policy engines that no longer own a live boundary.** Do not replace them with a new meta-gate.

## Success metrics

The correction is successful when:
- routine Operator requests complete with **zero secondary confirmation prompts**;
- the Operator never manually creates an approval ID, job ID, pillar, route plan, or receipt;
- verification/recovery failures trigger automatic repair/rerouting before asking the Operator;
- one Operator instruction causally authorizes its reversible implementation tranche;
- irreversible/high-impact consequences retain clear final confirmation;
- provider readback, rollback, provenance, and evidence integrity do not regress;
- the number of independent approval engines decreases rather than increases;
- user-visible time-to-action and repeated-context burden decrease.

## Final audit finding

The problem is not lack of safety. The problem is **authority inversion**: internal safety and verification mechanisms have repeatedly been allowed to demand service from the Operator.

The strongest existing GlacierEQ contracts already say the opposite. The repair therefore requires convergence back to existing Operator-first doctrine, not another architecture layer.
