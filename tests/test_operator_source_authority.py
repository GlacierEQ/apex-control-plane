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
    source_fidelity = policy["source_fidelity"]
    assert source_fidelity["verbatim_operator_source_is_controlling"] is True
    assert source_fidelity["summary_role"] == "INDEX_AND_ROUTING_ONLY"
    assert source_fidelity["summary_may_be_governing_source"] is False
    assert source_fidelity["summary_conflict_resolution"] == "VERBATIM_OPERATOR_SOURCE_WINS"
    assert source_fidelity["repeated_summary_does_not_gain_authority"] is True
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


def test_summary_can_never_become_governing_source(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["source_fidelity"]["summary_may_be_governing_source"] = True
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="summary_may_be_governing_source"):
        module.enforce_operator_source_authority()


def test_repeated_summary_cannot_gain_authority(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8"))
    policy["source_fidelity"]["repeated_summary_does_not_gain_authority"] = False
    import src.operator_source_authority as module
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="repeated_summary_does_not_gain_authority"):
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


def test_external_ai_draft_stays_evaluation_input_without_operator_adoption() -> None:
    from src import operator_source_authority as module
    result = module.assess_supplied_material(
        declared_origin="EXTERNAL_AI",
        intended_use="EVALUATE",
        historical_source_ref="conversation:external-ai-paste",
        adoption_source_ref=None,
        adopted_scope=None,
        style_cues=["long polished structure"],
        material_hidden_harms=["EXTRA_APPROVAL_GATE", "SCOPE_REDUCTION"],
    )
    assert result["status"] == "PROPOSAL_FOR_REVIEW"
    assert result["controlling_operator_direction"] is False
    assert result["operator_authorship_proven"] is False
    assert result["hidden_harms"] == ["EXTRA_APPROVAL_GATE", "SCOPE_REDUCTION"]


def test_external_ai_draft_requires_separate_explicit_scoped_adoption() -> None:
    from src import operator_source_authority as module
    adopted = module.assess_supplied_material(
        declared_origin="EXTERNAL_AI", intended_use="ADOPT",
        historical_source_ref="kimi:draft:42",
        adoption_source_ref="operator:message:43",
        adopted_scope="non-gating advisor and provenance only",
    )
    assert adopted["status"] == "ADOPTION_CLAIM_PENDING_SOURCE_VERIFICATION"
    assert adopted["controlling_operator_direction"] is False
    assert adopted["operator_authorship_proven"] is False
    assert adopted["adopted_scope"] == "non-gating advisor and provenance only"
    with pytest.raises(OperatorSourceAuthorityError, match="adoption_source_ref"):
        module.assess_supplied_material(
            declared_origin="EXTERNAL_AI", intended_use="ADOPT",
            historical_source_ref="kimi:draft:42",
            adoption_source_ref=None,
            adopted_scope="everything",
        )


def test_style_does_not_prove_authorship_or_authority() -> None:
    from src import operator_source_authority as module
    long_text = module.assess_supplied_material(
        declared_origin="UNKNOWN", intended_use="EVALUATE",
        historical_source_ref="conversation:long-text",
        style_cues=["polished", "no typos", "long paragraphs"],
    )
    short_text = module.assess_supplied_material(
        declared_origin="UNKNOWN", intended_use="EVALUATE",
        historical_source_ref="conversation:short-text",
        style_cues=["short", "typos", "meandering"],
    )
    for result in (long_text, short_text):
        assert result["status"] == "ORIGIN_UNVERIFIED_REVIEW"
        assert result["controlling_operator_direction"] is False
        assert result["operator_authorship_proven"] is False


def test_operator_directive_does_not_lose_authority_because_style_is_polished() -> None:
    from src import operator_source_authority as module
    result = module.assess_supplied_material(
        declared_origin="OPERATOR_AUTHORED",
        intended_use="DIRECT",
        historical_source_ref="operator:message:19",
        style_cues=["polished", "long"],
    )
    assert result["controlling_operator_direction"] is False
    assert result["status"] == "DECLARED_OPERATOR_DIRECTION_PENDING_SOURCE_VERIFICATION"
    assert result["operator_authorship_proven"] is False


def test_material_policy_structurally_blocks_laundering_and_requires_harm_audit(monkeypatch, tmp_path: Path) -> None:
    import src.operator_source_authority as module
    policy = module.enforce_operator_source_authority()
    surface = policy["user_supplied_material"]
    assert surface["style_may_prove_authorship"] is False
    assert surface["external_ai_paste_is_operator_authored"] is False
    assert surface["external_ai_proposal_requires_evaluation"] is True
    assert surface["explicit_adoption_requires_separate_operator_source"] is True
    assert surface["hidden_harms_must_be_tested"] is True
    policy["user_supplied_material"]["style_may_prove_authorship"] = True
    monkeypatch.setattr(module, "POLICY_PATH", _write_policy(tmp_path, policy))
    with pytest.raises(OperatorSourceAuthorityError, match="style_may_prove_authorship"):
        module.enforce_operator_source_authority()


def test_operator_authored_material_for_review_is_not_mislabeled_unknown() -> None:
    from src import operator_source_authority as module
    result = module.assess_supplied_material(
        declared_origin="OPERATOR_AUTHORED",
        intended_use="EVALUATE",
        historical_source_ref="operator:message:review-17",
        style_cues=["long polished passage"],
    )
    assert result["status"] == "OPERATOR_TEXT_FOR_EVALUATION"
    assert result["controlling_operator_direction"] is False
