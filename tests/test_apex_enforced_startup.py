from __future__ import annotations

import json

from apex_enforced_startup import (
    build_apex_startup_request,
    load_apex_policy,
    validate_apex_startup_receipt,
    validate_state_transition,
)


def _receipt() -> dict:
    return {
        "apex_startup": {
            "authority": "operator_intent",
            "objective": "maximum_coherent_advance",
            "context_reconstructed": True,
            "prior_state_retrieved": True,
            "continuation_resolved": True,
            "target_identity_resolved": True,
            "operator_intent_resolved": True,
            "operator_plan_authorized": True,
            "target_state": "integrated APEX startup",
            "prior_valid_gains_identified": True,
            "prior_valid_gains_preserved": True,
            "relevant_source_inspected": True,
            "contradiction_status": "resolved",
            "state_model_bound": True,
            "mutation_intent": "authorized",
            "action_scope": "internal",
            "selected_path": {
                "id": "continue-and-extend",
                "operator_alignment": True,
                "artificial_minimization": False,
                "destructive_reduction": False,
                "unsupported_action": False,
                "redundant_restart": False,
                "preserves_prior_valid_gain": True,
                "unsolicited_operator_asset_value_ranking": False,
                "unsolicited_operator_asset_disposition": False,
                "inspection_scope_expansion": False,
                "operator_owned_asset_identity_preserved": True,
            },
            "verification_plan": ["run tests", "adversarial state-promotion audit"],
            "material_claims": [
                {
                    "claim": "current control-plane source was inspected",
                    "state": "OBSERVED",
                    "provenance": "github:fetch-file-receipt",
                }
            ],
        }
    }


def test_valid_apex_startup_receipt_passes() -> None:
    policy = load_apex_policy()
    assert validate_apex_startup_receipt(policy, _receipt()) == ()


def test_operator_project_direction_authority_is_absolute() -> None:
    policy = load_apex_policy()
    authority = policy["operator_authority"]
    assert authority["mode"] == "absolute_project_direction"
    assert authority["sole_human_project_authority"] is True
    assert (
        authority[
            "current_explicit_instruction_is_sufficient_authorization_for_its_scope"
        ]
        is True
    )
    assert authority["secondary_human_approval_authority"] is False
    assert authority["lower_level_policy_veto"] is False
    assert authority["assistant_or_automation_override"] is False
    assert authority["repository_or_registry_override"] is False
    assert authority["operator_owned_asset_value_ranking_is_operator_only"] is True
    assert authority["operator_owned_asset_disposition_is_operator_only"] is True
    assert authority["inspection_does_not_expand_scope"] is True

    interlock = policy["mutation_interlock"]
    assert interlock["external_action_requires_operator_authorization_receipt"] is True
    assert interlock["external_action_requires_secondary_human_approval"] is False
    assert (
        interlock[
            "operator_owned_asset_disposition_requires_explicit_operator_direction"
        ]
        is True
    )
    assert (
        interlock[
            "operator_owned_asset_value_ranking_requires_explicit_operator_direction"
        ]
        is True
    )


def test_startup_request_cannot_reintroduce_secondary_approval_authority() -> None:
    policy = load_apex_policy()
    request = build_apex_startup_request(policy, task="execute operator target")
    requirements = request["requirements"]
    assert requirements["operator_project_direction_authority_is_absolute"] is True
    assert (
        requirements[
            "current_explicit_operator_instruction_is_authorization_for_its_scope"
        ]
        is True
    )
    assert requirements["secondary_human_approval_authority"] is False
    assert (
        requirements["external_actions_require_operator_authorization_receipt"] is True
    )
    serialized = json.dumps(request, sort_keys=True)
    assert "named_human_approval" not in serialized


def test_operator_asset_sovereignty_is_in_every_selected_path() -> None:
    policy = load_apex_policy()
    path = policy["path_requirements"]
    assert path["unsolicited_operator_asset_value_ranking"] is False
    assert path["unsolicited_operator_asset_disposition"] is False
    assert path["inspection_scope_expansion"] is False
    assert path["operator_owned_asset_identity_preserved"] is True

    request = build_apex_startup_request(policy, task="look at legal repos")
    selected = request["receipt_contract"]["apex_startup"]["selected_path"]
    for key, expected in path.items():
        assert selected[key] is expected


def test_unsolicited_asset_ranking_fails_closed() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["selected_path"][
        "unsolicited_operator_asset_value_ranking"
    ] = True
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any("unsolicited_operator_asset_value_ranking" in error for error in errors)


def test_inspection_scope_expansion_fails_closed() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["selected_path"]["inspection_scope_expansion"] = True
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any("inspection_scope_expansion" in error for error in errors)


