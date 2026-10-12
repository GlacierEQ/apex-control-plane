# Mem capture → existing APEX continuity → native action: controlled integration slice

Status (2026-10-12 HST): **proof slice, NOT automatic runtime deployment**.

## Actual ownership

- Mem: durable, versioned capture and provider-native note identity.
- APEX: existing `continuity_ingest_and_resolve_v1` RPC, matter resolution, action receipts and mission context admission.
- TickTick: native task ID, deadline, completion status and current readback.
- Spiral: unchanged `ContinuityJournal` and `SpiralEngine.run_mission()` for authenticated mission history and independent terminal outcome checks.
- This adapter: **pure, side-effect-free translation only**. It is not a new orchestration engine, background worker or truth authority.

## Verified controlled source

- Mem note: `3a0d2c6d-b452-52fa-8fd2-e70f6123d76f` (read back at version 2)
- Raw: `Review the Mem integration test on Friday.`
- Original text SHA-256: `23837d5a3b86d879c9e45087655279815e354d3729b4fc8d521b91023265f2e0`
- Date interpretation: Friday, 2026-10-16, all-day in `Pacific/Honolulu`; no clock time supplied.
- If a bare weekday is captured on that same weekday, the due day is ambiguous and is intentionally left UNSCHEDULED rather than guessing today or next week.
- One native TickTick task: `6acd437d8f086d8c22d09b15`, Inbox `inbox125380011`
- Provider readback: active status 0, `isAllDay=true`, due date `2026-10-16T00:00:00-1000`, correlation key and source hash in native content.
- `reminders=null`; notification scheduling is not proven.
- Adapter stable semantic action key: `mem:9bcb8b267314283ce03da87fddc62c5b82731869f098dbfdeb6d734758f6f7c9`.
- The TickTick marker was added to the EXISTING task and verified; no duplicate test task created.

## Host execution contract (not implemented by this pure module)

1. Retrieve actual Mem note by exact ID; compare version, content, source provenance, sensitivity and assigned project. The caller must authenticate/verify source truth; a label is not a secret scanner.
2. `build_capture(source)` classifies conservative typed data; ambiguous dates/actions stay unscheduled until clarified.
3. `make_ingest_rpc(capture)` yields args for EXISTING APEX `continuity_ingest_and_resolve_v1`; execute only with the correct authenticated Supabase service owner.
   - APEX's `continuity_ingest_external_event_v1` has a unique `(source_system, account_key, external_id)` conflict target.
   - Accordingly `p_external_id=note_id:vN` retains different Mem versions instead of overwriting them; stable semantic `idempotency_key` permits action dedupe.
   - Ingest does not authorize an external provider mutation. An unresolved matter must not be guessed into an unrelated matter.
4. Authorized host obtains a provider-native task plan from `make_ticktick_task(capture)`. Before any create, query the owner for existing correlation marker/native ID and reconcile potential prior timeouts.
5. Execute at most once after provider-specific authorization/reservation. Persist the attempt BEFORE side effects in the original authenticated Spiral journal when available. Without an independently anchored journal and authorization, do not describe this as automatic/resumable execution.
6. Read back the exact task from TickTick by native ID. `verify_ticktick_readback(capture, response)` checks source marker/hash, due day/timezone, title and active status. An active task is NOT the terminal completed outcome.
7. Append provider IDs/status/evidence to the existing versioned Mem note via optimistic-version update, and independently read back.
8. Reconcile the APEX provider receipt and the Spiral journal; preserve ambiguities, contradictions, denied permissions and continuation cursor. Timeout after write is UNKNOWN, not FAIL or SAFE_TO_RETRY.

## Acceptance and limitations

Focused tests: `python -m pytest -q tests/test_mem_capture_action_bridge.py`.
Full APEX regression suite and live provider wiring are separate gates. Source code and a PR do not constitute a runtime deployment.

This slice does NOT claim: Mem webhooks, generic all-language extraction, automatic owner selection, fully transactional cross-provider idempotency, restricted/privileged content scanning, Supabase RPC execution, authenticated Spiral journal binding, fresh-chat cold-start integration, reminder alerts, fault-injection proof or autonomous scheduling.

Remaining frontier: provider-wired APEX ingestion; transactional outbound admission; Spiral route recovery; timeout/duplicate/conflict testing; cold-start verification with exact Mem/owner IDs; real work inventory reconciliation.
