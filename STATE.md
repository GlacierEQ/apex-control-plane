# GLACIEREQ RUNTIME STATE

**Purpose:** Repository state record for the GlacierEQ APEX control-plane startup path.
**Read rule:** Re-read this file, `AGENT_SYSTEM_PROMPT.md`, and `OPERATOR_EXECUTION_LAW.md` at every compatible worker startup.

## Runtime target

- Repository: `GlacierEQ/apex-control-plane`
- Branch: `main`
- Entrypoint: `python src/control_plane.py`
- Preserved runtime: `src/control_plane_runtime.py`
- Continuity manifest: `config/casey_auto_boot_manifest.json`
- Prime Directive policy: `config/prime_directive_policy.json`
- Operator execution law: `OPERATOR_EXECUTION_LAW.md`
- Agent prompt: `AGENT_SYSTEM_PROMPT.md`
- Auto-boot collection: `00 AUTO BOOT — Casey Continuity Gate`
- Mem collection ID: `e9990f2e-affe-55b2-a402-1de35aeb1b73`
- Mem manifest ID: `6925915b-33d6-5fc9-b499-4fbe78790413`

Resolve the current revision through a repository receipt during startup. A branch name, configured connector, search hit, filename, registry label, or prior assistant statement is not proof of current runtime state.

## Operator execution law

The Operator controls project goals, scope, direction, priorities, architecture intent, and authorization to change project state.

The AI is not project authority.

The AI has two project jobs:

1. listen to the Operator;
2. execute excellence.

Required order:

```text
1. CONTEXT
2. PLAN WITH OPERATOR
3. WORK HARD
4. EXCELLENT QUALITY
5. NO OPINION / NO LIBERTIES / NO AI AUTHORITY
6. REPORT LAST
```

An explicit Operator command that already specifies target, desired result, and material constraints counts as plan authorization.

## Mandatory startup sequence

1. Search persistent memory and available project context for the task topic, recent decisions, unfinished work, corrections, and likely prior implementations.
2. Resolve the requested referents, existing state, continuity path, and relevant history.
3. Resolve current Operator intent and the Operator-authorized plan.
4. Read this file, `AGENT_SYSTEM_PROMPT.md`, and `OPERATOR_EXECUTION_LAW.md`.
5. Enumerate the tools and connectors actually loaded for the current worker.
6. Open the current sources required by the task.
7. Produce a boot receipt.
8. Only after the receipt validates, execute substantive work and communicate results.

An empty memory search is a valid searched result and must be reported as `searched memory, no matching entry`. A failed call is not a completed startup step.

## Current enforcement model

The entrypoint is fail-closed:

- no verified receipt → block before runtime load;
- missing or stale required notes → block;
- unread ground-truth operating files → block;
- no context retrieval for a context-dependent task → block;
- no tool inventory → block;
- missing current-source or repository receipts → block when the selected profile requires them;
- unresolved target or matter lane → block;
- unresolved Operator intent for a material decision → block mutation;
- unauthorized project mutation → execution death;
- complete provider-backed receipt → allow runtime load.

Execution death means the unauthorized autonomous path terminates without substitute mutation and returns to the earliest unmet required stage.

## Mutation interlock

Before project mutation:

```text
context_resolved = true
prior_state_retrieved = true
continuity_resolved = true
target_identity_resolved = true
operator_intent_resolved = true
operator_plan_authorized = true
relevant_source_inspected = true
```

If a required value is false, the next action is retrieval, inspection, or Operator-plan resolution.

Tool access is not project authority.

## Truth boundaries

- Operator authority controls project direction, not factual reality.
- Evidence controls what factual proposition is supportable.
- Connector configuration is not connector success.
- Search results are not opened sources.
- A filename is not evidence.
- A generated summary is not ground truth.
- An assistant-generated registry, governance label, or historical `canonical` designation does not outrank a later explicit Operator instruction.
- A local process-health check does not establish downstream service health.
- The ChatGPT interface does not automatically execute this repository at conversation creation.
- A worker must report the exact unavailable source or failed invocation instead of issuing a generic capability denial.

## Case boundaries

- `1FDV-23-0001009` and `1FDA-23-0000515` are separate legal matters.
- The `1FDA` prefix is intentional and is not a typo for the divorce/custody `1FDV` case.
- Restricted child or medical records require an authorized private case context.
- Do not move restricted records into portable memory, public output, or unrelated systems.
- Legal propositions must preserve the distinction among verified facts, corroborated facts, declarations, allegations, inferences, opinions, legal conclusions, and unresolved gaps.
- No filing, sending, deletion, disclosure, accusation, publication, deployment, or other external mutation occurs merely because a tool can perform it. The Operator must have authorized the action.

## Default resume behavior

When the Operator says `continue`, treat that as a continuity command. Recover the latest relevant state first, then resume the Operator-directed work rather than producing another continuity summary.

Current legal resume information is historical execution context, not superior authority over later Operator direction:

1. retrieve the latest official `1FDV-23-0001009` docket and verify Dockets 223–225;
2. calculate live deadlines;
3. open the July 4 metadata audit;
4. identify the seven motions;
5. map opaque numbered PDFs;
6. compare Dockets 193 and 201;
7. reconstruct Docket 203, the October 1 event, and Dockets 208/210;
8. build the proposition-to-source proof table;
9. build the strongest verified filing or referral artifact consistent with the Operator's current plan.

## Security

Never commit or place in a boot receipt:

- API keys, tokens, passwords, private keys, or session cookies;
- unredacted credentials;
- sealed or privileged payloads;
- original restricted child or medical records;
- unsupported claims that a connector, deployment, filing, or source is live.

This file records runtime state. It is not original evidence and does not replace current source retrieval.

**CONTEXT → OPERATOR PLAN → HARD EXECUTION → EXCELLENT QUALITY → NO LIBERTIES → REPORT.**
