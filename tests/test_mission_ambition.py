from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from continuous_impact_selection import ContinuousImpactSelector, ImpactCandidate  # noqa: E402
from mission_ambition import (  # noqa: E402
    AmbitionLevel,
    MissionAmbition,
    ambition_adjusted_features,
)


MISSION = "finish the live runtime until the system is actually operational"
OPERATION = "finish_runtime"


def test_repeated_unchanged_state_accumulates_drive() -> None:
    ambition = MissionAmbition()
    first = ambition.observe_selection(
        mission=MISSION, operation_class=OPERATION, state_version="state:blocked"
    )
    assert first.level is AmbitionLevel.STEADY

    levels = []
    for _ in range(4):
        pressure = ambition.observe_selection(
            mission=MISSION,
            operation_class=OPERATION,
            state_version="state:blocked",
        )
        levels.append(pressure.level)

    assert levels == [
        AmbitionLevel.PUSH,
        AmbitionLevel.DRIVE,
        AmbitionLevel.RELENTLESS,
        AmbitionLevel.BREAKTHROUGH,
    ]
    assert pressure.score == 1.0
    assert pressure.nonprogress_streak == 4


def test_verified_material_progress_resets_stagnation() -> None:
    ambition = MissionAmbition()
    for _ in range(3):
        ambition.observe_selection(
            mission=MISSION,
            operation_class=OPERATION,
            state_version="state:blocked",
        )

    pressure = ambition.record_outcome(
        mission=MISSION,
        operation_class=OPERATION,
        state_version="state:running",
        material_progress=True,
        reason="live kernel readback changed from blocked to running",
    )

    assert pressure.level is AmbitionLevel.STEADY
    assert pressure.nonprogress_streak == 0
    assert pressure.verified_progress_count == 1


def test_ambition_persists_across_runtime_instances(tmp_path) -> None:
    state_path = tmp_path / "ambition.json"
    first = MissionAmbition(state_path)
    first.observe_selection(
        mission=MISSION, operation_class=OPERATION, state_version="state:same"
    )
    first.observe_selection(
        mission=MISSION, operation_class=OPERATION, state_version="state:same"
    )

    second = MissionAmbition(state_path)
    pressure = second.pressure_for(mission=MISSION, operation_class=OPERATION)

    assert pressure.level is AmbitionLevel.PUSH
    assert pressure.nonprogress_streak == 1


def test_ambition_increases_direct_action_signal_and_stagnation_cost() -> None:
    ambition = MissionAmbition()
    ambition.observe_selection(
        mission=MISSION, operation_class=OPERATION, state_version="state:same"
    )
    for _ in range(4):
        pressure = ambition.observe_selection(
            mission=MISSION,
            operation_class=OPERATION,
            state_version="state:same",
        )

    direct = ambition_adjusted_features(
        {
            "mission_advancement": 0.9,
            "state_change_value": 0.9,
            "execution_proximity": 0.9,
        },
        metadata={"material_state_change": True},
        pressure=pressure,
    )
    meta = ambition_adjusted_features(
        {
            "mission_advancement": 0.2,
            "state_change_value": 0.1,
            "execution_proximity": 0.1,
            "meta_substitution_risk": 0.9,
            "rediscovery_risk": 0.9,
            "already_done_risk": 0.9,
        },
        metadata={"activity_only": True},
        pressure=pressure,
    )

    assert direct["ambition_drive"] > meta["ambition_drive"]
    assert meta["stagnation_risk"] > direct["stagnation_risk"]


def test_selector_exposes_compounding_ambition_in_execution_frame(tmp_path) -> None:
    selector = ContinuousImpactSelector(
        ambition_state_path=str(tmp_path / "ambition-state.json")
    )
    candidates = (
        ImpactCandidate(
            candidate_id="execute",
            operation="run the live integration and repair until readback changes",
            operation_class=OPERATION,
            expected_delta="runtime becomes operational",
            features={
                "mission_advancement": 0.9,
                "state_change_value": 0.9,
                "execution_proximity": 0.9,
                "success_impact": 0.8,
            },
            metadata={"material_state_change": True, "route_kind": "execution"},
        ),
        ImpactCandidate(
            candidate_id="summarize",
            operation="write another summary of why the runtime is not done",
            operation_class=OPERATION,
            expected_delta="another summary exists",
            features={
                "mission_advancement": 0.2,
                "state_change_value": 0.1,
                "execution_proximity": 0.1,
                "meta_substitution_risk": 0.8,
                "rediscovery_risk": 0.7,
            },
            metadata={"activity_only": True, "route_kind": "analysis"},
        ),
    )

    selector.select(
        task_id="ambition-1",
        mission=MISSION,
        operation_class=OPERATION,
        state_version="state:blocked",
        candidates=candidates,
    )
    decision = selector.select(
        task_id="ambition-2",
        mission=MISSION,
        operation_class=OPERATION,
        state_version="state:blocked",
        candidates=candidates,
    )

    assert decision.selected_candidate_id == "execute"
    assert decision.ambition_level == "push"
    assert decision.ambition_nonprogress_streak == 1
    frame = selector.execution_frame(decision)["content"]
    assert "Ambition: push" in frame
    assert "activity-only intermediate gain" in frame
