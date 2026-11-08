from __future__ import annotations

import json
import math

import pytest

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
        verify_outcome=lambda: True,
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
        verify_outcome=lambda: True,
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
        verify_outcome=lambda: True,
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


def test_operator_correction_survives_engine_restart(tmp_path) -> None:
    """A feedback update must shape the next worker, not only the current process."""
    state_path = tmp_path / "operator-learning.json"
    candidate = _candidate("scope-collapse", correction_risk=1.0, regression_risk=1.0)
    worker_a = AdaptiveIntelligenceEngine(
        ranker=AdaptiveRanker(learning_rate=0.5), model_state_path=state_path
    )
    prior = worker_a.ranker.score(candidate).score
    correction = worker_a.record_operator_correction(
        task_id="operator-turn-20261013",
        candidate=candidate,
        reason="answer-only response instead of durable learning",
    )
    assert state_path.exists()
    assert correction.prediction_after < prior

    worker_b = AdaptiveIntelligenceEngine(model_state_path=state_path)
    assert worker_b.ranker.score(candidate).score == correction.prediction_after
    assert worker_b.ranker.learning_rate == 0.5


def test_separate_python_process_recovers_learned_state(tmp_path) -> None:
    """A new Python interpreter must actually load the corrected behavior."""
    import subprocess
    import sys

    state_path = tmp_path / "operator-learning.json"
    candidate = _candidate("repeat-old-failure", correction_risk=1.0)
    engine = AdaptiveIntelligenceEngine(model_state_path=state_path)
    correction = engine.record_operator_correction(
        task_id="cross-process", candidate=candidate, reason="repeated uncorrected behavior"
    )
    code = (
        "from src.adaptive_intelligence import AdaptiveCandidate, AdaptiveIntelligenceEngine; "
        "import sys; "
        "engine=AdaptiveIntelligenceEngine(model_state_path=sys.argv[1]); "
        "candidate=AdaptiveCandidate('repeat-old-failure','context',{'correction_risk':1.0}); "
        "print(engine.ranker.score(candidate).score)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(state_path)],
        check=True, capture_output=True, text=True,
    )
    assert abs(float(proc.stdout.strip()) - correction.prediction_after) < 1e-12


def test_stale_second_worker_does_not_erase_first_workers_learning(tmp_path) -> None:
    """Each writer must rebase on the latest checkpoint while under the lock."""
    state_path = tmp_path / "operator-learning.json"
    candidate = _candidate("unsafe-default", correction_risk=1.0)
    worker_a = AdaptiveIntelligenceEngine(model_state_path=state_path)
    worker_b = AdaptiveIntelligenceEngine(model_state_path=state_path)
    first = worker_a.record_operator_correction(
        task_id="correction-1", candidate=candidate, reason="failed prior turn"
    )
    second = worker_b.record_operator_correction(
        task_id="correction-2", candidate=candidate, reason="failure repeated"
    )
    assert second.prediction_before == first.prediction_after
    resumed = AdaptiveIntelligenceEngine(model_state_path=state_path)
    assert resumed.ranker.score(candidate).score == second.prediction_after


def test_corrupt_persisted_learning_fails_closed_instead_of_resetting(tmp_path) -> None:
    """Bad state must never silently restore the wrong default behavior."""
    import pytest

    path = tmp_path / "learning.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        AdaptiveIntelligenceEngine(model_state_path=path)


def test_explicit_ranker_cannot_silently_replace_prior_learned_state(tmp_path) -> None:
    import pytest

    path = tmp_path / "learning.json"
    engine = AdaptiveIntelligenceEngine(model_state_path=path)
    engine.record_operator_correction(
        task_id="saved", candidate=_candidate("old", correction_risk=1),
        reason="firsthand operator correction",
    )
    with pytest.raises(ValueError, match="persisted"):
        AdaptiveIntelligenceEngine(model_state_path=path, ranker=AdaptiveRanker())


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_nonfinite_features_do_not_become_maximum_confidence(invalid) -> None:
    learner = AdaptiveIntelligenceEngine()
    with pytest.raises(ValueError, match="finite"):
        learner.rank([_candidate("corrupted-signal", provenance_strength=invalid)])


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_nonfinite_feedback_cannot_turn_into_positive_learning(tmp_path, invalid) -> None:
    model_path = tmp_path / "learned-state.json"
    engine = AdaptiveIntelligenceEngine(model_state_path=model_path)
    candidate = _candidate("broken-feedback", task_relevance=0.8, operator_alignment=1.0)
    initial = engine.ranker.score(candidate).score
    with pytest.raises(ValueError, match="finite"):
        engine.record_outcome(
            task_id="bad-feedback", candidate=candidate, reward=invalid,
            reason="invalid measurement is not successful work",
        )
    assert engine.ranker.score(candidate).score == initial
    assert not model_path.exists()


