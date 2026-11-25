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
