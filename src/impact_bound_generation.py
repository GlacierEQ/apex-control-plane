"""Provider-neutral model host that makes impact selection causal.

A normal model call can jump directly from context to an action.  That is the
failure boundary that passive prompt rules cannot close.  This host separates a
turn into three stages:

1. propose materially distinct candidate operations;
2. evaluate their impact against the current mission/state;
3. deterministically select one candidate, bind its decision receipt, then allow
   the execution model to act.

No proposal response is directly executable.  A material state change requires a
new turn and therefore a new impact decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping, Sequence

from continuous_impact_selection import (
    ContinuousImpactSelector,
    ImpactCandidate,
    ImpactDecision,
    ImpactSelectionViolation,
)


class ImpactBoundGenerationViolation(RuntimeError):
    """Raised when a model host attempts to bypass impact-bound selection."""


ModelCall = Callable[[Sequence[Mapping[str, Any]]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ImpactBoundTurn:
    decision: ImpactDecision
    output: Mapping[str, Any]
    candidate_count: int
    state_version: str


class ImpactBoundGenerationHost:
    """Three-stage generation host with deterministic impact selection."""

    def __init__(self, selector: ContinuousImpactSelector | None = None) -> None:
        self.selector = selector or ContinuousImpactSelector()

    def run_turn(
        self,
        *,
        task_id: str,
        mission: str,
        operation_class: str,
        state_version: str,
        base_messages: Sequence[Mapping[str, Any]],
        propose: ModelCall,
        evaluate: ModelCall,
        execute: ModelCall,
        minimum_candidates: int = 2,
    ) -> ImpactBoundTurn:
        """Run one complete impact-bound model turn.

        ``propose`` and ``evaluate`` may be the same underlying model, different
        models, or deterministic host functions.  ``execute`` never sees an
        unselected proposal as authority; it receives only the selected operation
        plus the original base context.
        """
        if minimum_candidates < 1:
            raise ImpactBoundGenerationViolation("minimum_candidates must be >= 1")

        proposal_response = propose(
            [
                *base_messages,
                self._proposal_message(
                    mission=mission,
                    operation_class=operation_class,
                    minimum_candidates=minimum_candidates,
                ),
            ]
        )
        proposals = self._parse_proposals(
            proposal_response,
            operation_class=operation_class,
            minimum_candidates=minimum_candidates,
        )

        evaluation_response = evaluate(
            [
                *base_messages,
                self._evaluation_message(
                    mission=mission,
                    operation_class=operation_class,
                    state_version=state_version,
                    proposals=proposals,
                ),
            ]
        )
        candidates = self._bind_evaluations(
            proposals,
            evaluation_response,
            operation_class=operation_class,
        )

        try:
            decision = self.selector.select(
                task_id=task_id,
                mission=mission,
                operation_class=operation_class,
                state_version=state_version,
                candidates=candidates,
            )
        except ImpactSelectionViolation as exc:
            raise ImpactBoundGenerationViolation(str(exc)) from exc

        execution_messages = [
            *base_messages,
            self.selector.execution_frame(decision),
        ]
        output = execute(execution_messages)
        if not isinstance(output, Mapping):
            raise ImpactBoundGenerationViolation("execution model output must be a mapping")

        return ImpactBoundTurn(
            decision=decision,
            output=dict(output),
            candidate_count=len(candidates),
            state_version=state_version,
        )

    @staticmethod
    def _proposal_message(
        *, mission: str, operation_class: str, minimum_candidates: int
    ) -> dict[str, Any]:
        return {
            "role": "system",
            "type": "impact_candidate_generation",
            "content": (
                "Do not execute yet. Generate materially distinct candidate NEXT OPERATIONS "
                f"for the current mission while preserving operation_class={operation_class!r}. "
                f"Return JSON only with key 'candidates' containing at least {minimum_candidates} "
                "objects. Each object requires candidate_id, operation, expected_delta. "
                "Do not add governance/rules merely to restate an already-known correction. "
                f"Mission: {mission}"
            ),
        }

    @staticmethod
    def _evaluation_message(
        *,
        mission: str,
        operation_class: str,
        state_version: str,
        proposals: Sequence[Mapping[str, str]],
    ) -> dict[str, Any]:
        compact = json.dumps(proposals, ensure_ascii=False, separators=(",", ":"))
        return {
            "role": "system",
            "type": "impact_candidate_evaluation",
            "content": (
                "Evaluate the candidate operations against CURRENT mission/state. Do not choose "
                "an operation and do not execute. Return JSON only with key 'evaluations'. "
                "Each evaluation must contain candidate_id and features with numeric values 0..1. "
                "Required features: mission_advancement, state_change_value, success_impact, "
                "failure_risk, delay_cost, reversibility, second_order_value, "
                "prior_gain_preservation, execution_proximity, verification_strength, "
                "already_done_risk, meta_substitution_risk, rule_accretion_risk, "
                "rediscovery_risk, regression_risk, unsupported_claim_risk, scope_drift_risk. "
                "High risk features mean MORE risk. Evaluate impact, not rhetorical attractiveness. "
                f"operation_class={operation_class!r}; state_version={state_version!r}; "
                f"mission={mission!r}; candidates={compact}"
            ),
        }

    @staticmethod
    def _parse_proposals(
        response: Mapping[str, Any],
        *,
        operation_class: str,
        minimum_candidates: int,
    ) -> tuple[dict[str, str], ...]:
        payload = _json_payload(response)
        rows = payload.get("candidates")
        if not isinstance(rows, list) or len(rows) < minimum_candidates:
            raise ImpactBoundGenerationViolation(
                f"proposal stage requires at least {minimum_candidates} candidates"
            )
        parsed: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise ImpactBoundGenerationViolation("candidate must be an object")
            candidate_id = _text(row.get("candidate_id"), "candidate_id")
            if candidate_id in seen:
                raise ImpactBoundGenerationViolation(f"duplicate candidate_id: {candidate_id}")
            seen.add(candidate_id)
            parsed.append(
                {
                    "candidate_id": candidate_id,
                    "operation": _text(row.get("operation"), "operation"),
                    "expected_delta": _text(row.get("expected_delta"), "expected_delta"),
                    "operation_class": operation_class,
                }
            )
        return tuple(parsed)

    @staticmethod
    def _bind_evaluations(
        proposals: Sequence[Mapping[str, str]],
        response: Mapping[str, Any],
        *,
        operation_class: str,
    ) -> tuple[ImpactCandidate, ...]:
        payload = _json_payload(response)
        rows = payload.get("evaluations")
        if not isinstance(rows, list):
            raise ImpactBoundGenerationViolation("evaluation stage requires evaluations array")
        by_id: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ImpactBoundGenerationViolation("evaluation must be an object")
            candidate_id = _text(row.get("candidate_id"), "evaluation.candidate_id")
            if candidate_id in by_id:
                raise ImpactBoundGenerationViolation(
                    f"duplicate evaluation candidate_id: {candidate_id}"
                )
            by_id[candidate_id] = row

        candidates: list[ImpactCandidate] = []
        for proposal in proposals:
            candidate_id = proposal["candidate_id"]
            evaluation = by_id.get(candidate_id)
            if evaluation is None:
                raise ImpactBoundGenerationViolation(
                    f"missing impact evaluation for candidate: {candidate_id}"
                )
            features = evaluation.get("features")
            if not isinstance(features, Mapping):
                raise ImpactBoundGenerationViolation(
                    f"candidate {candidate_id} evaluation.features must be an object"
                )
            numeric: dict[str, float] = {}
            for name, value in features.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ImpactBoundGenerationViolation(
                        f"candidate {candidate_id} feature {name} must be numeric"
                    )
                numeric[str(name)] = float(value)
            candidates.append(
                ImpactCandidate(
                    candidate_id=candidate_id,
                    operation=proposal["operation"],
                    operation_class=operation_class,
                    expected_delta=proposal["expected_delta"],
                    features=numeric,
                    metadata={"impact_evaluation_bound": True},
                )
            )
        return tuple(candidates)


def _json_payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        raise ImpactBoundGenerationViolation("model response must be a mapping")
    if isinstance(response.get("json"), Mapping):
        return response["json"]
    content = response.get("content")
    if isinstance(content, Mapping):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ImpactBoundGenerationViolation("model response content is not valid JSON") from exc
        if isinstance(parsed, Mapping):
            return parsed
    raise ImpactBoundGenerationViolation(
        "model response must expose structured JSON through json or content"
    )


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImpactBoundGenerationViolation(f"{field_name} must be non-empty")
    return value.strip()
