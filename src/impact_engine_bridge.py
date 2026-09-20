"""Bridge APEX control-plane action selection to canonical APEX-IMPACT-ENGINE ambition.

This module does not reimplement ambition. It projects control-plane candidates
into the existing ImpactEngine so persistent no-progress pressure, route-change
requirements, and verified progress resets have one owner.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from apex_impact import (
    ActionCandidate,
    ImpactEngine,
    MissionSnapshot,
    QualityMetric,
    QualitySet,
)


DEFAULT_AMBITION_STATE = Path.home() / ".apex" / "ambition-state.json"


@dataclass(frozen=True, slots=True)
class CanonicalAmbitionDecision:
    selected_candidate_id: str | None
    ranked_candidate_ids: tuple[str, ...]
    pressure: float
    no_progress_cycles: int
    route_change_required: bool
    mission_state_ref: str

    @property
    def active(self) -> bool:
        return self.pressure > 0.0


class CanonicalAmbitionBridge:
    """Use the estate's canonical ambition engine inside APEX selection."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        configured = state_path or os.getenv("APEX_AMBITION_STATE") or DEFAULT_AMBITION_STATE
        self.state_path = Path(configured).expanduser()
        self.engine = ImpactEngine(ambition_state_path=self.state_path)

    def evaluate(
        self,
        *,
        mission_state_ref: str,
        candidates: Sequence[Any],
    ) -> CanonicalAmbitionDecision:
        state_ref = _required_text(mission_state_ref, "mission_state_ref")
        actions = tuple(self._project(candidate) for candidate in candidates)
        snapshot = MissionSnapshot(
            system_quality=_quality("system_ready", 9.5),
            result_quality=_quality("mission_progress", 5.0),
            completion_quality=_quality("completion", 5.0),
            objective_achieved=False,
            actions=actions,
            mission_state_ref=state_ref,
        )
        decision = self.engine.evaluate(snapshot)
        return CanonicalAmbitionDecision(
            selected_candidate_id=decision.selected_action,
            ranked_candidate_ids=tuple(row.action_id for row in decision.ranked_actions),
            pressure=float(decision.ambition_pressure),
            no_progress_cycles=int(decision.no_progress_cycles),
            route_change_required=bool(decision.route_change_required),
            mission_state_ref=state_ref,
        )

    def record_verified_progress(self, mission_state_ref: str) -> None:
        self.engine.record_verified_progress(
            _required_text(mission_state_ref, "mission_state_ref")
        )

    @staticmethod
    def _project(candidate: Any) -> ActionCandidate:
        features = {
            str(name): float(value)
            for name, value in dict(getattr(candidate, "features", {}) or {}).items()
        }
        metadata = dict(getattr(candidate, "metadata", {}) or {})
        state_change = _feature(features, "state_change_value")
        mission_advance = _feature(features, "mission_advancement")
        execution = _feature(features, "execution_proximity")
        second_order = _feature(features, "second_order_value")
        verification = _feature(features, "verification_strength")
        delay_cost = _feature(features, "delay_cost")

        changes_target_state = bool(
            metadata.get("material_state_change") or state_change >= 0.50
        )
        unblocks_mission = bool(
            metadata.get("unblocks_mission")
            or mission_advance >= 0.50
            or execution >= 0.70
        )
        raw_flags = metadata.get("ambition_flags", ())
        flags = tuple(str(item) for item in raw_flags) if isinstance(raw_flags, (list, tuple)) else ()
        if metadata.get("activity_only") and "support_only" not in flags:
            flags += ("support_only",)

        scores = {
            "operator_impact": mission_advance * 10.0,
            "result_power": state_change * 10.0,
            "blocker_relief": execution * 10.0,
            "readiness": execution * 10.0,
            "urgency": delay_cost * 10.0,
            "external_leverage": second_order * 10.0,
            "compounding_value": second_order * 10.0,
            "evidence_gain": verification * 10.0,
        }
        return ActionCandidate(
            action_id=_required_text(getattr(candidate, "candidate_id", ""), "candidate_id"),
            description=_required_text(getattr(candidate, "operation", ""), "candidate.operation"),
            scores=scores,
            changes_target_state=changes_target_state,
            unblocks_mission=unblocks_mission,
            flags=flags,
            executable_now=bool(metadata.get("executable_now", True)),
            boundary_reason=(
                str(metadata["boundary_reason"])
                if metadata.get("boundary_reason") is not None
                else None
            ),
        )


def ambition_alignment_features(
    candidate_id: str,
    decision: CanonicalAmbitionDecision,
) -> Mapping[str, float]:
    """Translate canonical ambition into candidate-specific ranker features."""
    pressure = max(0.0, min(1.0, decision.pressure / 10.0))
    selected = candidate_id == decision.selected_candidate_id
    return {
        "ambition_alignment": pressure if selected else 0.0,
        "ambition_route_change": (
            pressure if selected and decision.route_change_required else 0.0
        ),
    }


def _quality(name: str, score: float) -> QualitySet:
    return QualitySet(
        (
            QualityMetric(
                name,
                score,
                required=True,
                evidence=(f"apex-control-plane:{name}",),
            ),
        )
    )


def _feature(features: Mapping[str, float], name: str) -> float:
    return max(0.0, min(1.0, float(features.get(name, 0.0))))


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    return value.strip()