def test_feature_clamping_preserved_but_rewards_must_be_measured() -> None:
    learner = AdaptiveIntelligenceEngine(ranker=AdaptiveRanker(learning_rate=0.2))
    candidate = _candidate("known-finite", task_relevance=1.5, verification_strength=0.6)
    features = candidate.normalized_features()
    assert features["task_relevance"] == 1.0
    before = learner.ranker.score(candidate).score
    event = learner.record_outcome(
        task_id="finite-feedback", candidate=candidate, reward=1.0,
        reason="independent confirmation", verify_outcome=lambda: True,
    )
    assert event.reward == 1.0
    assert learner.ranker.score(candidate).score > before


@pytest.mark.parametrize("reward", [2.0, -1.2, True, False])
def test_reward_outside_contract_never_mutates_persistent_state(tmp_path, reward) -> None:
    path = tmp_path / "learned.json"
    engine = AdaptiveIntelligenceEngine(model_state_path=path)
    candidate = _candidate("fake-metric", task_relevance=1.0)
    original = engine.ranker.score(candidate).score
    with pytest.raises(ValueError):
        engine.record_outcome(
            task_id="bad-metric", candidate=candidate,
            reward=reward, reason="untrusted grade",
            verify_outcome=lambda: True,
        )
    assert not path.exists()
    assert engine.ranker.score(candidate).score == original


@pytest.mark.parametrize("verifier", [None, lambda: False, lambda: None])
def test_positive_outcome_without_independent_readback_is_not_learned(tmp_path, verifier) -> None:
    path = tmp_path / "learned.json"
    engine = AdaptiveIntelligenceEngine(model_state_path=path)
    candidate = _candidate("falsely-done", task_relevance=1.0)
    before = engine.ranker.score(candidate).score
    with pytest.raises(ValueError, match="independent outcome verification"):
        engine.record_verified_success(
            task_id="not-done", candidate=candidate, reason="caller says complete",
            verify_outcome=verifier,
        )
    assert not path.exists()
    assert engine.ranker.score(candidate).score == before


def test_action_fragment_cannot_claim_mission_reward_even_with_native_blob(tmp_path) -> None:
    engine = AdaptiveIntelligenceEngine(model_state_path=tmp_path / "learning.json")
    candidate = AdaptiveCandidate("fragment", "action", {"mission_advancement": 1.0})
    before = engine.ranker.score(candidate).score
    fragment = {
        "native_stage": "VERIFIED_MATERIAL_DELTA",
        "provider_ref": "github:commit", "readback_ref": "github:blob",
        "source_state_ref": "github:old", "after_state_ref": "github:new",
    }
    with pytest.raises(ValueError, match="mission-complete"):
        engine.record_outcome(
            task_id="not-closed", candidate=candidate, reward=1.0,
            reason="PR opened, not merged", metadata=fragment,
            verify_outcome=lambda: True,
        )
    assert not engine.model_state_path.exists()
    assert engine.ranker.score(candidate).score == before


def test_action_verified_mission_outcome_can_be_rewarded(tmp_path) -> None:
    engine = AdaptiveIntelligenceEngine(model_state_path=tmp_path / "learning.json")
    candidate = AdaptiveCandidate("delivered", "action", {"task_relevance": 0.9})
    proof = {
        "native_stage": "HUMAN_OUTCOME",
        "provider_ref": "provider:outcome", "readback_ref": "provider:readback",
        "source_state_ref": "provider:old", "after_state_ref": "provider:new",
    }
    before = engine.ranker.score(candidate).score
    event = engine.record_outcome(
        task_id="delivered", candidate=candidate, reward=1.0,
        reason="owner-native confirmed", metadata=proof,
        verify_outcome=lambda: True,
    )
    assert event.reward == 1.0
    assert engine.ranker.score(candidate).score > before
    assert engine.model_state_path.exists()


def _native_action_proof(*, after: str = "provider:state-two") -> dict[str, str]:
    return {
        "native_stage": "HUMAN_OUTCOME",
        "provider_ref": "provider:successful-outcome",
        "readback_ref": "provider:independent-readback",
        "source_state_ref": "provider:state-one",
        "after_state_ref": after,
    }