def test_mutation_interlock_fields_are_mandatory() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    for field in (
        "prior_state_retrieved",
        "target_identity_resolved",
        "prior_valid_gains_identified",
        "relevant_source_inspected",
    ):
        receipt["apex_startup"][field] = False
    errors = validate_apex_startup_receipt(policy, receipt)
    for field in (
        "prior_state_retrieved",
        "target_identity_resolved",
        "prior_valid_gains_identified",
        "relevant_source_inspected",
    ):
        assert f"apex_startup.{field} must be true" in errors


def test_open_contradiction_blocks_startup() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["contradiction_status"] = "open_blocker"
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "apex_startup has an unresolved contradiction blocker" in errors


def test_artificial_minimization_blocks_selected_path() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["selected_path"]["artificial_minimization"] = True
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any("artificial_minimization" in error for error in errors)


def test_material_claim_requires_string_provenance() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["material_claims"] = [
        {"claim": "source exists", "state": "OBSERVED", "provenance": {}}
    ]
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any(
        "provenance is required for material claims" in error for error in errors
    )


def test_advanced_material_claim_requires_transition_receipt() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["material_claims"] = [
        {
            "claim": "execution verified",
            "source_state": "EXECUTED",
            "state": "VERIFIED",
            "provenance": "github:workflow-run",
            "transition_evidence": {},
        }
    ]
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any(
        "requires receipt reference: verification_receipt" in error for error in errors
    )

    receipt["apex_startup"]["material_claims"] = [
        {
            "claim": "deployment completed",
            "source_state": "COMMITTED",
            "state": "DEPLOYED",
            "provenance": "provider:deployment",
            "transition_evidence": {},
        }
    ]
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any(
        "requires receipt reference: deployment_receipt" in error for error in errors
    )


def test_advanced_material_claim_accepts_exact_transition_receipt() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["material_claims"] = [
        {
            "claim": "execution verified",
            "source_state": "EXECUTED",
            "state": "VERIFIED",
            "provenance": "github:workflow-run",
            "transition_evidence": {"verification_receipt": "github-check:12345"},
        }
    ]
    assert validate_apex_startup_receipt(policy, receipt) == ()


def test_external_action_requires_operator_authorization_not_second_approver() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["action_scope"] = "external"
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "external action requires apex_startup.operator_authorization" in errors

    receipt["apex_startup"]["operator_authorization"] = {
        "authorized": True,
        "authorization_ref": "operator-command:turn-user-message",
    }
    assert validate_apex_startup_receipt(policy, receipt) == ()


def test_old_named_human_gate_cannot_substitute_for_operator_authorization() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["action_scope"] = "external"
    receipt["apex_startup"]["named_human_approval"] = {
        "approver": "someone else",
        "authorized": True,
        "approval_ref": "other-human:approval",
    }
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "external action requires apex_startup.operator_authorization" in errors


def test_malformed_operator_authorization_is_rejected() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["action_scope"] = "external"
    receipt["apex_startup"]["operator_authorization"] = {
        "authorized": False,
        "authorization_ref": "false",
    }
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "operator_authorization.authorized must be true" in errors
    assert (
        "operator_authorization.authorization_ref must be a receipt reference" in errors
    )


def test_state_transition_requires_exact_evidence() -> None:
    policy = load_apex_policy()
    errors = validate_state_transition(
        policy,
        "ATTEMPTED",
        "EXECUTED",
        evidence={},
    )
    assert errors == (
        "state transition ATTEMPTED->EXECUTED requires receipt reference: execution_receipt",
    )
    assert (
        validate_state_transition(
            policy,
            "ATTEMPTED",
            "EXECUTED",
            evidence={"execution_receipt": "sha256:abc"},
        )
        == ()
    )


def test_truthy_non_receipt_evidence_is_rejected() -> None:
    policy = load_apex_policy()
    for invalid in ("false", ["receipt"], {"receipt": "x"}, 1, True):
        errors = validate_state_transition(
            policy,
            "ATTEMPTED",
            "EXECUTED",
            evidence={"execution_receipt": invalid},
        )
        assert errors == (
            "state transition ATTEMPTED->EXECUTED requires receipt reference: execution_receipt",
        )


def test_unlisted_state_jump_fails_closed() -> None:
    policy = load_apex_policy()
    errors = validate_state_transition(
        policy,
        "PROPOSED",
        "DEPLOYED",
        evidence={"deployment_receipt": "sha256:abc"},
    )
    assert errors == (
        "state transition PROPOSED->DEPLOYED is not explicitly authorized",
    )
