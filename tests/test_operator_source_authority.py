from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.operator_source_authority import (
    OperatorSourceAuthorityError,
    enforce_operator_source_authority,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_operator_source_authority_contract_is_valid() -> None:
    policy = enforce_operator_source_authority()
    assert policy["personalization"]["highest_user_authority_layer"] is True
    turn_context = policy["turn_start_context"]
    assert turn_context["scope"] == "every_operator_turn"
    assert turn_context["retrieval_attempt_required"] is True
    assert turn_context["model_may_skip_due_to_apparent_sufficiency"] is False
    assert turn_context["retrieved_context_must_causally_affect_action_when_material"] is True
    assert turn_context["retrieval_failure_is_mission_stop"] is False
    assert turn_context["support_mechanism_may_not_gain_veto"] is True
    assert policy["source_state"]["operator_words_are_source_state"] is True
    identity = policy["source_identity"]
    assert identity["operator_source_class"] == "KNOWLEDGE_USE_DIRECTION"
    assert identity["knowledge_system_source_class"] == "KNOWLEDGE_STATE"
    assert identity["source_classes_never_collapse"] is True
    assert identity["knowledge_state_alone_does_not_choose_use"] is True
    assert identity["operator_direction_does_not_rewrite_evidence_or_knowledge_state"] is True
    provenance = policy["intent_provenance"]
    assert provenance["project_direction_authority_classes"] == [
        "USER_ORIGINATED",
        "ASSISTANT_PROPOSED_USER_ACCEPTED",
    ]
    assert provenance["assistant_originated_uncontested_does_not_become_operator_intent"] is True
    assert provenance["absence_of_operator_objection_is_not_adoption"] is True


def _write_policy(tmp_path: Path, policy: dict) -> Path:
    policy_path = tmp_path / "operator_source_authority_contract.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return policy_path


def test_operator_source_authority_fails_closed_on_override(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["personalization"]["summary_may_override"] = True
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="summary_may_override"):
        module.enforce_operator_source_authority()


def test_model_cannot_skip_turn_retrieval_because_context_looks_sufficient(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["turn_start_context"]["model_may_skip_due_to_apparent_sufficiency"] = True
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="model_may_skip_due_to_apparent_sufficiency"):
        module.enforce_operator_source_authority()


def test_context_retrieval_failure_cannot_become_mission_stop(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["turn_start_context"]["retrieval_failure_is_mission_stop"] = True
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="retrieval_failure_is_mission_stop"):
        module.enforce_operator_source_authority()


def test_assistant_uncontested_cannot_gain_operator_authority(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["intent_provenance"]["project_direction_authority_classes"].append("ASSISTANT_ORIGINATED_UNCONTESTED")
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="project_direction_authority_classes"):
        module.enforce_operator_source_authority()


def test_knowledge_state_cannot_silently_become_use_direction(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["source_identity"]["knowledge_state_alone_does_not_choose_use"] = False
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="knowledge_state_alone_does_not_choose_use"):
        module.enforce_operator_source_authority()
