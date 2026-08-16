from __future__ import annotations

from operator_fidelity_preflight import (
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
            "operator_words_digest": digest_operator_words(*words),
            "literal_constraints": list(words),
            "correction_present": True,
            "objective_function_reassessed": True,
            "corrections_applied": [
                "minimum-scope default removed",
                "function restored above governance",
            ],
            "correction_effect": "path selection now maximizes coherent capability",
            "operator_directed_reduction": False,
            "selected_path": {
                "literal_instruction_fidelity": True,
                "instruction_displacement": False,
                "minimum_scope_default": False,
                "governance_first": False,
                "permission_loop": False,
                "capability_reduction": False,
                "preserves_prior_valid_gain": True,
                "functional_advance": "bind fidelity preflight into runtime boot",
                "strongest_coherent_path": "fail closed before runtime if direction is displaced",
            },
            "next_ceiling": "propagate the same invariant into downstream agents",
        }
    }


def test_valid_operator_fidelity_receipt_passes() -> None:
    policy = load_operator_fidelity_policy()
    assert validate_operator_fidelity_receipt(policy, _receipt()) == ()


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
