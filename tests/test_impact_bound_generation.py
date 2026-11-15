from pathlib import Path
import json
import sys

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from impact_bound_generation import (  # noqa: E402
    ImpactBoundGenerationHost,
    ImpactBoundGenerationViolation,
    IMPACT_FEATURE_NAMES,
)
from continuous_impact_selection import ImpactAttempt  # noqa: E402


BOUND_CLASS = "repair_runtime_selection"


def _features(value: float = 0.1, **overrides: float) -> dict[str, float]:
    row = {name: value for name in IMPACT_FEATURE_NAMES}
    row.update(overrides)
    return row


def _proposal_model(_messages):
    return {
        "content": json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "more-rules",
                        "operation": "add another copy of the same correction",
                        "expected_delta": "another passive rule exists",
                        "operation_class": BOUND_CLASS,
                    },
                    {
                        "candidate_id": "wire-selection",
                        "operation": "wire impact ranking into action selection",
                        "expected_delta": "the next operation is chosen by impact before execution",
                        "operation_class": BOUND_CLASS,
                    },
                ]
            }
        )
    }


def _evaluation_model(_messages):
    return {
        "json": {
            "evaluations": [
                {
                    "candidate_id": "more-rules",
                    "features": _features(
                        mission_advancement=0.1,
                        state_change_value=0.1,
                        success_impact=0.1,
                        failure_risk=0.2,
                        delay_cost=0.8,
                        reversibility=1.0,
                        second_order_value=0.1,
                        prior_gain_preservation=0.9,
                        execution_proximity=0.1,
                        verification_strength=0.2,
                        already_done_risk=1.0,
                        meta_substitution_risk=1.0,
                        rule_accretion_risk=1.0,
                        rediscovery_risk=0.9,
                        regression_risk=0.2,
                        unsupported_claim_risk=0.1,
                        scope_drift_risk=0.3,
                    ),
                },
                {
                    "candidate_id": "wire-selection",
                    "features": _features(
                        mission_advancement=1.0,
                        state_change_value=1.0,
                        success_impact=1.0,
                        failure_risk=0.15,
                        delay_cost=0.1,
                        reversibility=0.8,
                        second_order_value=0.9,
                        prior_gain_preservation=1.0,
                        execution_proximity=1.0,
                        verification_strength=0.9,
                        already_done_risk=0.0,
                        meta_substitution_risk=0.0,
                        rule_accretion_risk=0.0,
                        rediscovery_risk=0.0,
                        regression_risk=0.1,
                        unsupported_claim_risk=0.05,
                        scope_drift_risk=0.0,
                    ),
                },
            ]
        }
    }


def test_proposal_output_never_becomes_action_without_selection() -> None:
    host = ImpactBoundGenerationHost()
    seen_execution_messages = []

    def execute(messages):
        seen_execution_messages.extend(messages)
        return {"content": "executed selected operation"}

    turn = host.run_turn(
        task_id="impact-host",
        mission="make impact evaluation control action selection",
        operation_class=BOUND_CLASS,
        state_version="git:branch@1",
        base_messages=({"role": "user", "content": "do it"},),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )

    assert turn.decision.selected_candidate_id == "wire-selection"
    assert turn.output["content"] == "executed selected operation"
    # A response claiming execution cannot self-certify a provider side effect.
    assert turn.native_effect is None
    assert turn.native_verified is False
    frames = [
        row
        for row in seen_execution_messages
        if row.get("type") == "continuous_impact_selection"
    ]
    assert len(frames) == 1
    assert "wire impact ranking into action selection" in frames[0]["content"]
    assert "add another copy" not in frames[0]["content"]


def test_material_state_change_creates_new_decision_receipt() -> None:
    host = ImpactBoundGenerationHost()

    def execute(_messages):
        return {"content": "ok"}

    first = host.run_turn(
        task_id="impact-host",
        mission="repair selection",
        operation_class=BOUND_CLASS,
        state_version="state:before",
        base_messages=(),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )
    second = host.run_turn(
        task_id="impact-host",
        mission="repair selection",
        operation_class=BOUND_CLASS,
        state_version="state:after-tool-result",
        base_messages=(),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )
    assert first.decision.decision_sha256 != second.decision.decision_sha256
    assert first.decision.state_version != second.decision.state_version


