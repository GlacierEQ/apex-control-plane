"""Continuous impact evaluation for APEX action selection.

This module turns the Operator's long-standing "evaluate everything / understand
impact" working method into an executable selection function instead of another
passive rule.  It composes with ``adaptive_intelligence`` and is provider-neutral:
model hosts, tool routers, workers, and task runners can all submit candidate
operations and receive one inspectable selection.

The selector does not grant authority.  The bound Operator operation class remains
controlling.  Candidates that rewrite that operation are rejected before scoring.
The important distinction is causal: a candidate must be selected through impact
comparison before it is eligible to become the next operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from adaptive_intelligence import (
    AdaptiveCandidate,
    AdaptiveIntelligenceEngine,
    AdaptiveRanker,
    DEFAULT_WEIGHTS,
    RankedCandidate,
)


class ImpactSelectionViolation(RuntimeError):
    """Raised when action selection bypasses impact-aware comparison."""


IMPACT_WEIGHTS: dict[str, float] = {
    # Positive mission effects.
    "mission_advancement": 2.40,
    "state_change_value": 2.20,
    "success_impact": 1.60,
    "second_order_value": 1.10,
    "prior_gain_preservation": 1.70,
    "execution_proximity": 1.55,
    "reversibility": 0.80,
    # Negative impact / known failure attractors.
    "failure_risk": -1.45,
    "delay_cost": -0.80,
    "already_done_risk": -2.75,
    "meta_substitution_risk": -2.90,
    "rule_accretion_risk": -2.25,
    "rediscovery_risk": -2.70,
    "scope_drift_risk": -2.40,
}


@dataclass(frozen=True, slots=True)
class ImpactCandidate:
    """One possible next operation and its current impact model.

    ``features`` are normalized to [0, 1] by the adaptive ranker.  They may be
    produced by deterministic host logic, a dedicated evaluator model, measured
    runtime state, or a composition of those sources.  The selector never treats
    these features as source facts; they are decision inputs.
    """

    candidate_id: str
    operation: str
    operation_class: str
    expected_delta: str
    features: Mapping[str, float]
    evidence_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ImpactDecision:
    task_id: str
    mission_sha256: str
    operation_class: str
    state_version: str
    selected_candidate_id: str
    selected_operation: str
    selected_expected_delta: str
    score: float
    contributions: Mapping[str, float]
    ranked_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    decision_sha256: str


class ContinuousImpactSelector:
    """Select the strongest current operation by mission impact.

    The selector is intentionally re-entrant.  A host should call ``select`` again
    whenever a material tool result, source update, verification result, failure,
    correction, or target-state change alters the situation.  Re-evaluation
    replaces the prior decision for execution purposes; it does not erase history.
    """

    def __init__(self, engine: AdaptiveIntelligenceEngine | None = None) -> None:
        if engine is None:
            weights = dict(DEFAULT_WEIGHTS)
            weights.update(IMPACT_WEIGHTS)
            engine = AdaptiveIntelligenceEngine(ranker=AdaptiveRanker(weights=weights))
        self.engine = engine
        self._history: list[ImpactDecision] = []

    def select(
        self,
        *,
        task_id: str,
        mission: str,
        operation_class: str,
        state_version: str,
        candidates: Sequence[ImpactCandidate],
    ) -> ImpactDecision:
        task = _required_text(task_id, "task_id")
        mission_text = _required_text(mission, "mission")
        bound_operation = _required_text(operation_class, "operation_class")
        version = _required_text(state_version, "state_version")
        if not candidates:
            raise ImpactSelectionViolation("at least one candidate operation is required")

        seen: set[str] = set()
        eligible: list[ImpactCandidate] = []
        rejected: list[str] = []
        for candidate in candidates:
            candidate_id = _required_text(candidate.candidate_id, "candidate_id")
            if candidate_id in seen:
                raise ImpactSelectionViolation(f"duplicate candidate_id: {candidate_id}")
            seen.add(candidate_id)
            _required_text(candidate.operation, "candidate.operation")
            _required_text(candidate.expected_delta, "candidate.expected_delta")
            candidate_class = _required_text(
                candidate.operation_class, "candidate.operation_class"
            )
            if candidate_class != bound_operation:
                rejected.append(candidate_id)
                continue
            eligible.append(candidate)

        if not eligible:
            raise ImpactSelectionViolation(
                "no candidate preserves the bound Operator operation class"
            )

        adaptive_candidates = [self._to_adaptive(candidate) for candidate in eligible]
        ranking = self.engine.rank(adaptive_candidates)
        if not ranking:
            raise ImpactSelectionViolation("impact ranker returned no eligible candidate")

        selected_rank = ranking[0]
        selected = _candidate_by_id(eligible, selected_rank.candidate.candidate_id)
        decision_payload = {
            "task_id": task,
            "mission_sha256": _digest(mission_text),
            "operation_class": bound_operation,
            "state_version": version,
            "selected_candidate_id": selected.candidate_id,
            "selected_operation": selected.operation,
            "selected_expected_delta": selected.expected_delta,
            "score": selected_rank.score,
            "contributions": dict(sorted(selected_rank.contributions.items())),
            "ranked_candidate_ids": [row.candidate.candidate_id for row in ranking],
            "rejected_candidate_ids": rejected,
            "evidence_refs": list(selected.evidence_refs),
        }
        decision = ImpactDecision(
            task_id=task,
            mission_sha256=decision_payload["mission_sha256"],
            operation_class=bound_operation,
            state_version=version,
            selected_candidate_id=selected.candidate_id,
            selected_operation=selected.operation,
            selected_expected_delta=selected.expected_delta,
            score=selected_rank.score,
            contributions=decision_payload["contributions"],
            ranked_candidate_ids=tuple(decision_payload["ranked_candidate_ids"]),
            rejected_candidate_ids=tuple(rejected),
            evidence_refs=tuple(selected.evidence_refs),
            decision_sha256=_digest(_canonical_json(decision_payload)),
        )
        self._history.append(decision)
        return decision

    def record_verified_outcome(
        self,
        *,
        decision: ImpactDecision,
        candidates: Sequence[ImpactCandidate],
        success: bool,
        reason: str,
    ) -> None:
        """Feed verified outcome back into the adaptive ranker."""
        selected = _candidate_by_id(candidates, decision.selected_candidate_id)
        adaptive = self._to_adaptive(selected)
        self.engine.record_outcome(
            task_id=decision.task_id,
            candidate=adaptive,
            reward=1.0 if success else -1.0,
            reason=_required_text(reason, "reason"),
            metadata={
                "decision_sha256": decision.decision_sha256,
                "state_version": decision.state_version,
            },
        )

    def history(self) -> tuple[ImpactDecision, ...]:
        return tuple(self._history)

    @staticmethod
    def execution_frame(decision: ImpactDecision) -> dict[str, Any]:
        """Return a compact pre-action frame suitable for a system/developer turn.

        The frame is deliberately small.  It carries the selected operation and
        the reason it won without replaying the entire rule estate into context.
        """
        return {
            "role": "system",
            "type": "continuous_impact_selection",
            "content": (
                "CONTINUOUS IMPACT SELECTION IS BOUND FOR THIS STEP. "
                f"Operation class: {decision.operation_class}. "
                f"Selected operation: {decision.selected_operation}. "
                f"Expected mission delta: {decision.selected_expected_delta}. "
                "Execute this selected operation; do not replace it with planning, "
                "rediscovery, rule creation, or another meta-operation. Re-evaluate "
                "after any material state change. "
                f"Decision receipt: {decision.decision_sha256}."
            ),
        }

    def _to_adaptive(self, candidate: ImpactCandidate) -> AdaptiveCandidate:
        features = {str(name): float(value) for name, value in candidate.features.items()}
        # These are hard semantic facts of an eligible candidate, not model scores.
        features["task_relevance"] = max(features.get("task_relevance", 0.0), 1.0)
        features["operator_alignment"] = max(
            features.get("operator_alignment", 0.0), 1.0
        )
        return AdaptiveCandidate(
            candidate_id=candidate.candidate_id,
            kind="action",
            features=features,
            metadata={
                "operation": candidate.operation,
                "expected_delta_sha256": _digest(candidate.expected_delta),
                **dict(candidate.metadata),
            },
        )


def _candidate_by_id(
    candidates: Sequence[ImpactCandidate], candidate_id: str
) -> ImpactCandidate:
    for candidate in candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise ImpactSelectionViolation(f"candidate not found: {candidate_id}")


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImpactSelectionViolation(f"{field_name} must be non-empty")
    return value.strip()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
