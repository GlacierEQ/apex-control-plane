from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from continuous_impact_selection import ContinuousImpactSelector, ImpactCandidate  # noqa: E402
from prosecution_pressure import (  # noqa: E402
    ProsecutionLevel,
    ProsecutionSignal,
    assess_prosecution_pressure,
    pressure_adjusted_features,
)


def _candidate(
    candidate_id: str,
    *,
    route_kind: str,
    mission_advancement: float = 0.55,
    state_change_value: float = 0.55,
    execution_proximity: float = 0.55,
    unsupported_claim_risk: float = 0.05,
) -> ImpactCandidate:
    return ImpactCandidate(
        candidate_id=candidate_id,
        operation=f"run {route_kind} route",
        operation_class="advance_case",
        expected_delta=f"{route_kind} route changes target state",
        features={
            "mission_advancement": mission_advancement,
            "state_change_value": state_change_value,
            "success_impact": 0.55,
            "failure_risk": 0.10,
            "delay_cost": 0.10,
            "reversibility": 0.70,
            "second_order_value": 0.50,
            "prior_gain_preservation": 0.80,
            "execution_proximity": execution_proximity,
            "verification_strength": 0.80,
            "already_done_risk": 0.05,
            "meta_substitution_risk": 0.05,
            "rule_accretion_risk": 0.05,
            "rediscovery_risk": 0.05,
            "regression_risk": 0.05,
            "unsupported_claim_risk": unsupported_claim_risk,
            "scope_drift_risk": 0.05,
        },
        metadata={"route_kind": route_kind},
    )


def test_no_stagnation_means_normal_pressure() -> None:
    pressure = assess_prosecution_pressure(ProsecutionSignal())
    assert pressure.level is ProsecutionLevel.NORMAL
    assert pressure.score == 0.0
    assert pressure.prosecution_eligible is False


def test_operator_directive_activates_prosecution_only_with_supported_evidence() -> None:
    supported = assess_prosecution_pressure(
        ProsecutionSignal(
            operator_escalation_directive=True,
            supported_accountability_route=True,
            evidence_strength=0.80,
        )
    )
    assert supported.level is ProsecutionLevel.PROSECUTION
    assert supported.prosecution_eligible is True

    unsupported = assess_prosecution_pressure(
        ProsecutionSignal(
            operator_escalation_directive=True,
            supported_accountability_route=False,
            evidence_strength=0.90,
        )
    )
    assert unsupported.level is ProsecutionLevel.PRESSURE
    assert unsupported.prosecution_eligible is False


def test_repeated_nonprogress_raises_prosecution_pressure() -> None:
    pressure = assess_prosecution_pressure(
        ProsecutionSignal(
            consecutive_nonprogress=2,
            supported_accountability_route=True,
            evidence_strength=0.70,
        )
    )
    assert pressure.level is ProsecutionLevel.PROSECUTION
    assert "nonprogress:2" in pressure.reasons


def test_missed_receipt_plus_deadline_can_trigger_supported_prosecution() -> None:
    pressure = assess_prosecution_pressure(
        ProsecutionSignal(
            receipt_missing=True,
            deadline_breached=True,
            supported_accountability_route=True,
            evidence_strength=0.75,
        )
    )
    assert pressure.level is ProsecutionLevel.PROSECUTION
    assert {"receipt_missing", "deadline_breached"} <= set(pressure.reasons)


def test_pressure_penalizes_more_analysis_and_rewards_consequence_route() -> None:
    pressure = assess_prosecution_pressure(
        ProsecutionSignal(
            consecutive_nonprogress=2,
            supported_accountability_route=True,
            evidence_strength=0.80,
        )
    )
    base = {
        "mission_advancement": 0.5,
        "state_change_value": 0.5,
        "execution_proximity": 0.5,
        "delay_cost": 0.1,
        "meta_substitution_risk": 0.1,
        "rediscovery_risk": 0.1,
        "success_impact": 0.5,
        "second_order_value": 0.5,
    }
    analysis = pressure_adjusted_features(
        base,
        metadata={"route_kind": "analysis"},
        pressure=pressure,
    )
    enforcement = pressure_adjusted_features(
        base,
        metadata={"route_kind": "enforcement"},
        pressure=pressure,
    )
    assert analysis["delay_cost"] > base["delay_cost"]
    assert analysis["meta_substitution_risk"] > base["meta_substitution_risk"]
    assert enforcement["mission_advancement"] > base["mission_advancement"]
    assert enforcement["execution_proximity"] > base["execution_proximity"]


def test_selector_changes_route_when_supported_prosecution_pressure_is_active() -> None:
    selector = ContinuousImpactSelector()
    pressure = assess_prosecution_pressure(
        ProsecutionSignal(
            consecutive_nonprogress=3,
            receipt_missing=True,
            supported_accountability_route=True,
            evidence_strength=0.82,
        )
    )
    candidates = (
        _candidate(
            "analysis",
            route_kind="analysis",
            mission_advancement=0.70,
            state_change_value=0.60,
            execution_proximity=0.40,
        ),
        _candidate(
            "enforcement",
            route_kind="enforcement",
            mission_advancement=0.58,
            state_change_value=0.60,
            execution_proximity=0.60,
        ),
    )
    decision = selector.select(
        task_id="pressure-route",
        mission="advance the case instead of repeating analysis",
        operation_class="advance_case",
        state_version="state:stalled",
        candidates=candidates,
        pressure=pressure,
    )
    assert decision.selected_candidate_id == "enforcement"
    assert decision.pressure_level == "prosecution"
    assert decision.prosecution_eligible is True
    assert decision.pressure_score > 0.0


def test_weak_evidence_never_turns_prosecution_into_supported_route() -> None:
    pressure = assess_prosecution_pressure(
        ProsecutionSignal(
            consecutive_nonprogress=4,
            operator_escalation_directive=True,
            supported_accountability_route=True,
            evidence_strength=0.30,
        )
    )
    assert pressure.level is ProsecutionLevel.PRESSURE
    assert pressure.prosecution_eligible is False

    adjusted = pressure_adjusted_features(
        {"failure_risk": 0.1, "unsupported_claim_risk": 0.1},
        metadata={"route_kind": "prosecution"},
        pressure=pressure,
    )
    assert adjusted["unsupported_claim_risk"] == 0.1
