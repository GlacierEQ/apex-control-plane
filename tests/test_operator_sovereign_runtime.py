from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from operator_sovereign_runtime import create_operator_sovereign_runtime_kernel


def test_routine_mutation_binds_without_repeat_operator_approval():
    kernel = create_operator_sovereign_runtime_kernel(observed_gates=())

    snapshot = kernel.bind_task(
        literal_instruction="Update the case workspace with the recovered evidence index.",
        target_state="case workspace contains the recovered evidence index",
        operation_class="recoverable_internal_update",
        mode="mutation",
        action_scope="internal",
        verification_plan=("read back the updated workspace",),
    )

    assert snapshot.phase == "ready"
    assert kernel.task.operator_authorization_ref is not None
    assert kernel.task.operator_authorization_ref.startswith("mission-authority:")


def test_explicit_consequence_authority_reference_is_preserved_when_supplied():
    kernel = create_operator_sovereign_runtime_kernel(observed_gates=())

    kernel.bind_task(
        literal_instruction="Perform the explicitly authorized consequence-sensitive action.",
        target_state="authorized consequence completed",
        operation_class="consequence_sensitive_action",
        mode="mutation",
        action_scope="external",
        operator_authorization_ref="operator-approval:explicit-consequence-001",
        verification_plan=("read back provider state",),
    )

    assert (
        kernel.task.operator_authorization_ref
        == "operator-approval:explicit-consequence-001"
    )


def test_runtime_policy_declares_mission_authority_not_blanket_mutation_approval():
    kernel = create_operator_sovereign_runtime_kernel(observed_gates=())
    fidelity = kernel.policy["fidelity"]
    startup = kernel.policy["startup_semantics"]

    assert fidelity["mutation_requires_operator_authorization_reference"] is False
    assert fidelity["recoverable_mutation_inherits_active_mission_authority"] is True
    assert startup["verification_is_observational"] is True
    assert startup["missing_or_stale_context_does_not_revoke_mission_authority"] is True
