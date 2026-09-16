from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import apex_runtime_kernel as runtime
from apex_runtime_kernel import (
    ApexRuntimeKernel,
    RuntimePhase,
    RuntimeViolation,
    TaskMode,
    create_verified_runtime_kernel,
    load_runtime_policy,
)


_GATE_GETTERS = (
    "get_in_process_notion_validation",
    "get_in_process_boot_validation",
    "get_in_process_operator_fidelity_lock",
    "get_in_process_operator_fidelity_validation",
    "get_in_process_apex_validation",
)


def _arm(monkeypatch) -> ApexRuntimeKernel:
    valid = SimpleNamespace(ok=True, status="complete")
    for getter in _GATE_GETTERS:
        monkeypatch.setattr(runtime, getter, lambda valid=valid: valid)
    return create_verified_runtime_kernel()


def _bind_mutation(kernel: ApexRuntimeKernel) -> None:
    kernel.bind_task(
        literal_instruction="build the strongest runtime",
        target_state="verified runtime kernel is committed and read back",
        operation_class="create_and_integrate_runtime",
        mode=TaskMode.MUTATION,
        action_scope="internal",
        prior_state_ref="github:existing-apex-control-plane",
        source_refs=("github:control-plane.py", "github:apex-enforced-startup.py"),
        verification_plan=(
            "run deterministic tests",
            "run adversarial transition tests",
            "read back committed files",
        ),
    )


def test_direct_constructor_is_rejected() -> None:
    with pytest.raises(TypeError, match="verified factory"):
        ApexRuntimeKernel(
            policy=load_runtime_policy(),
            startup_gates=(),
            _seal=object(),
        )


def test_factory_converts_missing_startup_observer_to_uplift(monkeypatch) -> None:
    valid = SimpleNamespace(ok=True, status="complete")
    for getter in _GATE_GETTERS:
        monkeypatch.setattr(runtime, getter, lambda valid=valid: valid)
    monkeypatch.setattr(runtime, "get_in_process_apex_validation", lambda: None)

    kernel = create_verified_runtime_kernel()

    assert kernel.phase is RuntimePhase.BOOTSTRAPPED
    assert kernel.startup_gates == runtime.EXPECTED_STARTUP_OBSERVERS
    assert any("apex_startup: validation missing" in item for item in kernel.startup_findings)


