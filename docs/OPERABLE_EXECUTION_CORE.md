# Operable execution core — independent running path

**Objective:** Execute an authorized operation, inspect the owning target, recover failures, and persist only truthful state. Legacy APEX startup gates are not imported.

## Execute now

From the repository root (Python 3.11+, no third-party packages):

    python scripts/operate_direct.py --state .local/operations.sqlite submit-file --id first-run --path .local/results/hello.txt --content operating

This runs immediately, reads the written file back, and returns `verified: true` only if the target exactly matches. Repeating the same id/payload does not perform the effect again. Use `--queue-only` to submit without dispatch.

To resume or inspect an operation:

    python scripts/operate_direct.py --state .local/operations.sqlite run --id first-run
    python scripts/operate_direct.py --state .local/operations.sqlite status --id first-run

The state database contains request inputs; keep it private and outside version control, in a directory accessible only to the authorized host. File effects are restricted to the trusted current working directory by default. Use `--root /trusted/workspace` to explicitly choose a different permitted workspace. Paths outside that root and symbolic-link escapes are rejected.

## Connect real providers

The core accepts registered provider adapters. Implement `execute(payload, operation_id)` to call a real authenticated provider action and `verify(payload)` to independently read its current state. Return `True` if the desired effect is observed, `False` if absent, or `None` if the provider is inconclusive. The adapter's `idempotent` field identifies whether replay after confirmed absence is safe. Use the stable operation ID as the provider idempotency key whenever supported.

Example integration, where provider_write and provider_read are existing authenticated host operations:

    class NativeConnector:
        idempotent = True

        def execute(self, payload, operation_id):
            return provider_write(payload, idempotency_key=operation_id)

        def verify(self, payload):
            state = provider_read(payload["target_id"])
            return state == payload["desired_state"]  # None when unavailable

    with OperationalCore(".local/operations.sqlite", {"provider": NativeConnector()}) as core:
        core.submit("stable-unique-effect", "provider", request)
        result = core.run("stable-unique-effect")
        print(result.as_dict())

The host—not this library—establishes authenticated connector identity and the operator's intended scope. Do not populate adapter operations from untrusted documents. No credentials are embedded in this repository.

## Live GitHub adapter

The implementation now includes `src/provider_github.py` and `scripts/operate_github.py`. It uses GitHub's actual Contents API with a host-supplied `GITHUB_TOKEN`, reads the target before writes to avoid unnecessary commits, writes to the explicitly chosen branch/path, and independently re-reads the target before returning verified. No token is persisted in the operation journal.

From an authorized host with a scoped GitHub token:

    GITHUB_TOKEN=<host_secret> python scripts/operate_github.py --state .local/github.sqlite --id unique-change-001 --repo GlacierEQ/apex-control-plane --branch main --path proof/result.txt --content-file ./desired-content.txt

The example path is illustrative; select the actual intended target. This script does not ask for another approval after the host has authenticated and authorized the requested effect. The adapter tests use an in-process HTTP double; a deployed authenticated GitHub write/readback is a separate evidence requirement.

## Recovery instead of gate accumulation

States: `queued -> running -> verified`. When readback shows a missing effect, an idempotent operation becomes `retryable`; when readback is unknown it becomes `uncertain` and is checked before any later retry. Non-idempotent ambiguous operations become `needs_reconciliation`, not blind duplicates. Active leases prevent competing invocations; expired leases trigger source-state readback before replay. SQLite state survives process restarts.

This engine reports verified provider effects, not human-world mission outcomes. External mail, legal actions, financial transfers, and other consequential actions still depend on their owning providers' native authorization and confirmation.

## Evidence and migration

Run `python -m unittest discover -s tests -p 'test_operational_core.py' -v`. Tests cover actual file effects, simulated connector callbacks, response loss after a successful effect, retries, lease recovery, no duplicates, restart, and a real CLI subprocess. **The simulated adapter tests do not prove any production connector is already wired.**

A usable deployment requires connecting one live provider adapter, performing an authorized action through it, verifying source-native readback, then migrating further work. Re-running a previously verified operation re-checks current target state and repairs an idempotent effect if it has drifted. Preserve prior mission data and evidence while replacing the nonoperational execution path. Do not mistake a green repository test, a coordination record, or a connector health check for a running cross-connector service.
