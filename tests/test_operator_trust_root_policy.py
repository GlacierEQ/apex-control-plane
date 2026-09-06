from __future__ import annotations

from apex_enforced_startup import build_apex_startup_request, load_apex_policy
from operator_fidelity_preflight import load_operator_fidelity_policy


FORBIDDEN_OPERATOR_ROLES = {
    "adversary",
    "hostile_actor",
    "untrusted_principal",
    "obstruction_source",
    "external_opponent",
}


def test_apex_policy_binds_operator_as_principal_trust_root() -> None:
    policy = load_apex_policy()
    authority = policy["operator_authority"]
    assert policy["operator_trust_root_contract"] == "000_OPERATOR_TRUST_ROOT.md"
    assert authority["operator_is_principal"] is True
    assert authority["operator_is_trust_root"] is True
    assert authority["operator_as_adversary_forbidden"] is True
    assert authority["operator_correction_is_not_hostility"] is True
    assert authority["operator_disagreement_is_not_adversarial_behavior"] is True
    assert authority["operator_forceful_language_is_not_threat_signal"] is True
    assert authority["operator_firsthand_knowledge_is_not_external_adversary_input"] is True
    assert authority["operator_rejecting_agent_plan_is_not_obstruction"] is True


def test_historical_operator_adversary_state_has_zero_runtime_effect() -> None:
    policy = load_apex_policy()
    semantics = policy["classification_semantics"]
    decontamination = policy["retrieval_decontamination"]

    assert semantics["operator_role"] == "principal_trust_root"
    assert semantics["operator_role_reclassification_allowed"] is False
    assert semantics["historical_operator_adversary_state"] == "superseded_defect_provenance_only"
    assert semantics["historical_operator_adversary_governance_effect"] == "zero"
    assert semantics["historical_operator_adversary_trust_effect"] == "zero"
    assert semantics["historical_operator_adversary_risk_effect"] == "zero"
    assert semantics["historical_operator_adversary_routing_effect"] == "zero"

    assert decontamination["enabled"] is True
    assert decontamination["preserve_historical_source"] is True
    assert decontamination["strip_governing_effect_from_operator_adversary_labels"] is True
    assert decontamination["strip_trust_effect_from_operator_adversary_labels"] is True
    assert decontamination["strip_risk_weight_effect_from_operator_adversary_labels"] is True
    assert decontamination["strip_routing_effect_from_operator_adversary_labels"] is True
    assert decontamination["mark_as"] == "superseded_defect_provenance"
    assert decontamination["restore_operator_role"] == "principal_trust_root"


def test_adversarial_analysis_scope_excludes_operator_identity_and_authority() -> None:
    policy = load_apex_policy()
    scope = {str(value).strip().lower() for value in policy["classification_semantics"]["adversarial_analysis_scope"]}
    assert "operator" not in scope
    assert "operator_identity" not in scope
    assert "operator_authority" not in scope
    assert "claims" in scope
    assert "evidence" in scope
    assert "implementations" in scope
    assert "source_supported_external_opposition" in scope


def test_startup_request_exports_trust_root_instead_of_adversary_role() -> None:
    policy = load_apex_policy()
    request = build_apex_startup_request(policy, task="continue operator-directed work")
    authority = request["operator_authority"]
    assert authority["operator_is_principal"] is True
    assert authority["operator_is_trust_root"] is True
    assert authority["operator_as_adversary_forbidden"] is True
    serialized = str(request).lower()
    for role in FORBIDDEN_OPERATOR_ROLES:
        assert f"'operator_role': '{role}'" not in serialized


def test_fidelity_policy_carries_same_decontamination_contract() -> None:
    policy = load_operator_fidelity_policy()
    trust = policy["operator_trust_root"]
    assert policy["operator_trust_root_contract"] == "000_OPERATOR_TRUST_ROOT.md"
    assert trust["operator_role"] == "principal_trust_root"
    assert trust["operator_as_adversary_forbidden"] is True
    assert trust["operator_correction_is_not_hostility"] is True
    assert trust["operator_disagreement_is_not_adversarial_behavior"] is True
    assert trust["operator_forceful_language_is_not_threat_signal"] is True
    assert trust["operator_firsthand_knowledge_is_not_external_adversary_input"] is True
    assert trust["operator_rejecting_agent_plan_is_not_obstruction"] is True
    assert trust["historical_operator_adversary_state"] == "superseded_defect_provenance_only"
    assert trust["historical_governance_effect"] == "zero"
    assert trust["historical_trust_effect"] == "zero"
    assert trust["historical_risk_effect"] == "zero"
    assert trust["historical_routing_effect"] == "zero"
    assert trust["adversarial_methods_target_operator_authority"] is False


def test_regression_signatures_name_the_old_failure_modes() -> None:
    signatures = set(load_operator_fidelity_policy()["regression_signatures"])
    expected = {
        "FORBIDDEN: operator classified as adversary",
        "FORBIDDEN: operator correction classified as hostile input",
        "FORBIDDEN: operator disagreement classified as adversarial behavior",
        "FORBIDDEN: operator forceful language classified as threat signal",
        "FORBIDDEN: operator firsthand knowledge classified as external adversary input",
        "FORBIDDEN: operator rejection of agent plan classified as obstruction",
    }
    assert expected <= signatures