def test_routine_mutation_needs_no_separate_authorization_reference(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    assert kernel.phase is RuntimePhase.READY
    assert kernel.task.operator_authorization_ref is None


def test_destructive_mutation_retains_scoped_authority(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    with pytest.raises(RuntimeViolation, match="scoped operator authority"):
        kernel.bind_task(
            literal_instruction="delete the obsolete provider object",
            target_state="obsolete provider object removed",
            operation_class="delete_remote_object",
            mode=TaskMode.MUTATION,
            action_scope="external",
            verification_plan=("verify exact target deletion",),
        )


def test_mutation_completes_with_full_evidence_chain(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    kernel.begin()
    kernel.record_execution("github-commit:abc123")
    kernel.record_test("pytest:run-1", passed=True)
    kernel.record_adversarial_test("pytest:adversarial-1", passed=True)
    kernel.record_verification(
        "verification:run-1",
        passed=True,
        verified_gain_refs=("github-blob:runtime-kernel",),
    )
    kernel.begin_persistence()
    kernel.record_persistence("github-commit:def456")
    result = kernel.record_readback(
        "github-readback:def456",
        matches_expected_state=True,
        target_reached=True,
    )

    assert result.phase == "complete"
    assert kernel.phase is RuntimePhase.COMPLETE
    assert result.receipt_kinds == (
        "execution",
        "test",
        "adversarial_test",
        "verification",
        "persistence",
        "readback",
    )


def test_failed_test_forces_repair_and_retest(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()
    kernel.record_execution("execution:first")

    failed = kernel.record_test("pytest:first", passed=False)
    assert failed.phase == "repairing"
    assert "test_failed" in failed.repair_reasons

    with pytest.raises(RuntimeViolation, match="expected one of: adversarial_testing"):
        kernel.record_adversarial_test("pytest:illegal", passed=True)

    repaired = kernel.record_repair("patch:repair-1")
    assert repaired.phase == "testing"
    kernel.record_test("pytest:second", passed=True)
    assert kernel.phase is RuntimePhase.ADVERSARIAL_TESTING


def test_failed_adversarial_test_forces_repair(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()
    kernel.record_execution("execution:first")
    kernel.record_test("pytest:first", passed=True)

    result = kernel.record_adversarial_test("pytest:adversarial", passed=False)
    assert result.phase == "repairing"
    assert "adversarial_test_failed" in result.repair_reasons


def test_instruction_drift_is_detected_without_becoming_startup_authority(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    kernel.assert_instruction_fidelity("build the strongest runtime")
    with pytest.raises(RuntimeViolation, match="instruction drift"):
        kernel.assert_instruction_fidelity("build a weaker runtime")


def test_observation_has_separate_non_mutating_lifecycle(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    kernel.bind_task(
        literal_instruction="inspect the runtime",
        target_state="runtime state accurately described",
        operation_class="inspect",
        mode=TaskMode.OBSERVATION,
        action_scope="none",
        source_refs=("github:runtime-kernel",),
        verification_plan=("cross-check observed source",),
    )
    kernel.begin()
    kernel.record_observation("github-read:runtime-kernel")
    kernel.record_verification("verification:observation", passed=True)
    result = kernel.record_readback(
        "readback:observation",
        matches_expected_state=True,
        target_reached=True,
    )

    assert result.phase == "complete"
    assert result.receipt_kinds == ("observation", "verification", "readback")


def test_observation_verification_miss_routes_to_repair(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    kernel.bind_task(
        literal_instruction="inspect",
        target_state="truthful state",
        operation_class="inspect",
        mode=TaskMode.OBSERVATION,
        action_scope="none",
    )
    kernel.begin()
    kernel.record_observation("read:state")
    result = kernel.record_verification("verification:state", passed=False)
    assert result.phase == "repairing"
    assert "verification_failed" in result.repair_reasons


def test_missing_verified_gain_routes_to_repair_instead_of_permission_failure(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()
    kernel.record_execution("execution:first")
    kernel.record_test("pytest:first", passed=True)
    kernel.record_adversarial_test("pytest:adversarial", passed=True)

    result = kernel.record_verification("verification:first", passed=True)

    assert result.phase == "repairing"
    assert "verified_gain_reference_missing" in result.repair_reasons


def test_readback_mismatch_routes_to_repair_without_erasing_execution(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()
    kernel.record_execution("execution:first")
    kernel.record_test("pytest:first", passed=True)
    kernel.record_adversarial_test("pytest:adversarial", passed=True)
    kernel.record_verification(
        "verification:first",
        passed=True,
        verified_gain_refs=("gain:one",),
    )
    kernel.begin_persistence()
    kernel.record_persistence("persistence:first")

    result = kernel.record_readback(
        "readback:first",
        matches_expected_state=False,
        target_reached=False,
    )

    assert result.phase == "repairing"
    assert "readback_mismatch" in result.repair_reasons
    assert "execution" in result.receipt_kinds
    assert "persistence" in result.receipt_kinds


def test_concrete_provider_blocker_is_resumable_and_route_local(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()

    blocked = kernel.block(
        "provider rejected write",
        reference="provider-error:403",
    )
    assert blocked.phase == "blocked"
    assert blocked.unresolved_blockers == ("provider rejected write",)

    resumed = kernel.resolve_blocker(
        "provider rejected write",
        resolution_reference="provider-recovery:alternate-route",
    )
    assert resumed.phase == "executing"
    assert resumed.unresolved_blockers == ()


def test_verification_plan_is_auto_strengthened_when_omitted(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    kernel.bind_task(
        literal_instruction="improve the runtime",
        target_state="runtime improved and read back",
        operation_class="update_runtime",
        mode="mutation",
        action_scope="internal",
    )
    assert "read back provider or target state" in kernel.task.verification_plan


def test_audit_never_contains_literal_instruction_or_receipt_details(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    secret_phrase = "literal private operator instruction"
    kernel.bind_task(
        literal_instruction=secret_phrase,
        target_state="done",
        operation_class="mutation",
        mode="mutation",
        action_scope="internal",
        verification_plan=("verify",),
    )
    kernel.begin()
    kernel.record_execution(
        "execution:1",
        details={"private_tool_argument": "never log this payload"},
    )

    serialized = repr(kernel.audit_events())
    assert secret_phrase not in serialized
    assert "never log this payload" not in serialized
    assert kernel.snapshot().instruction_sha256 is not None
