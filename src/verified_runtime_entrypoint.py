#!/usr/bin/env python3
"""Verified APEX runtime entrypoint.

The preserved `control_plane_runtime` module remains the implementation library.
This executable boundary refuses to process even the local synthetic smoke event
until it is bound to the sealed strong-boot session and that session's exact
verified runtime kernel. The smoke action then traverses the kernel's observation
lifecycle through verification and readback before output is emitted.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import sys
from typing import Any, Mapping

from apex_runtime_kernel import ApexRuntimeKernel
from apex_strong_boot import StrongBootSession, require_strong_boot
from control_plane_runtime import (
    CaseBrainOrchestrator,
    CaseEvent,
    ClaimClass,
    Producer,
    SourcePointer,
    VerificationStatus,
    canonical_json,
    canonical_sha256,
)


class RuntimeBindingViolation(RuntimeError):
    """Raised when runtime work is not bound to the verified strong-boot kernel."""


SMOKE_INSTRUCTION = "run verified local read-only control-plane smoke test"


def require_runtime_context(
    namespace: Mapping[str, Any],
) -> tuple[StrongBootSession, ApexRuntimeKernel]:
    """Resolve and validate the exact strong-boot session/kernel pair for execution."""
    process_session = require_strong_boot()
    injected_session = namespace.get("APEX_STRONG_BOOT_SESSION")
    injected_kernel = namespace.get("APEX_RUNTIME_KERNEL")

    # Direct execution of this verified boundary may use the already-established
    # process session. The control-plane wrapper supplies both objects explicitly,
    # and when supplied their identities must match exactly.
    if injected_session is None and injected_kernel is None:
        session = process_session
        kernel = process_session.runtime_kernel
    else:
        if injected_session is not process_session:
            raise RuntimeBindingViolation(
                "injected strong-boot session does not match process boot session"
            )
        if injected_kernel is not process_session.runtime_kernel:
            raise RuntimeBindingViolation(
                "injected runtime kernel does not belong to strong-boot session"
            )
        session = injected_session
        kernel = injected_kernel

    snapshot = kernel.snapshot()
    if snapshot.phase != "bootstrapped":
        raise RuntimeBindingViolation(
            f"runtime kernel must enter runtime boundary bootstrapped; got {snapshot.phase!r}"
        )
    if snapshot.task_id is not None:
        raise RuntimeBindingViolation("runtime kernel already contains a bound task")
    if snapshot.startup_gates != session.gates:
        raise RuntimeBindingViolation("runtime kernel gate proof differs from strong-boot session")
    return session, kernel


def execute_verified_local_smoke(namespace: Mapping[str, Any]) -> dict[str, Any]:
    """Run the local smoke action entirely inside the verified kernel lifecycle."""
    session, kernel = require_runtime_context(namespace)
    kernel.bind_task(
        literal_instruction=SMOKE_INSTRUCTION,
        target_state="synthetic read-only event processed, verified, and read back",
        operation_class="local_read_only_smoke_test",
        mode="observation",
        action_scope="none",
        source_refs=("runtime-source:control_plane_runtime",),
        verification_plan=(
            "process deterministic synthetic event without external action",
            "verify output is completed and externally non-authorizing",
            "read back kernel completion state",
        ),
    )
    kernel.assert_instruction_fidelity(SMOKE_INSTRUCTION)
    kernel.begin()

    try:
        result = _process_synthetic_event()
        output_sha256 = canonical_sha256(result)
        target_reached = (
            result.get("status") == "completed"
            and result.get("external_action_authorized") is False
        )
        kernel.record_observation(
            "runtime-observation:local-smoke",
            details={"output_sha256": output_sha256},
        )
        kernel.record_verification(
            "runtime-verification:local-smoke",
            passed=target_reached,
            details={
                "output_sha256": output_sha256,
                "external_action_authorized": result.get("external_action_authorized"),
            },
        )
        if not target_reached:
            raise RuntimeBindingViolation(
                "synthetic runtime smoke did not satisfy its verified target"
            )
        final_snapshot = kernel.record_readback(
            "runtime-readback:local-smoke",
            matches_expected_state=True,
            target_reached=True,
            details={"output_sha256": output_sha256},
        )
    except Exception as exc:
        if kernel.phase.value not in {"blocked", "complete"}:
            kernel.block(
                "verified local runtime smoke failed",
                reference=f"runtime-error:{type(exc).__name__}",
            )
        raise

    if final_snapshot.phase != "complete":
        raise RuntimeBindingViolation(
            f"verified runtime did not complete readback; got {final_snapshot.phase!r}"
        )

    return {
        "result": result,
        "apex_runtime": {
            "strong_boot_session_id": session.session_id,
            "runtime_id": kernel.runtime_id,
            "phase": final_snapshot.phase,
            "receipt_kinds": list(final_snapshot.receipt_kinds),
            "startup_gates": list(final_snapshot.startup_gates),
            "external_action_authorized": False,
        },
    }


def _process_synthetic_event() -> dict[str, Any]:
    source = SourcePointer(
        system="local",
        canonical_uri="file://example/court-record.pdf",
    )
    event = CaseEvent(
        event_id="example-event",
        case_id="synthetic-local-smoke",
        occurred_at=datetime.now(UTC),
        event_type="court_record_received",
        title="Example read-only ingestion",
        summary="Synthetic smoke-test event.",
        claim_class=ClaimClass.MODEL_INFERENCE,
        verification_status=VerificationStatus.PENDING_REVIEW,
        sources=(source,),
        tags=("dry_run",),
    )
    orchestrator = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha="0" * 40,
            component="verified-local-smoke-test",
        )
    )
    return orchestrator.process_event(event)


def _main(namespace: Mapping[str, Any]) -> int:
    try:
        payload = execute_verified_local_smoke(namespace)
    except Exception as exc:
        blocked = {
            "boot_status": "blocked",
            "runtime_binding_status": "blocked",
            "error": f"{type(exc).__name__}: {exc}",
            "runtime_authorized": False,
            "external_action_authorized": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 78
    print(canonical_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(globals()))