def test_provider_outcome_cannot_earn_twice_across_workers_or_tasks(tmp_path) -> None:
    path = tmp_path / "learning.json"
    first = AdaptiveIntelligenceEngine(model_state_path=path)
    stale = AdaptiveIntelligenceEngine(model_state_path=path)
    a = AdaptiveCandidate("first", "action", {"task_relevance": 1.0})
    b = AdaptiveCandidate("second", "action", {"task_relevance": 1.0})
    proof = _native_action_proof()
    first.record_verified_success(
        task_id="mission-one", candidate=a, reason="provider verified",
        metadata=proof, verify_outcome=lambda: True,
    )
    checkpoint = path.read_bytes()
    assert len(json.loads(checkpoint)["reward_receipts"]) == 1
    with pytest.raises(ValueError, match="already rewarded"):
        stale.record_verified_success(
            task_id="different-mission", candidate=b, reason="receipt relabeled",
            metadata=proof, verify_outcome=lambda: True,
        )
    restarted = AdaptiveIntelligenceEngine(model_state_path=path)
    with pytest.raises(ValueError, match="already rewarded"):
        restarted.record_outcome(
            task_id="third-mission", candidate=a, reward=1.0, reason="replay",
            metadata=proof, verify_outcome=lambda: True,
        )
    assert path.read_bytes() == checkpoint
    second_readback = dict(proof, readback_ref="provider:corroborating-readback")
    with pytest.raises(ValueError, match="already rewarded"):
        restarted.record_verified_success(
            task_id="same-outcome-new-evidence", candidate=b,
            reason="readback changed, outcome did not", metadata=second_readback,
            verify_outcome=lambda: True,
        )
    assert path.read_bytes() == checkpoint
    restarted.record_verified_success(
        task_id="mission-two", candidate=b, reason="distinct native state",
        metadata=_native_action_proof(after="provider:state-three"),
        verify_outcome=lambda: True,
    )
    assert len(json.loads(path.read_text())["reward_receipts"]) == 2


def test_in_memory_replay_rejected_but_negative_feedback_survives() -> None:
    engine = AdaptiveIntelligenceEngine()
    candidate = AdaptiveCandidate("route", "action", {"task_relevance": 0.9})
    proof = _native_action_proof()
    engine.record_verified_success(
        task_id="mission", candidate=candidate, reason="native verified",
        metadata=proof, verify_outcome=lambda: True,
    )
    score = engine.ranker.score(candidate).score
    with pytest.raises(ValueError, match="already rewarded"):
        engine.record_verified_success(
            task_id="mission", candidate=candidate, reason="duplicate",
            metadata=proof, verify_outcome=lambda: True,
        )
    assert engine.ranker.score(candidate).score == score
    assert engine.record_operator_correction(
        task_id="mission", candidate=candidate, reason="regression",
    ).reward == -1.0
    assert engine.ranker.score(candidate).score < score


def test_replayed_context_observation_does_not_earn_again(tmp_path) -> None:
    path = tmp_path / "learning.json"
    engine = AdaptiveIntelligenceEngine(model_state_path=path)
    candidate = _candidate("retrieval", task_relevance=1.0)
    engine.record_verified_success(
        task_id="one", candidate=candidate, reason="source read",
        metadata={"commit": "abc123"}, verify_outcome=lambda: True,
    )
    with pytest.raises(ValueError, match="already rewarded"):
        engine.record_verified_success(
            task_id="one", candidate=candidate, reason="renamed",
            metadata={"commit": "abc123"}, verify_outcome=lambda: True,
        )
    engine.record_verified_success(
        task_id="one", candidate=candidate, reason="new source",
        metadata={"commit": "def456"}, verify_outcome=lambda: True,
    )
    assert len(json.loads(path.read_text())["reward_receipts"]) == 2


def test_legacy_model_preserved_and_corrupted_reward_receipts_rejected(tmp_path) -> None:
    path = tmp_path / "learning.json"
    original = AdaptiveRanker().export_state()
    original.pop("reward_receipts")
    path.write_text(json.dumps(original))
    engine = AdaptiveIntelligenceEngine(model_state_path=path)
    assert engine.ranker.weights == original["weights"]
    assert engine.ranker.reward_receipts == set()
    invalid = dict(original, reward_receipts=["not-a-real-digest"])
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="reward receipt history"):
        AdaptiveIntelligenceEngine(model_state_path=path)
    assert json.loads(path.read_text()) == invalid


def test_failed_persistent_checkpoint_cannot_create_false_reward_log(tmp_path, monkeypatch) -> None:
    import src.adaptive_intelligence as learning_module

    path = tmp_path / "learning.json"
    log = tmp_path / "feedback.jsonl"
    engine = AdaptiveIntelligenceEngine(model_state_path=path, feedback_path=log)
    candidate = AdaptiveCandidate("atomic", "action", {"task_relevance": 1.0})
    proof = _native_action_proof()
    before = engine.ranker.score(candidate).score
    original_writer = learning_module._write_learning_state

    def fail_write(*args):
        raise OSError("simulated checkpoint failure")

    monkeypatch.setattr(learning_module, "_write_learning_state", fail_write)
    with pytest.raises(OSError, match="checkpoint failure"):
        engine.record_verified_success(
            task_id="mission", candidate=candidate, reason="verified",
            metadata=proof, verify_outcome=lambda: True,
        )
    assert engine.ranker.score(candidate).score == before
    assert not path.exists()
    assert not log.exists()

    monkeypatch.setattr(learning_module, "_write_learning_state", original_writer)
    engine.record_verified_success(
        task_id="mission", candidate=candidate, reason="verified",
        metadata=proof, verify_outcome=lambda: True,
    )
    assert len(log.read_text().splitlines()) == 1
    assert len(json.loads(path.read_text())["reward_receipts"]) == 1
