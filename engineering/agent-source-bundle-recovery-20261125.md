# Agent source-bundle execution and recovery — 2026-11-25

Operator direction: deliver callable functions and useful outcomes, not a test-only
change. Existing APEX DirectExecutor owns durable local operations; Tasklet stays
an atomic execution primitive. This change is isolated from the Omni, memory,
legal, and continuity automation configurations.

Base: `58090da77c764bc75a401babff3cb380bf672dc2`, source blob
`a7a3e9db7ee4045b75b52f691e7029a8c26a4a7c`.
Implemented source blob: `f6694751fb6941bc6c2472dff5eb0076fe89c65e`.

## New functions

- `build_source_bundle_action`: pin explicit UTF-8 source files by SHA-256.
- `source_bundle_step`: create a deterministic source-bearing JSON artifact,
  validate its contents against the pinned inputs, and expose read-only recovery.
- `local_mission_step`: route source_bundle through the existing execute_now CLI.
- `DirectExecutor.recover_internal`: reconcile an existing durable local
  reservation using verified readback, without dispatching the effect again.
  External authorization and reconciliation remain unchanged.

## Actual execution

Isolated Linux/Python 3.13.5; provider-read source copied locally and Git blob
identity checked before patching. The original CLI blocked both source_bundle
actions. The changed CLI completed a two-operation mission over four actual
Tasklet files from `f9ec85969f54a2cdb8467097deed2175c1d6aa6c`.
A first process created the runtime bundle then exited 73 before recording its
receipt (SQLite: RESERVED, no receipt). A second process recovered that artifact
without changing its modification time, executed the independent second action,
and persisted two VERIFIED receipts. A third process replayed both with fresh
readback. All four embedded source Git blob identities matched the provider.
Existing casebook CLI also executed a local compatibility example successfully.

Artifacts (SHA-256):
- tasklet-runtime.sources.json, 30,405 bytes, two files:
  60db536dd4eeb846b120a0b122ae9b2147df87d6f8ee1ab070c11190c152a296
- tasklet-regressions.sources.json, 9,391 bytes, two files:
  da715fb4a98aa59b5e730b0a14643ab06c7e5cde607362ed1b3698ced4cfbf6d

## Continuation

The callable local function and cross-process recovery are exercised, not a claim
of automatic ChatGPT invocation or general exactly-once semantics. Full APEX
suite, provider execution, and end-to-end APEX/Spiral/Tasklet integration are
not established. Next: bind existing scheduler/continuation consumer to this
source-bearing operation and an explicitly registered useful downstream handler,
execute a recovered mission rather than just generate another report. Source
bundle recovery must not be used to bypass external authority or unknown-effect
reconciliation. No merge, deployment, credential, permission, or automation
configuration changes. No new workflow run requested.


## Objective-driven context execution and autonomous dependency continuation

Operator correction: make functions, not test-only changes; continue until
the useful work frontier is exhausted. Extended the existing DirectExecutor
and execute_now CLI instead of creating a competing orchestrator. Parent
`86e421727f280a9059afa41f07957f0a437e97f0`; executed source blob
`114c205b0420efda5befa19ae2367c3fed3e5798`.

New callable behavior:
- prepare_context_mission pins an objective and explicit source scope in a
  durable immutable manifest. Resuming the original objective loads the manifest.
- prepare_context_followup accepts a previous same-mission manifest and
  preserves pinned source hashes for a new objective.
- resolve_source_context chooses structural Python evidence for exact named
  symbols or ranked text retrieval otherwise; returns source hashes, line
  ranges, exact excerpts and explicit no-match/coverage evidence.
- python_symbol_evidence includes syntactic call candidates and callback
  argument candidates; python_dependency_trace discovers local dependencies
  using the selected definitions, including callback arguments.
- run_context_mission executes the two-stage acquisition/retrieval pipeline,
  then consumes verified results to derive further dependency objectives.
  Stable per-objective identities and a content-addressed mission source
  snapshot permit recovery, eliminate duplicate acquisition, and advance
  until no unvisited named local dependency candidate remains.
- Existing CLI --objective, --mission-id, --operation-id, --source-root and
  repeated --source-file now prepare and execute an objective directly;
  --from-manifest prepares a follow-up with no live source requirement.

Exact final source exercised in isolated Python 3.13.5. Actual input: four
Tasklet files at `f9ec85969f54a2cdb8467097deed2175c1d6aa6c`, independently matched GitHub blob identities.
Original execute_now baseline blocked context_mission. Changed implementation
automatically traversed the run_tasklet dependency frontier: 16 distinct
definition names across the three structural packets (root + two follow-ups).
Static candidate relationships are not a runtime-resolved Python call graph.

A first process created the source snapshot, the root context packet and the
first automatically selected follow-up artifact, then deliberately exited 73
before recording that follow-up receipt. SQLite showed two VERIFIED and one
RESERVED. The isolated source directory was renamed, retaining all bytes but
making the original path unavailable. A second process ran the identical CLI
command, recovered the artifact without changing its mtime, replayed the
original snapshot and root, and executed the remaining dependency query.
Two subsequent separate CLI invocations created new objectives via
--from-manifest, selected callback analysis and text retrieval respectively,
and reused the original snapshot. Six unique durable operations VERIFIED,
one source snapshot, no unresolved/unexpanded dependency names. Independently
verified all 176 source excerpts and source SHA-256/Git blob identities.
Existing casebook CLI completed its local compatibility operation. Compileall
passed. No native model/provider or full repository test run was initiated.

Evidence hashes:
- retained source snapshot: 7f22ac7eaab149371f0981ffd4df796c653b708eb8d82adbe1f581cac843c867
- execution-closure context: ae683522de7462f839b79e15c8a55ed166bfc4da694ace458c6ee125b0175d0f
- first recovered dependency packet: ad0d64048a778235df64cad22ea40a1c78dc4a59f7735196d2ac5ad06f760e57
- second dependency packet: b18f15eb05a3a13c1b15d5bdcd7f3b705e47f25c856e01e7e13e03d3cd98dc67
- callback follow-up: 1f5893c352bb375c479ee65559e10946d74dea07b827980dafc83fbca7a4c2c0
- capacity follow-up: f59c190e02255aaf2c243c571e3e26616d37b54fe88000cbf3a720520fe8a31f

Next executable transition: bind the verified context packet and actual
callable operations into the existing host's admitted session/impact
execution callbacks; select and execute a useful downstream non-retrieval
operation from recovered evidence, then verify its owning state. This local
deterministic source analysis is not an LLM, arbitrary mission planning,
automatic ChatGPT invocation, dynamic external provider execution, or
production deployment. No merge, deployment, scheduled-task configuration,
credential or permission changes. No unrelated Linear records mutated.
