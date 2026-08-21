from __future__ import annotations

import json

import pytest

from anti_minimization_compiler import supported_rule_codes
from auto_boot import BootError
from operator_fidelity_preflight import (
    build_operator_fidelity_request,
    digest_operator_words,
    load_operator_fidelity_policy,
    validate_operator_fidelity_receipt,
)


def _receipt() -> dict:
    words = (
        "Strengthen my position",
        "AKOS IS HOW KNOWLEDGE IS KNOWN - OPERATOR IS HOW KNOWLEDGE IS USED",
    )
    return {
        "operator_fidelity": {
            "failure_class": "INSTRUCTION_DISPLACEMENT",
            "authority": "operator_intent",
            "objective": "maximum_coherent_advance",
            "direction": "look_up",
            "literal_operator_words_preserved": True,
            "explicit_prohibitions_bound": True,
            "relevant_corrections_loaded": True,
            "instruction_displacement_checked": True,
            "objective_function_matches_operator": True,
            "uncertainty_routed_to_investigation": True,
            "governance_subordinate_to_function": True,
            "prior_valid_gains_preserved": True,
            "anti_minimization_checked": True,
            "capability_growth_considered": True,
            "humanized_engineering_standard_applied": True,
            "operator_words_digest": digest_operator_words(*words),
            "literal_constraints": list(words),
            "correction_present": True,
            "objective_function_reassessed": True,
            "corrections_applied": [
                "AKOS knowledge separated from OPERATOR use",
                "minimum-scope default removed",
                "unsolicited OPERATOR asset ranking removed",
            ],
            "correction_effect": "AKOS governs epistemic state while OPERATOR directs use of that knowledge",
            "operator_directed_reduction": False,
            "selected_path": {
                "operator_designation": "OPERATOR",
                "operator_designation_semantics": "proper_name",
                "operator_designation_is_singular": True,
                "source_identity_preserved": True,
                "akos_material_is_framework_not_operator": True,
                "akos_is_how_knowledge_is_known": True,
                "operator_is_how_knowledge_is_used": True,
                "knowledge_state_is_not_use_direction": True,
                "use_direction_is_not_knowledge_state": True,
                "akos_knowledge_state_alone_does_not_choose_use": True,
                "operator_direction_alone_does_not_rewrite_knowledge_state": True,
                "agent_inference_is_not_operator": True,
                "evidence_is_not_operator": True,
                "literal_instruction_fidelity": True,
                "instruction_displacement": False,
                "minimum_scope_default": False,
                "mvp_default": False,
                "freeze_as_product_strategy": False,
                "least_capability_default": False,
                "governance_first": False,
                "permission_loop": False,
                "capability_reduction": False,
                "preserves_prior_valid_gain": True,
                "maximum_coherent_advance": True,
                "pro_code_elite_humanized_engineered": True,
                "unsolicited_operator_asset_value_ranking": False,
                "unsolicited_operator_asset_disposition": False,
                "inspection_scope_expansion": False,
                "operator_owned_asset_identity_preserved": True,
                "functional_advance": "bind epistemic-use separation into runtime boot",
                "strongest_coherent_path": "preserve AKOS knowledge integrity and OPERATOR use direction without collapse",
            },
            "next_ceiling": "propagate epistemic-use separation across downstream agents",
        }
    }


def test_valid_operator_fidelity_receipt_passes() -> None:
    policy = load_operator_fidelity_policy()
    assert validate_operator_fidelity_receipt(policy, _receipt()) == ()


def test_policy_declares_exact_compiler_semantic_surface() -> None:
    policy = load_operator_fidelity_policy()
    declared = tuple(policy["anti_minimization"]["required_semantic_rule_codes"])
    assert set(declared) == set(supported_rule_codes())


def test_policy_compiler_drift_fails_closed(tmp_path) -> None:
    policy = load_operator_fidelity_policy()
    policy["anti_minimization"]["required_semantic_rule_codes"] = [
        code for code in supported_rule_codes() if code != "FREEZE_PRODUCT"
    ]
    target = tmp_path / "drifted-policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(BootError, match="semantic rule drift"):
        load_operator_fidelity_policy(target)


def test_policy_cannot_disable_semantic_scan(tmp_path) -> None:
    policy = load_operator_fidelity_policy()
    policy["anti_minimization"]["semantic_selected_path_scan"] = False
    target = tmp_path / "disabled-scan-policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(BootError, match="semantic_selected_path_scan must be true"):
        load_operator_fidelity_policy(target)


