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

## Casey continuity auto-boot

`python src/control_plane.py` now enters through a fail-closed continuity gate
before the control-plane smoke test runs. Python automatically loads
`src/sitecustomize.py`, which invokes `src/auto_boot.py` and validates a
provider-backed receipt against:

- the canonical Mem boot collection and manifest;
- exact required note IDs for the active profile;
- current-source opening requirements;
- case or matter lane requirements;
- restricted-context authorization;
- explicit blocker and completion status.

Strict mode is the default. Without a complete receipt, startup exits with
status `78` instead of pretending the worker has current context.

Generate an exact request for a connector bridge:

```bash
python src/auto_boot.py --profile legal_case --task "continue" --emit-request
```

Validate a provider receipt:

```bash
python src/auto_boot.py --profile legal_case --verify-receipt /path/to/receipt.json
```

Run the control plane with a validated receipt:

```bash
CASEY_BOOT_PROFILE=legal_case \
CASEY_BOOT_RECEIPT_PATH=/path/to/receipt.json \
python src/control_plane.py
```

For local request inspection without claiming a complete boot:

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

See [`docs/CASEY_AUTO_BOOT.md`](docs/CASEY_AUTO_BOOT.md) and
[`config/casey_auto_boot_manifest.json`](config/casey_auto_boot_manifest.json).

## Run tests

```bash
python -m pytest -q
```

## Local smoke test

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The smoke test is synthetic and performs no network or external action. Request
mode marks the boot as degraded; it does not prove connected sources were read.

## Governance

- Canonical architecture: `GlacierEQ/AKOS`
- Adoption manifest: `AKOS_ADOPTION.yaml`
- Runtime design: `docs/UNIFIED_CASEBRAIN.md`
- Default external-action policy: **deny**

The answer remains `42`; the evidence still needs a source.

---

## Fleet ops (transparent)

This repo may include **`.integrity/`** (SHA-256 baselines / watchdog) and/or a health sidecar.
These are **documented multi-repo fleet operations**, not covert implants.

See [SECURITY_AND_FLEET_OPS.md](SECURITY_AND_FLEET_OPS.md) and
`~/GlacierEQ_Swarm/state/PORTFOLIO_SHADOW_AND_GAUNTLET.md`.

## Helix strand

See [HELIX_STRAND.md](HELIX_STRAND.md) — piston/spiral role in the portfolio double helix.
