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
        operator_authorization_ref="operator-command:turn-current",
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


def test_factory_requires_every_in_process_gate(monkeypatch) -> None:
    valid = SimpleNamespace(ok=True, status="complete")
    for getter in _GATE_GETTERS:
        monkeypatch.setattr(runtime, getter, lambda valid=valid: valid)
    monkeypatch.setattr(runtime, "get_in_process_apex_validation", lambda: None)

    with pytest.raises(RuntimeViolation, match="apex_startup: validation missing"):
        create_verified_runtime_kernel()


def test_mutation_cannot_complete_without_full_receipt_chain(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    assert kernel.phase is RuntimePhase.READY
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


def test_instruction_drift_is_rejected(monkeypatch) -> None:
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


def test_mutation_requires_verified_gain_at_verification(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    kernel.begin()
    kernel.record_execution("execution:first")
    kernel.record_test("pytest:first", passed=True)
    kernel.record_adversarial_test("pytest:adversarial", passed=True)

    with pytest.raises(RuntimeViolation, match="verified gain"):
        kernel.record_verification("verification:first", passed=True)
    assert kernel.phase is RuntimePhase.VERIFYING


def test_blocker_is_resumable_without_false_completion(monkeypatch) -> None:
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


def test_audit_never_contains_literal_instruction_or_receipt_details(
    monkeypatch,
) -> None:
    kernel = _arm(monkeypatch)
    secret_phrase = "literal private operator instruction"
    kernel.bind_task(
        literal_instruction=secret_phrase,
        target_state="done",
        operation_class="mutation",
        mode="mutation",
        action_scope="internal",
        operator_authorization_ref="operator-command:current",
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
