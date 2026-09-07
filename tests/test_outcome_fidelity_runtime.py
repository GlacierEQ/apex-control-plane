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
from apex_runtime_kernel import RuntimePhase, TaskMode, create_verified_runtime_kernel
from outcome_fidelity_runtime import (
    OutcomeFidelityViolation,
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
        operator_authorization_ref="operator-command:current",
        prior_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
        source_refs=("case-source:ticket-100859",),
        verification_plan=(
            "bind new source evidence to the active proposition",
            "verify that the proposition state itself changed",
            "read back the resulting case state",
        ),
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


def test_policy_is_fail_closed() -> None:
    policy = load_outcome_fidelity_policy()
    assert policy["fail_closed"] is True
    assert policy["required_for_mutation"] is True
    assert "artifact_created" in policy["activity_only_transition_kinds"]
    assert "genuine_external_boundary" in policy["allowed_transition_kinds"]


def test_mutation_cannot_persist_without_mission_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    with pytest.raises(OutcomeFidelityViolation, match="cannot persist"):
        kernel.begin_persistence()

    assert kernel.phase is RuntimePhase.VERIFIED


def test_artifact_creation_is_explicitly_rejected_as_progress(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    with pytest.raises(OutcomeFidelityViolation, match="assistant activity is not mission progress"):
        kernel.record_mission_outcome(
            "outcome:fake-artifact",
            transition_kind="artifact_created",
            before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            after_state_ref="artifact:new-ledger",
            evidence_refs=("artifact:new-ledger",),
        )


def test_same_before_and_after_state_is_not_progress(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    with pytest.raises(OutcomeFidelityViolation, match="mission state did not change"):
        kernel.record_mission_outcome(
            "outcome:no-change",
            transition_kind="attributed",
            before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            after_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            evidence_refs=("source-proof:native-record-1",),
        )


def test_activity_artifacts_alone_cannot_prove_outcome(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    with pytest.raises(OutcomeFidelityViolation, match="solely by assistant-authored"):
        kernel.record_mission_outcome(
            "outcome:fake-attribution",
            transition_kind="attributed",
            before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            after_state_ref="case-proposition:ALG-NEX-641@ACTOR_ATTRIBUTED",
            evidence_refs=("ledger:actor-ledger", "matrix:attribution-matrix"),
        )


def test_real_source_bearing_state_transition_allows_completion(monkeypatch) -> None:
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


def test_external_boundary_requires_route_exhaustion(monkeypatch) -> None:
    kernel = _arm(monkeypatch)
    _bind_mutation(kernel)

    with pytest.raises(OutcomeFidelityViolation, match="routes_exhausted=true"):
        kernel.record_mission_outcome(
            "outcome:external-boundary",
            transition_kind="genuine_external_boundary",
            before_state_ref="case-proposition:ALG-NEX-641@ITEMS_MATCHED",
            evidence_refs=("provider-error:records-not-produced",),
            boundary_reason="native recovery inventory remains exclusively provider-held",
            routes_exhausted=False,
        )


def test_genuine_external_boundary_is_valid_only_with_evidence(monkeypatch) -> None:
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
