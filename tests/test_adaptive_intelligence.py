from __future__ import annotations

import json

from src.adaptive_intelligence import (
    AdaptiveCandidate,
    AdaptiveIntelligenceEngine,
    AdaptiveRanker,
)


def _candidate(candidate_id: str, **features: float) -> AdaptiveCandidate:
    return AdaptiveCandidate(candidate_id=candidate_id, kind="context", features=features)


def test_rank_prefers_provenance_alignment_and_verification() -> None:
    engine = AdaptiveIntelligenceEngine()
    strong = _candidate(
        "strong",
        semantic_relevance=0.80,
        task_relevance=0.90,
        provenance_strength=1.0,
        operator_alignment=1.0,
        verification_strength=0.95,
        unsupported_claim_risk=0.05,
    )
    weak = _candidate(
        "weak",
        semantic_relevance=0.90,
        task_relevance=0.80,
        provenance_strength=0.20,
        operator_alignment=0.60,
        verification_strength=0.10,
        unsupported_claim_risk=0.90,
    )

    ranked = engine.rank([weak, strong])

    assert ranked[0].candidate.candidate_id == "strong"
    assert ranked[0].score > ranked[1].score
    assert ranked[0].contributions["provenance_strength"] > 0


def test_verified_success_increases_prediction() -> None:
    ranker = AdaptiveRanker(learning_rate=0.25)
    engine = AdaptiveIntelligenceEngine(ranker=ranker)
    candidate = _candidate(
        "route-github",
        task_relevance=0.9,
        operator_alignment=1.0,
        verification_strength=0.7,
    )

    event = engine.record_verified_success(
        task_id="task-1",
        candidate=candidate,
        reason="repository source opened and resulting state verified",
    )

    assert event.prediction_after > event.prediction_before


def test_operator_correction_decreases_prediction() -> None:
    ranker = AdaptiveRanker(learning_rate=0.25)
    engine = AdaptiveIntelligenceEngine(ranker=ranker)
    candidate = _candidate(
        "mvp-narrowing-route",
        task_relevance=0.8,
        operator_alignment=0.3,
        regression_risk=0.8,
        correction_risk=0.9,
    )

    event = engine.record_operator_correction(
        task_id="task-2",
        candidate=candidate,
        reason="narrowed requested system instead of preserving capability",
    )

    assert event.prediction_after < event.prediction_before
    assert event.reward == -1.0


def test_feedback_is_appended_as_auditable_jsonl(tmp_path) -> None:
    feedback_path = tmp_path / "adaptive_feedback.jsonl"
    engine = AdaptiveIntelligenceEngine(feedback_path=feedback_path)
    candidate = _candidate("source-a", provenance_strength=1.0, task_relevance=0.8)

    engine.record_verified_success(
        task_id="task-3",
        candidate=candidate,
        reason="source matched runtime state",
        metadata={"commit": "abc123"},
    )

    rows = feedback_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["candidate_id"] == "source-a"
    assert payload["metadata"]["commit"] == "abc123"
    assert payload["reason"].startswith("verified_success:")


def test_model_state_round_trips(tmp_path) -> None:
    state_path = tmp_path / "adaptive_model.json"
    engine = AdaptiveIntelligenceEngine(ranker=AdaptiveRanker(learning_rate=0.17))
    candidate = _candidate("memory-a", continuity_value=1.0, operator_alignment=1.0)
    engine.record_verified_success(
        task_id="task-4",
        candidate=candidate,
        reason="restored prior valid state",
    )
    engine.save_model_state(state_path)

    loaded = AdaptiveIntelligenceEngine.load_model_state(state_path)

    assert loaded.learning_rate == 0.17
    assert loaded.weights == engine.ranker.weights
    assert loaded.bias == engine.ranker.bias


def test_semantic_enricher_is_pluggable() -> None:
    engine = AdaptiveIntelligenceEngine(semantic_enricher=lambda query, text: 0.91)
    candidate = _candidate("memory-b", task_relevance=0.7)

    enriched = engine.enrich_semantic_score(
        query="APEX execution foundation",
        text="context and continuity",
        candidate=candidate,
    )

    assert enriched.features["semantic_relevance"] == 0.91
