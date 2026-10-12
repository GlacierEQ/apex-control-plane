# ChatGPT authenticated Spiral context bridge

This is an **explicit, source-bound invocation surface** over the pre-existing APEX
`src/spiral_live_journal.py` and the original GlacierEQ Spiral
`ContinuityJournal`. It does not create a global ChatGPT message interceptor.

## Source authority and security

- One exact `mission-id` selects one immutable mission identity; an unrelated chat is not silently attached.
- `init` is separate from `recover`; recovery never creates missing journals.
- The journal is HMAC-authenticated with a random locally generated key stored in an owner-only file.
- The independently stored expected head detects changed, truncated and rolled-back journals.
- A mission-specific file lock serializes writes and their expected-head advancement.
- Missing, insecure or symlinked state fails closed. The credential is never emitted on stdout.
- Actual APEX action admission must occur *after* recovered corrections, provider facts and the exact cursor change the chosen action. `recover` alone does not attest application.

## Local operation

Use Python 3.12+; `SPIRAL_ROOT` must be an independently verified checkout of
`GlacierEQ/spiral-engine` (tested against
`ef0d9cd80cf987acc0a864a553d72cec8fe1b9cd`).
Choose an owner-private durable `STORE` outside any Git checkout.

```bash
BRIDGE=scripts/chatgpt_context_bridge.py
STORE="$HOME/.local/share/glaciereq/spiral-session-bridge"
SPIRAL_ROOT="/path/to/trusted/spiral-engine"
MISSION="glaciereq-chatgpt-context-enforcement"

# Only once, with the operator's exact objective and outcome:
python3 "$BRIDGE" --store "$STORE" --spiral-root "$SPIRAL_ROOT" --mission-id "$MISSION" \
  init --objective "Recover and apply mission context across ChatGPT sessions" \
  --outcome "TWO_REAL_SESSIONS_VERIFIED"

# Independent new chat session, read-only:
python3 "$BRIDGE" --store "$STORE" --spiral-root "$SPIRAL_ROOT" --mission-id "$MISSION" \
  recover --session-id "actual-chat-session-id"
```

Use `fact --key K --value V --source PROVIDER_NATIVE_RECEIPT`,
`correct --instruction TEXT`, or `checkpoint --cursor CURSOR` only when
the source and mutation have been verified. Each append advances the independent
head and is read back through the original authenticated adapter.

## Proof and unresolved boundary

`.github/workflows/spiral-real-journal.yml` exercises the pinned upstream,
the original cross-process APEX gate and this bridge's tests. It validates
cross-process identity, facts/corrections, expected head, rollback detection,
duplicate-init protection, permissions, and concurrent updates.

**Not proven by these tests:** native ChatGPT automatic invocation, a real
ChatGPT/iOS conversation identifier passed by the host, or operator-authenticated
case/legal provider retrieval. These need a supported ChatGPT host/client trigger
and a two-genuine-chat acceptance test. No generated CLI, extension, plugin
skill, passing CI, or assistant statement can replace that evidence.

Do not save private case material or access keys in GitHub or publicly visible
test fixtures.
