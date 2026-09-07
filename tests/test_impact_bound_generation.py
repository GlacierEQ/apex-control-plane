from pathlib import Path
import json
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from impact_bound_generation import ImpactBoundGenerationHost  # noqa: E402


def _proposal_model(_messages):
    return {
        "content": json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "more-rules",
                        "operation": "add another copy of the same correction",
                        "expected_delta": "another passive rule exists",
                    },
                    {
                        "candidate_id": "wire-selection",
                        "operation": "wire impact ranking into action selection",
                        "expected_delta": "the next operation is chosen by impact before execution",
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
                    "features": {
                        "mission_advancement": 0.1,
                        "state_change_value": 0.1,
                        "success_impact": 0.1,
                        "failure_risk": 0.2,
                        "delay_cost": 0.8,
                        "reversibility": 1.0,
                        "second_order_value": 0.1,
                        "prior_gain_preservation": 0.9,
                        "execution_proximity": 0.1,
                        "verification_strength": 0.2,
                        "already_done_risk": 1.0,
                        "meta_substitution_risk": 1.0,
                        "rule_accretion_risk": 1.0,
                        "rediscovery_risk": 0.9,
                        "regression_risk": 0.2,
                        "unsupported_claim_risk": 0.1,
                        "scope_drift_risk": 0.3,
                    },
                },
                {
                    "candidate_id": "wire-selection",
                    "features": {
                        "mission_advancement": 1.0,
                        "state_change_value": 1.0,
                        "success_impact": 1.0,
                        "failure_risk": 0.15,
                        "delay_cost": 0.1,
                        "reversibility": 0.8,
                        "second_order_value": 0.9,
                        "prior_gain_preservation": 1.0,
                        "execution_proximity": 1.0,
                        "verification_strength": 0.9,
                        "already_done_risk": 0.0,
                        "meta_substitution_risk": 0.0,
                        "rule_accretion_risk": 0.0,
                        "rediscovery_risk": 0.0,
                        "regression_risk": 0.1,
                        "unsupported_claim_risk": 0.05,
                        "scope_drift_risk": 0.0,
                    },
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
        operation_class="repair_runtime_selection",
        state_version="git:branch@1",
        base_messages=({"role": "user", "content": "do it"},),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )

    assert turn.decision.selected_candidate_id == "wire-selection"
    assert turn.output["content"] == "executed selected operation"
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
        operation_class="repair_runtime_selection",
        state_version="state:before",
        base_messages=(),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )
    second = host.run_turn(
        task_id="impact-host",
        mission="repair selection",
        operation_class="repair_runtime_selection",
        state_version="state:after-tool-result",
        base_messages=(),
        propose=_proposal_model,
        evaluate=_evaluation_model,
        execute=execute,
    )
    assert first.decision.decision_sha256 != second.decision.decision_sha256
    assert first.decision.state_version != second.decision.state_version
