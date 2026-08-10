# APEX Control Plane — Central Orchestration & Gateway Control 🏛️


The repository contains local control-plane and audit mechanisms for:

- immutable SHA-256 transport envelopes and idempotency keys;
- explicit separation of facts, allegations, inferences, and recommendations;
- deterministic timeline/deadline projections;
- analytical threat signals with required alternative explanations;
- recommendation generation with hard human-review and external-action denial;
- connector retries, circuit breakers, dead-letter capture, and audit receipts;
- repository census/registry checks;
- strict continuity boot requests and provider-receipt validation;
- AKOS adoption metadata and secret-reference-only configuration.

These are repository-local mechanisms. This public surface does **not** establish live access to private case records, connected Mem/provider data, production external systems, or autonomous external action.

## Continuity auto-boot

`python src/control_plane.py` is an explicit fail-closed wrapper. It runs
`src/auto_boot.py` **before** loading the preserved runtime in
`src/control_plane_runtime.py`.

The boot verifier checks configured requirements such as:

- the canonical boot collection and manifest;
- required note IDs and versions;
- structured current-source receipts;
- repository revision receipts for systems work;
- lane/profile state;
- deadline-check status when a profile requires it;
- restricted-context authorization and state;
- current task and next material action;
- blocker type, blocker contents, and final boot status.

Strict mode is the default. Without a complete provider-backed receipt, startup
emits a deterministic boot request and exits with status `78` instead of
pretending current provider context was loaded.

Generate a connector request:

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

The profile name above is an interface example. **No case-specific evidence or private legal record is part of this README's public capability claim.**

For local request inspection without claiming a complete boot:

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

`src/sitecustomize.py` remains an optional secondary hook when `src` is already
on `PYTHONPATH` or another entrypoint is explicitly forced with
`CASEY_AUTO_BOOT=1`. The canonical command does not depend on that hook.

See [`docs/CASEY_AUTO_BOOT.md`](docs/CASEY_AUTO_BOOT.md) and
[`config/casey_auto_boot_manifest.json`](config/casey_auto_boot_manifest.json).

## Native proof

The repository CI exercises the registry and audit-hardening surfaces on the exact source head for pull requests and pushes:

```bash
python -m pytest -q tests/test_scan_repos.py
python -m pytest -q tests/test_audit_hardening.py
```

CI also runs Ruff, format checks, mypy for the registry scanner, and the repository security workflow. A successful workflow is evidence only for the exact Git head it executed.

## Local smoke test

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The smoke test is synthetic and performs no network or external action. Request
mode marks the boot as degraded; it does not prove connected sources were read.

## Governance

- Canonical architecture reference: `GlacierEQ/AKOS`
- Adoption manifest: `AKOS_ADOPTION.yaml`
- Runtime design: `docs/UNIFIED_CASEBRAIN.md`
- Default external-action policy: **deny**

The answer remains `42`; the evidence still needs a source.
=======
[![Python](https://img.shields.io/badge/Python-3.9+-blue)]()
[![SQL](https://img.shields.io/badge/SQL-PostgreSQL-blue)]()
[![Domain](https://img.shields.io/badge/Domain-Control%20Plane-purple)]()
>>>>>>> 608d541 (chore: Hyper Excellence Activation & structural matrix alignment)

## Fleet operations boundary

## 🎯 For Recruiters & Hiring Managers

This repository implements the **APEX Control Plane** — the central orchestrator that coordinates routing, state storage, and inter-agent communication across the swarm. It demonstrates:

- **Centralized RPC routing** and service discovery for micro-agents
- **PostgreSQL relational storage** for transactional integrity
- **Cluster state management** tracking active nodes, jobs, and worker health
- **Restful & WebSocket gateways** for unified client control

**Why this matters**: Every distributed system requires a resilient control plane to manage state transitions, worker registration, and task distribution without single-point-of-failure bottlenecks.

---

## 🔬 For Engineers & Technical Reviewers

### Core Components

| Component | Language | Purpose |
|---|---|---|
| `src/control_plane.py` | Python | Gateway server, state reconciliation loop, RPC hub |
| `migrations/` | SQL | PostgreSQL schema DDLs for cluster metadata |
| `tests/` | Python | Control plane integration test suite |

---

## 🤖 ML/AI & Programmatic Mesh Integration

- **MCP Tool**: `query_control_plane()` — status inspection for AI swarm agents
- **Mastermind Sidecar**: Direct integration with APEX Highway mesh telemetry
- **SHA-256 Integrity**: Tracked via `.integrity/file_hashes.json`

---

## ⚡ Quick Start

```bash
python3 src/control_plane.py
python3 tests/test_control_plane.py
```