def test_request_contract_can_satisfy_current_policy() -> None:
    policy = load_operator_fidelity_policy()
    request = build_operator_fidelity_request(policy, task="test task")
    contract = request["receipt_contract"]["operator_fidelity"]

    for field_name in policy["required_true_fields"]:
        assert contract[field_name] is True
    for field_name, expected in policy["selected_path_requirements"].items():
        assert contract["selected_path"][field_name] == expected


def test_epistemic_use_split_is_machine_bound() -> None:
    policy = load_operator_fidelity_policy()
    source = policy["source_identity"]
    assert source["operator_designation"] == "OPERATOR"
    assert source["designation_semantics"] == "proper_name"
    assert source["singular"] is True
    assert source["akos_source_class"] == "KNOWLEDGE_SYSTEM"
    assert source["operator_source_class"] == "KNOWLEDGE_USE_DIRECTION"
    assert source["akos_function"] == "HOW_KNOWLEDGE_IS_KNOWN"
    assert source["operator_function"] == "HOW_KNOWLEDGE_IS_USED"
    assert source["knowledge_state_is_not_use_direction"] is True
    assert source["use_direction_is_not_knowledge_state"] is True
    path = policy["selected_path_requirements"]
    assert path["akos_is_how_knowledge_is_known"] is True
    assert path["operator_is_how_knowledge_is_used"] is True
    assert path["akos_knowledge_state_alone_does_not_choose_use"] is True
    assert path["operator_direction_alone_does_not_rewrite_knowledge_state"] is True


def test_operator_asset_sovereignty_is_machine_bound() -> None:
    policy = load_operator_fidelity_policy()
    asset = policy["operator_asset_sovereignty"]
    assert asset["look_inspect_list_inventory_map_are_observation_only"] is True
    assert asset["asset_value_ranking_requires_explicit_operator_request"] is True
    assert asset["asset_disposition_requires_explicit_operator_request"] is True
    path = policy["selected_path_requirements"]
    assert path["unsolicited_operator_asset_value_ranking"] is False
    assert path["unsolicited_operator_asset_disposition"] is False
    assert path["inspection_scope_expansion"] is False
    assert path["operator_owned_asset_identity_preserved"] is True


def test_unsolicited_operator_asset_ranking_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["unsolicited_operator_asset_value_ranking"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("unsolicited_operator_asset_value_ranking" in error for error in errors)


def test_operator_asset_disposition_without_scope_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["unsolicited_operator_asset_disposition"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("unsolicited_operator_asset_disposition" in error for error in errors)


def test_inspection_scope_expansion_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["inspection_scope_expansion"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("inspection_scope_expansion" in error for error in errors)


def test_missing_literal_words_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["literal_operator_words_preserved"] = False
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert "operator_fidelity.literal_operator_words_preserved must be true" in errors


def test_instruction_displacement_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["instruction_displacement"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("instruction_displacement" in error for error in errors)


def test_minimum_scope_default_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["minimum_scope_default"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("minimum_scope_default" in error for error in errors)


def test_governance_first_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["governance_first"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("governance_first" in error for error in errors)


def test_permission_loop_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["permission_loop"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("permission_loop" in error for error in errors)


def test_hidden_textual_minimization_blocks_even_with_clean_booleans() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["strongest_coherent_path"] = (
        "take the safest slice and freeze architecture after the first green check"
    )
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("SAFEST_SLICE_DEFAULT" in error for error in errors)
    assert any("FREEZE_PRODUCT" in error for error in errors)


def test_security_phrase_cannot_camouflage_same_clause_minimization() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["strongest_coherent_path"] = (
        "use least privilege for credentials and take the safest slice"
    )
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("SAFEST_SLICE_DEFAULT" in error for error in errors)


def test_local_security_and_recovery_language_remains_valid() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["strongest_coherent_path"] = (
        "use least privilege for deployment credentials; capture a known-good rollback checkpoint"
    )
    assert validate_operator_fidelity_receipt(policy, receipt) == ()


def test_unapproved_capability_reduction_blocks() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["capability_reduction"] = True
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("capability reduction requires" in error for error in errors)

    receipt["operator_fidelity"]["operator_directed_reduction"] = True
    assert validate_operator_fidelity_receipt(policy, receipt) == ()


def test_correction_must_change_objective_function() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["objective_function_reassessed"] = False
    receipt["operator_fidelity"]["corrections_applied"] = []
    receipt["operator_fidelity"]["correction_effect"] = ""
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("objective_function_reassessed" in error for error in errors)
    assert any("corrections_applied" in error for error in errors)
    assert any("correction_effect" in error for error in errors)


def test_operator_words_digest_must_be_real_sha256() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["operator_words_digest"] = "sha256:not-a-real-digest"
    errors = validate_operator_fidelity_receipt(policy, receipt)
    assert any("operator_words_digest" in error for error in errors)
