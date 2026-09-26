from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import apex_runtime_kernel as runtime
from apex_runtime_kernel import RuntimePhase, TaskMode, create_verified_runtime_kernel
from outcome_fidelity_runtime import enforce_outcome_fidelity


_GATE_GETTERS = (
    "get_in_process_notion_validation",
    "get_in_process_boot_validation",
    "get_in_process_operator_fidelity_lock",
    "get_in_process_operator_fidelity_validation",
    "get_in_process_apex_validation",
)


def _arm(monkeypatch):
    valid = SimpleNamespace(ok=True, status="complete")
    for getter in _GATE_GETTERS:
        monkeypatch.setattr(runtime, getter, lambda valid=valid: valid)
    return enforce_outcome_fidelity(create_verified_runtime_kernel())


def _verified_mutation_without_outcome(kernel) -> None:
    kernel.bind_task(
        literal_instruction="advance the real objective",
        target_state="the external or architectural objective actually changes",
        operation_class="continue_execution",
        mode=TaskMode.MUTATION,
        action_scope="external",
        prior_state_ref="mission:before",
        source_refs=("source:operator",),
        verification_plan=("execute", "test", "read back"),
    )
    kernel.record_context_recovery(
        "context-recovery:current",
        recovered_refs=("source:operator",),
        details={
            "prior_corrections_checked": True,
            "material_context_found": True,
            "material_context_applied": True,
            "applied_context_refs": ("source:operator",),
        },
    )
    kernel.begin()
    kernel.record_execution("provider:attempt")
    kernel.record_test("test:behavior", passed=True)
    kernel.record_adversarial_test("test:no-prose-completion", passed=True)
    kernel.record_verification(
        "verification:intermediate",
        passed=True,
        verified_gain_refs=("provider:intermediate-delta",),
    )
    kernel.begin_persistence()
    kernel.record_persistence("provider:persisted-intermediate")


def test_mutation_cannot_complete_on_intermediate_gain_without_mission_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _verified_mutation_without_outcome(kernel)

    final = kernel.record_readback(
        "provider:intermediate-readback",
        matches_expected_state=True,
        target_reached=True,
    )

    assert final.phase != "complete"
    assert final.phase == "repairing"
    assert kernel.outcome_state()["recorded"] is False
    assert "mission_outcome_required_for_mutation_completion" in final.repair_reasons


def test_observation_can_still_complete_without_mutation_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    kernel.bind_task(
        literal_instruction="inspect current state",
        target_state="state accurately described",
        operation_class="inspect",
        mode=TaskMode.OBSERVATION,
        action_scope="none",
        source_refs=("provider:state",),
        verification_plan=("verify observation",),
    )
    kernel.record_context_recovery(
        "context-recovery:observation",
        recovered_refs=("provider:state",),
        details={
            "prior_corrections_checked": True,
            "material_context_found": True,
            "material_context_applied": True,
            "applied_context_refs": ("provider:state",),
        },
    )
    kernel.begin()
    kernel.record_observation("provider:state-read")
    kernel.record_verification("verification:observation", passed=True)
    final = kernel.record_readback(
        "provider:observation-readback",
        matches_expected_state=True,
        target_reached=True,
    )

    assert final.phase == "complete"
