from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from continuous_impact_selection import (  # noqa: E402
    ContinuousImpactSelector,
    ImpactCandidate,
    ImpactSelectionViolation,
)


def _candidate(
    candidate_id: str,
    operation: str,
    expected_delta: str,
    *,
    operation_class: str = "repair_runtime_selection",
    **features: float,
) -> ImpactCandidate:
    return ImpactCandidate(
        candidate_id=candidate_id,
        operation=operation,
        operation_class=operation_class,
        expected_delta=expected_delta,
        features=features,
        evidence_refs=(f"test:{candidate_id}",),
    )


def test_live_runtime_repair_beats_another_rule_copy() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "rule-copy",
            "add another impact rule beside existing prompts",
            "another passive instruction exists",
            mission_advancement=0.15,
            state_change_value=0.10,
            success_impact=0.15,
            execution_proximity=0.10,
            prior_gain_preservation=0.80,
            reversibility=0.95,
            already_done_risk=1.0,
            meta_substitution_risk=0.95,
            rule_accretion_risk=1.0,
            rediscovery_risk=0.90,
        ),
        _candidate(
            "wire-ranker",
            "wire adaptive impact ranking into the live action-selection path",
            "candidate actions are compared by impact before execution",
            mission_advancement=1.0,
            state_change_value=0.95,
            success_impact=0.95,
            execution_proximity=0.90,
            prior_gain_preservation=1.0,
            reversibility=0.80,
            failure_risk=0.20,
            meta_substitution_risk=0.05,
            rule_accretion_risk=0.05,
            rediscovery_risk=0.05,
        ),
    )

    decision = selector.select(
        task_id="selection-defect",
        mission="make impact evaluation causally control the next operation",
        operation_class="repair_runtime_selection",
        state_version="git:main@before",
        candidates=candidates,
    )

    assert decision.selected_candidate_id == "wire-ranker"
    assert decision.ranked_candidate_ids[0] == "wire-ranker"
    assert decision.decision_sha256
    frame = selector.execution_frame(decision)
    assert frame["role"] == "system"
    assert "wire adaptive impact ranking" in frame["content"]
    assert "Re-evaluate after any material state change" in frame["content"]


def test_reweight_after_material_state_change_can_change_next_action() -> None:
    selector = ContinuousImpactSelector()
    first = (
        _candidate(
            "inspect-host",
            "trace the live model host integration boundary",
            "the actual inference caller is identified",
            mission_advancement=0.95,
            state_change_value=0.70,
            execution_proximity=0.75,
            success_impact=0.85,
            already_done_risk=0.0,
        ),
        _candidate(
            "patch-host",
            "patch the model host now",
            "the model host enforces impact selection",
            mission_advancement=0.70,
            state_change_value=0.95,
            execution_proximity=0.90,
            success_impact=0.95,
            failure_risk=0.85,
            unsupported_claim_risk=0.75,
        ),
    )
    first_decision = selector.select(
        task_id="dynamic",
        mission="repair the live selection path",
        operation_class="repair_runtime_selection",
        state_version="state:unknown-host",
        candidates=first,
    )
    assert first_decision.selected_candidate_id == "inspect-host"

    second = (
        _candidate(
            "inspect-host",
            "trace the live model host integration boundary",
            "the actual inference caller is identified again",
            mission_advancement=0.15,
            state_change_value=0.05,
            execution_proximity=0.10,
            success_impact=0.10,
            already_done_risk=1.0,
            rediscovery_risk=1.0,
        ),
        _candidate(
            "patch-host",
            "patch the verified model host with impact-bound generation",
            "every generated action passes impact selection before execution",
            mission_advancement=1.0,
            state_change_value=1.0,
            execution_proximity=1.0,
            success_impact=1.0,
            prior_gain_preservation=1.0,
            failure_risk=0.15,
            unsupported_claim_risk=0.05,
        ),
    )
    second_decision = selector.select(
        task_id="dynamic",
        mission="repair the live selection path",
        operation_class="repair_runtime_selection",
        state_version="state:verified-host",
        candidates=second,
    )
    assert second_decision.selected_candidate_id == "patch-host"
    assert second_decision.state_version != first_decision.state_version
    assert second_decision.decision_sha256 != first_decision.decision_sha256
    assert len(selector.history()) == 2


def test_operation_class_rewrite_is_rejected_before_scoring() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "meta",
            "write a new governance architecture",
            "a new architecture document exists",
            operation_class="design_governance",
            mission_advancement=1.0,
            state_change_value=1.0,
        ),
        _candidate(
            "repair",
            "repair the runtime selection path",
            "selection behavior changes",
            mission_advancement=0.8,
            state_change_value=0.8,
        ),
    )
    decision = selector.select(
        task_id="op-class",
        mission="repair runtime selection",
        operation_class="repair_runtime_selection",
        state_version="state:1",
        candidates=candidates,
    )
    assert decision.selected_candidate_id == "repair"
    assert decision.rejected_candidate_ids == ("meta",)


def test_all_operation_class_rewrites_fail_closed() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "wrong",
            "summarize the defect",
            "summary exists",
            operation_class="summarize",
            mission_advancement=1.0,
        ),
    )
    try:
        selector.select(
            task_id="fail",
            mission="repair runtime selection",
            operation_class="repair_runtime_selection",
            state_version="state:1",
            candidates=candidates,
        )
    except ImpactSelectionViolation as exc:
        assert "no candidate preserves" in str(exc)
    else:
        raise AssertionError("operation-class rewrite must fail closed")