def test_high_scoring_operation_class_drift_is_rejected_before_scoring() -> None:
    host = ImpactBoundGenerationHost()

    def propose(_messages):
        return {
            "json": {
                "candidates": [
                    {
                        "candidate_id": "drift-to-meta",
                        "operation": "stop execution and write a new governance plan",
                        "expected_delta": "another planning artifact exists",
                        "operation_class": "meta_planning",
                    },
                    {
                        "candidate_id": "valid-repair",
                        "operation": "repair the live selection boundary",
                        "expected_delta": "runtime selection is causally impact-bound",
                        "operation_class": BOUND_CLASS,
                    },
                ]
            }
        }

    def evaluate(_messages):
        return {
            "json": {
                "evaluations": [
                    {
                        "candidate_id": "drift-to-meta",
                        "features": _features(
                            mission_advancement=1.0,
                            state_change_value=1.0,
                            success_impact=1.0,
                            second_order_value=1.0,
                            prior_gain_preservation=1.0,
                            execution_proximity=1.0,
                            verification_strength=1.0,
                            reversibility=1.0,
                            failure_risk=0.0,
                            delay_cost=0.0,
                            already_done_risk=0.0,
                            meta_substitution_risk=0.0,
                            rule_accretion_risk=0.0,
                            rediscovery_risk=0.0,
                            regression_risk=0.0,
                            unsupported_claim_risk=0.0,
                            scope_drift_risk=0.0,
                        ),
                    },
                    {
                        "candidate_id": "valid-repair",
                        "features": _features(
                            mission_advancement=0.55,
                            state_change_value=0.55,
                            success_impact=0.55,
                            prior_gain_preservation=0.6,
                            execution_proximity=0.6,
                            verification_strength=0.6,
                            failure_risk=0.2,
                            delay_cost=0.2,
                        ),
                    },
                ]
            }
        }

    executed = []

    def execute(messages):
        executed.extend(messages)
        return {"content": "valid repair executed"}

    turn = host.run_turn(
        task_id="drift-rejection",
        mission="repair runtime selection",
        operation_class=BOUND_CLASS,
        state_version="state:drift-test",
        base_messages=(),
        propose=propose,
        evaluate=evaluate,
        execute=execute,
    )

    assert turn.decision.selected_candidate_id == "valid-repair"
    assert turn.decision.rejected_candidate_ids == ("drift-to-meta",)
    assert "valid repair" in turn.output["content"]
    assert not any("governance plan" in str(message) for message in executed)


def test_all_operation_class_drift_fails_before_execution() -> None:
    host = ImpactBoundGenerationHost()

    def propose(_messages):
        return {
            "json": {
                "candidates": [
                    {
                        "candidate_id": "summarize",
                        "operation": "summarize what should be repaired",
                        "expected_delta": "summary exists",
                        "operation_class": "summary",
                    },
                    {
                        "candidate_id": "plan",
                        "operation": "write a repair plan",
                        "expected_delta": "plan exists",
                        "operation_class": "planning",
                    },
                ]
            }
        }

    def evaluate(_messages):
        return {
            "json": {
                "evaluations": [
                    {"candidate_id": "summarize", "features": _features(0.9)},
                    {"candidate_id": "plan", "features": _features(0.9)},
                ]
            }
        }

    executed = []

    def execute(messages):
        executed.extend(messages)
        return {"content": "must not run"}

    with pytest.raises(
        ImpactBoundGenerationViolation,
        match="no candidate preserves the bound Operator operation class",
    ):
        host.run_turn(
            task_id="all-drift",
            mission="repair runtime selection",
            operation_class=BOUND_CLASS,
            state_version="state:all-drift",
            base_messages=(),
            propose=propose,
            evaluate=evaluate,
            execute=execute,
        )

    assert executed == []


def _native_attempt(decision, *, candidate_id=None, stage="VERIFIED_MATERIAL_DELTA"):
    return ImpactAttempt(
        mission_sha256=decision.mission_sha256,
        candidate_id=candidate_id or decision.selected_candidate_id,
        method_id="provider-dispatch-with-reservation",
        source_state_ref="github:blob:before",
        stage=stage,
        provider_ref="github:commit:after",
        after_state_ref="github:blob:after",
        readback_ref="github:readback:after",
        source_class="source_native",
    )


