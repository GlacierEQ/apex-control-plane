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
from outcome_fidelity_runtime import (
    enforce_outcome_fidelity,
    load_outcome_fidelity_policy,
)


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


def _bind_mutation(kernel) -> None:
    kernel.bind_task(
        literal_instruction="continue the live case proposition until it changes",
        target_state="the underlying proposition is proved, disproved, advanced, or genuinely externally bounded",
        operation_class="continue_case_execution",
        mode=TaskMode.MUTATION,
        action_scope="internal",
        prior_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        source_refs=("case-source:ticket-100859",),
        verification_plan=(
            "bind new source evidence to the active proposition",
            "verify that the proposition state itself changed",
            "read back the resulting case state",
        ),
    )
    kernel.record_context_recovery(
        "context-recovery:active-case",
        recovered_refs=(
            "case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            "case-source:ticket-100859",
        ),
        details={
            "prior_corrections_checked": True,
            "material_context_found": True,
            "material_context_applied": True,
            "applied_context_refs": (
                "case-proposition:ALG-NEX-641@ITEMS_MATCHED",
                "case-source:ticket-100859",
            ),
        },
    )
    kernel.begin()
    kernel.record_execution("execution:case-pass")
    kernel.record_test("test:case-pass", passed=True)
    kernel.record_adversarial_test("test:case-adversarial", passed=True)
    kernel.record_verification(
        "verification:case-pass",
        passed=True,
        verified_gain_refs=("source-proof:native-record-1",),
    )
    assert kernel.phase is RuntimePhase.VERIFIED


def test_policy_measures_progress_without_fail_closed_authority() -> None:
    policy = load_outcome_fidelity_policy()
    assert policy["fail_closed"] is False
    assert policy["required_for_mutation"] is True
    assert policy["mission_outcome_measurement_required"] is True
    assert "artifact_created" in policy["activity_only_transition_kinds"]
    assert "genuine_external_boundary" in policy["allowed_transition_kinds"]


def test_mutation_can_persist_verified_intermediate_gain_without_fake_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    state = kernel.begin_persistence()

    assert state.phase == "persisting"
    outcome = kernel.outcome_state()
    assert outcome["recorded"] is False
    assert outcome["uplift_required"] is True
    assert any("persist verified intermediate gain" in item for item in outcome["findings"])


