"""Adaptive intelligence foundation for APEX.

This module adds an auditable online-learning layer for ranking context, tools,
models, routes, and candidate actions. It is deliberately provider-neutral:
external embedding, reranking, classification, or evaluator models can supply
features, while the local learner records outcome feedback and adapts ranking
weights over time.

The learner never grants project authority and never mutates external systems.
It ranks evidence/capability candidates; Operator intent and the control-plane
mutation interlocks remain controlling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


DEFAULT_WEIGHTS: dict[str, float] = {
    "semantic_relevance": 1.30,
    "task_relevance": 1.45,
    "provenance_strength": 1.60,
    "recency": 0.55,
    "continuity_value": 1.25,
    "operator_alignment": 1.75,
    "verification_strength": 1.50,
    "novel_capability": 0.65,
    "estimated_utility": 1.10,
    "contradiction_risk": -1.35,
    "correction_risk": -1.70,
    "unsupported_claim_risk": -1.80,
    "regression_risk": -1.20,
    "latency_cost": -0.25,
    "token_cost": -0.20,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


@dataclass(frozen=True)
class AdaptiveCandidate:
    """A rankable context/tool/model/action candidate.

    Feature values are normalized to [0, 1]. Unknown features are allowed and
    ignored until a weight exists for them, which permits external ML enrichers
    to add signals without breaking older runtimes.
    """

    candidate_id: str
    kind: str
    features: Mapping[str, float]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def normalized_features(self) -> dict[str, float]:
        return {name: _clamp01(value) for name, value in self.features.items()}


@dataclass(frozen=True)
class RankedCandidate:
    candidate: AdaptiveCandidate
    score: float
    raw_score: float
    contributions: Mapping[str, float]


@dataclass(frozen=True)
class FeedbackEvent:
    task_id: str
    candidate_id: str
    kind: str
    reward: float
    reason: str
    prediction_before: float
    prediction_after: float
    timestamp: str
    metadata: Mapping[str, object] = field(default_factory=dict)


class AdaptiveRanker:
    """Small transparent online learner suitable for control-plane feedback.

    The model is a logistic scorer updated with bounded stochastic gradient
    steps. It is intentionally simple enough to audit while still allowing
    real outcome-driven learning instead of frozen hand-written heuristics.
    """

    def __init__(
        self,
        weights: Mapping[str, float] | None = None,
        *,
        bias: float = 0.0,
        learning_rate: float = 0.08,
        weight_limit: float = 4.0,
    ) -> None:
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        self.bias = float(bias)
        self.learning_rate = float(learning_rate)
        self.weight_limit = abs(float(weight_limit))

    def score(self, candidate: AdaptiveCandidate) -> RankedCandidate:
        features = candidate.normalized_features()
        contributions = {
            name: self.weights[name] * features.get(name, 0.0)
            for name in self.weights
            if features.get(name, 0.0) != 0.0
        }
        raw = self.bias + sum(contributions.values())
        return RankedCandidate(
            candidate=candidate,
            score=_sigmoid(raw),
            raw_score=raw,
            contributions=contributions,
        )

    def rank(self, candidates: Iterable[AdaptiveCandidate]) -> list[RankedCandidate]:
        return sorted(
            (self.score(candidate) for candidate in candidates),
            key=lambda item: (item.score, item.raw_score, item.candidate.candidate_id),
            reverse=True,
        )

    def observe(
        self, candidate: AdaptiveCandidate, reward: float
    ) -> tuple[float, float]:
        """Learn from an observed outcome.

        ``reward`` is bounded to [-1, 1]. Positive outcomes reinforce active
        features; failures, regressions, or Operator corrections weaken them.
        Returns the predicted score before and after the update.
        """

        bounded_reward = max(-1.0, min(1.0, float(reward)))
        target = (bounded_reward + 1.0) / 2.0
        before = self.score(candidate).score
        error = target - before
        features = candidate.normalized_features()

        for name, value in features.items():
            if name not in self.weights:
                continue
            updated = self.weights[name] + self.learning_rate * error * value
            self.weights[name] = max(
                -self.weight_limit, min(self.weight_limit, updated)
            )

        self.bias = max(
            -self.weight_limit,
            min(self.weight_limit, self.bias + self.learning_rate * error),
        )
        after = self.score(candidate).score
        return before, after

    def export_state(self) -> dict[str, object]:
        return {
            "version": 1,
            "weights": dict(sorted(self.weights.items())),
            "bias": self.bias,
            "learning_rate": self.learning_rate,
            "weight_limit": self.weight_limit,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, object]) -> "AdaptiveRanker":
        return cls(
            weights={
                str(key): float(value)
                for key, value in dict(state.get("weights", {})).items()
            },
            bias=float(state.get("bias", 0.0)),
            learning_rate=float(state.get("learning_rate", 0.08)),
            weight_limit=float(state.get("weight_limit", 4.0)),
        )


SemanticEnricher = Callable[[str, str], float]


class AdaptiveIntelligenceEngine:
    """Coordinates ML-assisted ranking and auditable feedback capture."""

    def __init__(
        self,
        *,
        ranker: AdaptiveRanker | None = None,
        feedback_path: str | Path | None = None,
        semantic_enricher: SemanticEnricher | None = None,
    ) -> None:
        self.ranker = ranker or AdaptiveRanker()
        self.feedback_path = Path(feedback_path) if feedback_path else None
        self.semantic_enricher = semantic_enricher

    def enrich_semantic_score(
        self,
        *,
        query: str,
        text: str,
        candidate: AdaptiveCandidate,
    ) -> AdaptiveCandidate:
        """Attach semantic relevance from an embedding/reranker provider hook."""

        if self.semantic_enricher is None:
            return candidate
        features = dict(candidate.features)
        features["semantic_relevance"] = _clamp01(self.semantic_enricher(query, text))
        return AdaptiveCandidate(
            candidate_id=candidate.candidate_id,
            kind=candidate.kind,
            features=features,
            metadata=candidate.metadata,
        )

    def rank(self, candidates: Sequence[AdaptiveCandidate]) -> list[RankedCandidate]:
        return self.ranker.rank(candidates)

    def record_outcome(
        self,
        *,
        task_id: str,
        candidate: AdaptiveCandidate,
        reward: float,
        reason: str,
        metadata: Mapping[str, object] | None = None,
    ) -> FeedbackEvent:
        before, after = self.ranker.observe(candidate, reward)
        event = FeedbackEvent(
            task_id=task_id,
            candidate_id=candidate.candidate_id,
            kind=candidate.kind,
            reward=max(-1.0, min(1.0, float(reward))),
            reason=reason,
            prediction_before=before,
            prediction_after=after,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )
        self._append_feedback(event)
        return event

    def record_operator_correction(
        self,
        *,
        task_id: str,
        candidate: AdaptiveCandidate,
        reason: str,
        metadata: Mapping[str, object] | None = None,
    ) -> FeedbackEvent:
        return self.record_outcome(
            task_id=task_id,
            candidate=candidate,
            reward=-1.0,
            reason=f"operator_correction:{reason}",
            metadata=metadata,
        )

    def record_verified_success(
        self,
        *,
        task_id: str,
        candidate: AdaptiveCandidate,
        reason: str,
        metadata: Mapping[str, object] | None = None,
    ) -> FeedbackEvent:
        return self.record_outcome(
            task_id=task_id,
            candidate=candidate,
            reward=1.0,
            reason=f"verified_success:{reason}",
            metadata=metadata,
        )

    def save_model_state(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.ranker.export_state(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def load_model_state(path: str | Path) -> AdaptiveRanker:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        return AdaptiveRanker.from_state(state)

    def _append_feedback(self, event: FeedbackEvent) -> None:
        if self.feedback_path is None:
            return
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": event.task_id,
            "candidate_id": event.candidate_id,
            "kind": event.kind,
            "reward": event.reward,
            "reason": event.reason,
            "prediction_before": event.prediction_before,
            "prediction_after": event.prediction_after,
            "timestamp": event.timestamp,
            "metadata": dict(event.metadata),
        }
        with self.feedback_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
