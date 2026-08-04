# GLACIEREQ RUNTIME STATE

**Authority:** Repository ground truth for the GlacierEQ APEX control-plane startup path.  
**Read rule:** Re-read this file at every agent or worker startup. Chat context is not a durable source of current system state.

## Canonical runtime

- Repository: `GlacierEQ/apex-control-plane`
- Canonical branch: `main`
- Entrypoint: `python src/control_plane.py`
- Preserved runtime: `src/control_plane_runtime.py`
- Continuity manifest: `config/casey_auto_boot_manifest.json`
- Prime Directive policy: `config/prime_directive_policy.json`
- Agent prompt: `AGENT_SYSTEM_PROMPT.md`
- Auto-boot collection: `00 AUTO BOOT — Casey Continuity Gate`
- Mem collection ID: `e9990f2e-affe-55b2-a402-1de35aeb1b73`
- Canonical Mem manifest ID: `6925915b-33d6-5fc9-b499-4fbe78790413`

Resolve the current `main` revision through a repository receipt during startup. A branch name, configured connector, search hit, filename, or prior assistant statement is not proof of current runtime state.

## Mandatory startup sequence

1. Search persistent memory for the task topic, user/project context, recent decisions, and unfinished work.
2. Read this file and `AGENT_SYSTEM_PROMPT.md` from the active repository or case folder.
3. Enumerate the tools and connectors actually loaded for the current worker.
4. Open the current sources required by the task.
5. Produce a boot receipt.
6. Only after the receipt validates, plan, execute, and communicate.

An empty memory search is a valid searched result and must be reported as `searched memory, no matching entry`. A failed call is not a completed startup step.

## Current enforcement model

The canonical entrypoint is fail-closed:

- no verified receipt → block before runtime load;
- missing or stale required notes → block;
- unread ground-truth files → block;
- no tool inventory → block;
- missing current-source or repository receipts → block when the selected profile requires them;
- wrong case or matter lane → block;
- unresolved blockers → block;
- complete provider-backed receipt → allow runtime load.

The response middleware separately prevents an LLM from emitting conversational text before the startup stages have completed. Tool calls may pass through; tool-call success must be recorded before the gate advances.

## Truth boundaries

- Connector configuration is not connector success.
- Search results are not opened sources.
- A filename is not evidence.
- A generated summary is not ground truth.
- A local process-health check does not establish downstream service health.
- The ChatGPT interface does not automatically execute this repository at conversation creation.
- A worker must report the exact unavailable source or failed invocation instead of issuing a generic capability denial.

## Case boundaries

- `1FDV-23-0001009` and `1FDA-23-0000515` are separate legal matters.
- The `1FDA` prefix is intentional: it identifies the domestic-abuse/TRO/OFP track and is not a typo for the divorce/custody `1FDV` case.
- Restricted child or medical records require an authorized private case context.
- Do not move restricted records into portable memory, public output, or unrelated systems.
- Legal propositions must preserve the distinction among verified facts, corroborated facts, declarations, allegations, inferences, opinions, legal conclusions, and unresolved gaps.
- No autonomous filing, sending, deletion, disclosure, accusation, or external mutation without authority.

## Default resume behavior

When Casey says `continue`, resume the highest-value unfinished material action after startup, rather than producing another continuity summary.

Current default legal resume chain:

1. retrieve the latest official `1FDV-23-0001009` docket and verify Dockets 223–225;
2. calculate live deadlines;
3. open the July 4 metadata audit;
4. identify the seven motions;
5. map opaque numbered PDFs;
6. compare Dockets 193 and 201;
7. reconstruct Docket 203, the October 1 event, and Dockets 208/210;
8. build the proposition-to-source proof table;
9. build the strongest verified filing or referral artifact.

## Security

Never commit or place in a boot receipt:

- API keys, tokens, passwords, private keys, or session cookies;
- unredacted credentials;
- sealed or privileged payloads;
- original restricted child or medical records;
- unsupported claims that a connector, deployment, filing, or source is live.

This file governs runtime state. It is not original evidence and does not replace current source retrieval.
