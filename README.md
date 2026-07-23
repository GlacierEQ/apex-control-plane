# apex-control-plane

**Portfolio runtime:** capacity-aware worker dispatch plus the bounded Unified CASEBRAIN control plane.

## What changed

The original worker registry remains backward compatible. The runtime now adds:

- immutable SHA-256 transport envelopes and idempotency keys;
- explicit separation of facts, allegations, inferences, and recommendations;
- deterministic timeline/deadline projections;
- analytical threat signals with required alternative explanations;
- recommendation generation with hard human-review and external-action denial;
- connector retries, circuit breakers, dead-letter capture, and audit receipts;
- AKOS adoption metadata and secret-reference-only configuration.

## Run tests

```bash
python -m pytest -q
```

## Local smoke test

```bash
python src/control_plane.py
```

The smoke test is synthetic and performs no network or external action.

## Governance

- Canonical architecture: `GlacierEQ/AKOS`
- Adoption manifest: `AKOS_ADOPTION.yaml`
- Runtime design: `docs/UNIFIED_CASEBRAIN.md`
- Default external-action policy: **deny**

The answer remains `42`; the evidence still needs a source.