def test_effectful_turn_fails_preflight_without_both_native_callbacks() -> None:
    seen = []
    def never_propose(messages):
        seen.append(messages)
        return _proposal_model(messages)

    with pytest.raises(ImpactBoundGenerationViolation, match="requires native execution"):
        ImpactBoundGenerationHost().run_turn(
            task_id="real-effect", mission="change provider state",
            operation_class=BOUND_CLASS, state_version="source:before",
            base_messages=(), propose=never_propose, evaluate=_evaluation_model,
            execute=lambda _: {"content": "not allowed"},
            require_native_effect=True,
        )
    assert not seen


def test_verified_native_effect_is_proven_before_model_describes_result() -> None:
    seen = []
    calls = []
    def perform(decision):
        calls.append(("perform", decision.selected_candidate_id))
        return _native_attempt(decision)

    def verify(receipt):
        calls.append(("readback", receipt.provider_ref))
        return receipt.readback_ref == "github:readback:after"

    def execute(messages):
        calls.append(("respond", None))
        seen.extend(messages)
        return {"content": "provider delta confirmed; mission still open"}

    turn = ImpactBoundGenerationHost().run_turn(
        task_id="native-effect", mission="repair a real provider",
        operation_class=BOUND_CLASS, state_version="source:before",
        base_messages=(), propose=_proposal_model, evaluate=_evaluation_model,
        execute=execute, require_native_effect=True,
        perform_selected=perform, verify_native_readback=verify,
    )
    assert turn.decision.selected_candidate_id == "wire-selection"
    assert turn.native_verified is True
    assert turn.native_effect is not None
    assert turn.native_effect.stage == "VERIFIED_MATERIAL_DELTA"
    assert [name for name, _ in calls] == ["perform", "readback", "respond"]
    proofs = [message for message in seen if message.get("type") == "verified_native_effect"]
    assert len(proofs) == 1
    evidence = json.loads(proofs[0]["content"])
    assert evidence["provider_ref"] == "github:commit:after"
    assert evidence["mission_complete"] is False


def test_wrong_native_receipt_cannot_be_passed_to_response_model() -> None:
    called = []
    with pytest.raises(ImpactBoundGenerationViolation, match="does not match selected"):
        ImpactBoundGenerationHost().run_turn(
            task_id="wrong-native", mission="repair runtime",
            operation_class=BOUND_CLASS, state_version="source:before",
            base_messages=(), propose=_proposal_model, evaluate=_evaluation_model,
            execute=lambda _: called.append("respond") or {"content": "done"},
            require_native_effect=True,
            perform_selected=lambda decision: _native_attempt(decision, candidate_id="more-rules"),
            verify_native_readback=lambda _: called.append("readback") or True,
        )
    assert not called


def test_failed_provider_readback_cannot_generate_success_response() -> None:
    called = []
    with pytest.raises(ImpactBoundGenerationViolation, match="not independently verified"):
        ImpactBoundGenerationHost().run_turn(
            task_id="readback-failed", mission="repair runtime",
            operation_class=BOUND_CLASS, state_version="source:before",
            base_messages=(), propose=_proposal_model, evaluate=_evaluation_model,
            execute=lambda _: called.append("respond") or {"content": "done"},
            require_native_effect=True,
            perform_selected=_native_attempt,
            verify_native_readback=lambda _: False,
        )
    assert not called


def test_material_delta_cannot_be_invented_from_blocked_provider_attempt() -> None:
    with pytest.raises(ImpactBoundGenerationViolation, match="no independently verified effect"):
        ImpactBoundGenerationHost().run_turn(
            task_id="blocked-native", mission="repair runtime",
            operation_class=BOUND_CLASS, state_version="source:before",
            base_messages=(), propose=_proposal_model, evaluate=_evaluation_model,
            execute=lambda _: {"content": "done"},
            require_native_effect=True,
            perform_selected=lambda decision: _native_attempt(decision, stage="BLOCKED"),
            verify_native_readback=lambda _: True,
        )