def test_artifact_creation_is_preserved_but_not_promoted_to_mission_progress(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    snapshot = kernel.record_mission_outcome(
        "outcome:fake-artifact",
        transition_kind="artifact_created",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        after_state_ref="artifact:new-ledger",
        evidence_refs=("artifact:new-ledger",),
    )

    assert snapshot.phase == "verified"
    assert "outcome_uplift" in snapshot.receipt_kinds
    state = kernel.outcome_state()
    assert state["recorded"] is False
    assert any("activity-only gain" in item for item in state["findings"])


def test_same_before_and_after_state_drives_next_frontier_instead_of_veto(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    kernel.record_mission_outcome(
        "outcome:no-change",
        transition_kind="attributed",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        after_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        evidence_refs=("source-proof:native-record-1",),
    )

    state = kernel.outcome_state()
    assert state["recorded"] is False
    assert any("did not change mission state" in item for item in state["findings"])


def test_activity_artifacts_alone_cannot_prove_outcome_but_work_is_preserved(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    snapshot = kernel.record_mission_outcome(
        "outcome:fake-attribution",
        transition_kind="attributed",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        after_state_ref="case-proposition:ALG-NEX-641@ACTOR_ATTRIBUTED",
        evidence_refs=("ledger:actor-ledger", "matrix:attribution-matrix"),
    )

    assert snapshot.phase == "verified"
    assert kernel.outcome_state()["recorded"] is False
    assert any(
        "assistant-authored activity artifacts" in item
        for item in kernel.outcome_state()["findings"]
    )


def test_real_source_bearing_state_transition_records_mission_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    outcome = kernel.record_mission_outcome(
        "outcome:ALG-NEX-641-actor-attribution",
        transition_kind="attributed",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        after_state_ref="case-proposition:ALG-NEX-641@ACTOR_ATTRIBUTED",
        evidence_refs=(
            "provider-native:cad-1234",
            "source-proof:bwc-5678",
        ),
    )
    assert "mission_outcome" in outcome.receipt_kinds

    kernel.begin_persistence()
    kernel.record_persistence("github-commit:case-state")
    final = kernel.record_readback(
        "case-readback:ALG-NEX-641@ACTOR_ATTRIBUTED",
        matches_expected_state=True,
        target_reached=True,
    )
    assert final.phase == "complete"
    assert kernel.outcome_state()["transition_kind"] == "attributed"


def test_external_boundary_without_route_exhaustion_becomes_uplift_finding(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    kernel.record_mission_outcome(
        "outcome:external-boundary",
        transition_kind="genuine_external_boundary",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        evidence_refs=("provider-error:records-not-produced",),
        boundary_reason="native recovery inventory remains exclusively provider-held",
        routes_exhausted=False,
    )

    state = kernel.outcome_state()
    assert state["recorded"] is False
    assert any("internal routes were exhausted" in item for item in state["findings"])


def test_genuine_external_boundary_is_recorded_with_evidence(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    outcome = kernel.record_mission_outcome(
        "outcome:external-boundary",
        transition_kind="genuine_external_boundary",
        before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        evidence_refs=(
            "provider-response:no-native-recovery-inventory",
            "route-check:all-authorized-internal-sources-exhausted",
        ),
        boundary_reason="item-level recovered-property identity requires provider-native production",
        routes_exhausted=True,
    )
    assert "mission_outcome" in outcome.receipt_kinds
    assert kernel.outcome_state()["transition_kind"] == "genuine_external_boundary"


def test_intermediate_gain_is_preserved_but_cannot_complete_mutation(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    kernel.begin_persistence()
    kernel.record_persistence("github-commit:intermediate")
    final = kernel.record_readback(
        "readback:intermediate",
        matches_expected_state=True,
        target_reached=True,
    )

    assert final.phase == "repairing"
    state = kernel.outcome_state()
    assert state["recorded"] is False
    assert state["uplift_required"] is True
    assert any("next material frontier" in item for item in state["findings"])
    assert "mission_outcome_required_for_mutation_completion" in final.repair_reasons


def test_observation_tasks_are_not_forced_to_fake_progress(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    kernel.bind_task(
        literal_instruction="inspect the current runtime",
        target_state="runtime state accurately described",
        operation_class="inspect",
        mode=TaskMode.OBSERVATION,
        action_scope="none",
        source_refs=("github:runtime",),
        verification_plan=("cross-check source",),
    )
    kernel.record_context_recovery(
        "context-recovery:runtime-inspection",
        recovered_refs=("github:runtime",),
        details={
            "prior_corrections_checked": True,
            "material_context_found": True,
            "material_context_applied": True,
            "applied_context_refs": ("github:runtime",),
        },
    )
    kernel.begin()
    kernel.record_observation("github-read:runtime")
    kernel.record_verification("verification:observation", passed=True)
    final = kernel.record_readback(
        "readback:observation",
        matches_expected_state=True,
        target_reached=True,
    )
    assert final.phase == "complete"
    assert kernel.outcome_state()["recorded"] is False
    assert kernel.outcome_state()["uplift_required"] is False


def test_forward_frontier_restores_owning_mission_and_reroutes_blocker(monkeypatch) -> None:
    from mission_forward_progress import ForwardAction, ForwardReceipt, ForwardLedger

    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    ledger = ForwardLedger("mission:EXAMPLE")
    ledger.record(ForwardReceipt(
        "blocked-write", "original", "state:version-1", "BLOCKED",
        "provider-error:blocked",
    ))
    snapshot = kernel.restore_forward_frontier(
        ledger.snapshot(), expected_mission_id="mission:EXAMPLE"
    )
    assert snapshot["mission_id"] == "mission:EXAMPLE"
    next_action = kernel.select_forward_frontier((
        ForwardAction("blocked-write", "original", "state:version-1", 8, 5, authorized=True),
        ForwardAction("unresolved-review", "original", "state:version-1", 10, 9, authorized=True),
    ))
    assert next_action.action_id == "unresolved-review"
    assert "blocked-write" in next_action.suppressed

    updated = kernel.record_forward_receipt(ForwardReceipt(
        "unresolved-review", "original", "state:version-1",
        "INTERMEDIATE", "github:accepted", readback_ref="github:readback",
    ))
    assert updated["receipts"][-1]["stage"] == "INTERMEDIATE"
    assert kernel.outcome_state()["forward_frontier_attached"] is True
    assert kernel.outcome_state()["forward_human_outcomes_in_attached_journal"] == 0
    assert kernel.outcome_state()["recorded"] is False


def test_forward_frontier_rejects_wrong_mission_and_unloaded_history(monkeypatch) -> None:
    import pytest
    from mission_forward_progress import ForwardAction, ForwardLedger
    from outcome_fidelity_runtime import OutcomeFidelityViolation

    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)
    with pytest.raises(OutcomeFidelityViolation):
        kernel.select_forward_frontier((
            ForwardAction("some-work", "original", "state:v1", 5, 5, authorized=True),
        ))
    with pytest.raises(ValueError, match="mission"):
        kernel.restore_forward_frontier(
            ForwardLedger("mission:OTHER").snapshot(),
            expected_mission_id="mission:EXAMPLE",
        )
