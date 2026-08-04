# Casey Continuity Auto-Boot

The APEX control plane now has a deterministic, fail-closed continuity gate.
It is designed for ephemeral workers that cannot safely assume they remember a
prior chat, case run, repository decision, or source state.

## Automatic startup

Running:

```bash
python src/control_plane.py
```

causes Python to import `src/sitecustomize.py` before the control-plane module.
The hook invokes `src/auto_boot.py` and requires a provider-backed boot receipt.
Without a valid receipt, strict mode exits with status `78` before the synthetic
control-plane smoke test runs.

The gate is narrow. It runs automatically for `control_plane.py`, skips pytest
and the boot verifier itself, and can be forced for another Python entrypoint:

```bash
CASEY_AUTO_BOOT=1 python another_entrypoint.py
```

## Modes

### Strict — default

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

A complete receipt is mandatory. Missing notes, missing current sources,
incorrect case/matter lane, stale manifest version, or explicit blockers stop
startup.

### Request

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The hook prints a deterministic JSON boot request to stderr and continues with
`CASEY_BOOT_STATUS=degraded`. This is for local inspection and bridge
development, not for claiming current case awareness.

### Off

```bash
CASEY_AUTO_BOOT_MODE=off python src/control_plane.py
```

or:

```bash
CASEY_AUTO_BOOT_DISABLE=1 python src/control_plane.py
```

Disabling the gate must be explicit. A disabled run cannot claim that connected
continuity or current sources were loaded.

## Boot profiles

Set profiles with a comma-separated environment variable:

```bash
CASEY_BOOT_PROFILE=legal_case python src/control_plane.py
CASEY_BOOT_PROFILE=systems python src/control_plane.py
CASEY_BOOT_PROFILE=legal_case,restricted_child \
CASEY_RESTRICTED_CONTEXT_AUTHORIZED=1 \
python src/control_plane.py
```

`always` is inserted automatically. Available profiles are:

- `always`
- `legal_case`
- `restricted_child`
- `systems`
- `separate_matter`

The machine-readable profile definitions are in
`config/casey_auto_boot_manifest.json`. The canonical human-readable source is
Mem note `6925915b-33d6-5fc9-b499-4fbe78790413` in collection
`e9990f2e-affe-55b2-a402-1de35aeb1b73`.

## Request generation

A connector bridge can request the exact boot workload without starting the
control plane:

```bash
python src/auto_boot.py \
  --profile legal_case \
  --task "continue the highest-value unfinished 1FDV artifact" \
  --emit-request
```

The request identifies the exact Mem note IDs, collection ID, manifest ID,
profile, task, and required receipt fields.

## Receipt delivery

Supply a receipt as either inline JSON or a file path, never both:

```bash
CASEY_BOOT_RECEIPT_PATH=/secure/runtime/boot-receipt.json \
CASEY_BOOT_PROFILE=legal_case \
python src/control_plane.py
```

or:

```bash
CASEY_BOOT_RECEIPT_JSON='{"boot_status":"complete", ...}' \
CASEY_BOOT_PROFILE=legal_case \
python src/control_plane.py
```

The receipt must prove that exact notes were fetched by ID and that current
sources required by the selected profile were opened. Search hits, filenames,
connector configuration, and inherited summaries do not satisfy the contract.

## Validate a receipt without starting the runtime

```bash
python src/auto_boot.py \
  --profile legal_case \
  --verify-receipt /secure/runtime/boot-receipt.json
```

Success exits `0`. A failed gate exits `78` and reports every missing or stale
requirement.

## Security boundaries

The repository contains only note identifiers, collection identifiers, profile
rules, and receipt schemas. It contains no API keys, tokens, passwords, private
keys, restricted child records, medical source payloads, or sealed material.

The `restricted_child` profile requires explicit authorization and remains
excluded from portable memory and unrelated projections.

## What this integration proves

It proves that the local APEX Python runtime will not silently proceed as fully
booted without a receipt satisfying the checked contract.

It does **not** prove that ChatGPT itself automatically runs this repository at
the start of every UI conversation. For ChatGPT conversations, the Mem
collection and canonical manifest provide the connected-source boot target;
the runtime hook provides the executable enforcement path wherever this APEX
entrypoint is used.
