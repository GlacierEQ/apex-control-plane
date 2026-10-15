# APEX Session Admission Gateway — Host Integration Contract

**Owner:** `GlacierEQ/apex-control-plane` (`main`)  
**Source:** `src/chat_context_admission.py`, `src/apex_session_gateway.py`,
`src/apex_session_gateway_store.py`

## Enforcement boundary

An APEX-controlled **host must call** `run_admitted_session()` around **every
model invocation**. This controls the APEX-hosted execution path only. It does
not install a native ChatGPT startup hook, intercept ChatGPT account memory,
or override OpenAI's internal memory consolidation.

The tested lifecycle is:

```text
host independently identifies current mission
  -> open authenticated Spiral journal, verify current head/cursor
  -> APEX recovering kernel + source-matched ContextApplication
  -> transactional durable reservation, before model callback
  -> model receives the admitted recovery receipt
  -> reject unsupported source attribution and memory classification
  -> persist response as ASSISTANT-AUTHORED
  -> persist proposals as SOURCE_CANDIDATE_ONLY
  -> independent SQLite readback and digest check
  -> response can be returned
```

A provider model may produce incorrect free-form prose despite these controls.
The `corrections_applied` field is a model-reported claim, **not independent
semantic proof** that the model interpreted every correction correctly.
The gateway enforces provenance of structured assertions and quarantines memory
candidates; it does not certify the truth of arbitrary free-form model text.

## Concrete host wiring

Host supplies original source bytes from a separately authenticated store
(`resolve_source`); the returned `OriginRecord.speaker` must reflect
provider-original authorship, **not a model-derived guess**.

```python
from src.apex_session_gateway import run_admitted_session
from src.apex_session_gateway_store import GatewayCheckpointStore

# Caller must independently select the mission from the current user intent,
# authenticate the original Spiral journal, and create the APEX recovering kernel.
store = GatewayCheckpointStore(
    "/owner-private/apex/model-continuations.sqlite",
    mission_id=expected_mission_id,
)
output = run_admitted_session(
    journal=authenticated_spiral_journal,
    chat_session_id=host_supplied_session_id,
    kernel=apex_kernel_in_context_recovering_phase,
    expected_mission_id=expected_mission_id,
    invocation_id=host_supplied_turn_id,
    apply_context=host_source_matched_application,   # -> ContextApplication
    invoke_model=host_actual_model_invocation,        # -> GatewayModelOutput
    resolve_source=authenticated_original_source_readback,  # -> OriginRecord
    reserve=store.reserve,
    persist=store.persist,
    readback=store.readback,
)
```

The above placeholders are obligations of the **real host**, not automatically
resolved by GitHub code. The host must avoid sending messages before
`run_admitted_session` returns successfully. A host that invokes its model
outside this gateway bypasses enforcement.

## Memory rule

`MemoryProposal` is **not** a persisted instruction, profile fact, or accepted
memory. An exact user quote — including a negated correction — does not give
a model authority to relabel the quote as the opposite user instruction.
The gateway refuses direct model classification into `user_instruction`,
`user_fact`, or `user_preference`. Any adoption must travel a **separate,
independently authenticated user-authority route**. The durable record explicitly
marks `response_author=assistant` and
`memory_authority=SOURCE_CANDIDATE_ONLY`.

Original messages and correction source spans stay in the owning original
store. SQLite copies are only the execution proof lane, not the new source
of truth or a global cross-platform memory service.

## Security / deployment

- SQLite file and parent must be owner-private; symlinks are refused.
- All participating workers must share **the same** durable database path.
- Distributed workers require a shared transactional provider; distinct local
  SQLite copies do **not** provide cross-machine idempotency.
- Failed/ambiguous attempts retain their reservation and require provider
  reconciliation; do not silently rerun a possibly effectful model callback.
- An authenticated journal, independent source resolver and host invocation
  are non-optional; test fixtures or a model assertion cannot stand in for them.
- No real OpenAI API call, production host, native ChatGPT startup event or
  ChatGPT memory-consolidation interception has been demonstrated by CI.

## Verification and remaining acceptance condition

`.github/workflows/connector-mission-admission.yml` compiles the gateway and
executes `tests.test_apex_session_gateway` plus
`tests.test_apex_session_gateway_store`, alongside prior admission suites.

As of 2026-10-15, Actions run
[38722354181](https://github.com/GlacierEQ/apex-control-plane/actions/runs/38722354181)
passed 54 tests, including cross-process SQLite readback, identical-session
replay denial, concurrent reservation, and source-authority regressions.
This verifies **repository behavior**, not automatic native ChatGPT integration.

**To establish permanent native enforcement:** provider-level ability to
intercept/require APEX on every new ChatGPT session must be proven, followed by
fresh native sessions with independently observed APEX invocation and memory
outcomes. Until then, label **NATIVE_BOOT_UNVERIFIED** and
**NATIVE_MEMORY_CONTROL_UNVERIFIED**, while preserving the verified
APEX-controlled runtime capabilities.
