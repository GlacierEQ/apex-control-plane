# Casey Continuity Auto-Boot

The APEX control plane has a deterministic, fail-closed continuity gate. It is
designed for ephemeral workers that cannot safely assume they remember a prior
chat, case run, repository decision, deadline, or source state.

## Canonical automatic startup

Running:

```bash
python src/control_plane.py
```

executes the small wrapper at `src/control_plane.py`. The wrapper calls
`automatic_boot()` **before** it loads the preserved implementation in
`src/control_plane_runtime.py`.

Without a valid provider-backed receipt, strict mode emits a deterministic JSON
boot request to stderr and exits with status `78`. The runtime does not load and
the synthetic smoke test does not execute.

`src/sitecustomize.py` is only a secondary hook for environments where `src` is
already on `PYTHONPATH`, or when another entrypoint is explicitly forced with
`CASEY_AUTO_BOOT=1`. The canonical startup command does not depend on automatic
site discovery.

## Modes

### Strict — default

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

A complete receipt is mandatory. Missing notes, wrong note versions, malformed
source receipts, incorrect case/matter lane, missing repository proof, missing
deadline-check state, stale manifest identity, or explicit blockers stop
startup.

### Request

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The wrapper prints a deterministic JSON boot request and continues with
`CASEY_BOOT_STATUS=degraded`. This is for local inspection and connector-bridge
development. It is not a claim of current case or repository awareness.

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

The manifest pins every required Mem note to an exact version. A later or older
note version blocks startup until the manifest is deliberately reconciled.

## Request generation

A connector bridge can request the exact boot workload without starting the
control plane:

```bash
python src/auto_boot.py \
  --profile legal_case \
  --task "continue the highest-value unfinished 1FDV artifact" \
  --emit-request
```

The request identifies exact Mem note IDs and versions, collection and manifest
identity, profiles, current task, and required receipt fields.

## Receipt requirements

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

The verifier checks:

- exact boot-manifest ID and version;
- exact Mem collection ID;
- every required note ID and pinned version;
- structured `sources_opened` rows with `system`, `object_id`, and a `version`
  key;
- structured repository receipts for the systems profile;
- `case_lane` for legal-case work;
- `matter_lane` for separate matters;
- a deadline check marked `verified` with sources or `not_relevant` with a
  reason;
- boolean `restricted_context`, including `true` for restricted-child work;
- non-empty `current_task` and `next_material_action`;
- `boot_status=complete` and an empty array of blockers.

Search hits, filenames, connector configuration, inherited summaries, empty
objects, and unversioned note claims do not satisfy the contract.

## Validate a receipt without starting the runtime

```bash
python src/auto_boot.py \
  --profile legal_case \
  --verify-receipt /secure/runtime/boot-receipt.json
```

Success exits `0`. A failed gate exits `78` and reports every missing, malformed,
or incompatible requirement.

## Optional forced hook

For another Python entrypoint already using `src` on `PYTHONPATH`:

```bash
PYTHONPATH=src \
CASEY_AUTO_BOOT=1 \
CASEY_AUTO_BOOT_MODE=request \
python another_entrypoint.py
```

The optional hook skips the verifier CLI and pytest. The explicit
`src/control_plane.py` wrapper remains the primary enforcement path.

## Security boundaries

The repository contains only note identifiers, pinned versions, collection
identifiers, profile rules, and receipt schemas. It contains no API keys,
tokens, passwords, private keys, restricted child records, medical source
payloads, or sealed material.

The `restricted_child` profile requires explicit authorization and remains
excluded from portable memory and unrelated projections.

## What this integration proves

It proves that the APEX control-plane Python entrypoint cannot load its runtime
as fully booted without a receipt satisfying the checked contract.

It does **not** prove that the ChatGPT UI automatically executes this repository
at the start of every conversation. For ChatGPT conversations, the dedicated
Mem collection and canonical manifest are the connected-source boot target; the
repository supplies executable enforcement wherever the APEX entrypoint runs.
