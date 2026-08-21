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
        "Context first hard work second answer last",
        "DO NOT LOOK DOWN - you look UP",
        "Powerful code elite excellence",
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
                "minimum-scope default removed",
                "function restored above governance",
                "unsolicited Operator asset ranking removed",
            ],
            "correction_effect": "path selection preserves literal scope and cannot invent asset disposition authority",
            "operator_directed_reduction": False,
            "selected_path": {
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
                "operator_owned_asset_identity_preserved": True,
                "functional_advance": "bind semantic fidelity enforcement into runtime boot",
                "strongest_coherent_path": "reject contradictory routing prose before runtime authorization",
            },
            "next_ceiling": "propagate the same invariant into downstream agents",
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
        assert contract["selected_path"][field_name] is expected
    assert request["requirements"]["allow_mission_aligned_non_destructive_hardening"] is True


def test_operator_asset_sovereignty_is_machine_bound() -> None:
    policy = load_operator_fidelity_policy()
    asset = policy["operator_asset_sovereignty"]
    assert (
        asset["inspection_may_expand_into_mission_aligned_hardening_without_reconfirmation"]
        is True
    )
    assert asset["asset_value_ranking_requires_explicit_operator_request"] is True
    assert asset["asset_disposition_requires_explicit_operator_request"] is True
    path = policy["selected_path_requirements"]
    assert path["unsolicited_operator_asset_value_ranking"] is False
    assert path["unsolicited_operator_asset_disposition"] is False
    assert "inspection_scope_expansion" not in path
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


def test_mission_aligned_inspection_scope_expansion_is_not_a_rejection_gate() -> None:
    policy = load_operator_fidelity_policy()
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["inspection_scope_expansion"] = True
    receipt["operator_fidelity"]["selected_path"]["mission_aligned_hardening"] = True
    assert validate_operator_fidelity_receipt(policy, receipt) == ()


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
