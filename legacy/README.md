# Legacy archive — historical evidence, not active runtime doctrine

This directory preserves source-bearing historical implementations for lineage, forensic comparison, regression archaeology, and recovery of uniquely useful mechanisms.

It is **not** an authority source for current APEX execution semantics.

## Mandatory interpretation

- Historical `gate`, `approval`, `permit`, `fail_closed`, `blocked`, `hard_lock`, `exit 78`, or equivalent language in this directory describes the archived implementation that existed at that point in lineage.
- Those historical semantics must not be imported, copied, generated into active code, or treated as current policy merely because they are present in the repository.
- Active runtime behavior is defined by current non-legacy source, current policy, current tests/CI, provider constraints, and current Operator direction.
- Preserve this archive rather than rewriting it to look current. Its historical bytes are evidence of prior system behavior.
- When mining the archive for useful capability, transplant only the beneficial mechanism and bind it to current execution semantics. Do not rehydrate obsolete generalized permission authority.

## Current execution invariant

```text
CAPABILITY
  -> EXECUTE KNOWN PERMITTED FRONTIERS
  -> HARDEN / TEST / VERIFY
  -> REPAIR / REROUTE AFFECTED FRONTIERS
  -> PRESERVE VERIFIED GAIN
  -> COMPLETE
  -> RECEIPT / READBACK
```

Recoverable uncertainty is repair work, not a blanket stop condition. Concrete provider, credential, hardware, legal, destructive-action, irreversible-action, and unrecoverable runtime-integrity constraints remain scoped to the route that actually carries them.
