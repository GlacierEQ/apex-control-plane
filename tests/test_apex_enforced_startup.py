from __future__ import annotations

from apex_enforced_startup import (
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
    assert any("provenance is required for material claims" in error for error in errors)


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
    assert any("requires receipt reference: verification_receipt" in error for error in errors)

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
    assert any("requires receipt reference: deployment_receipt" in error for error in errors)


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


def test_external_action_requires_named_human_approval() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["action_scope"] = "external"
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "external action requires apex_startup.named_human_approval" in errors

    receipt["apex_startup"]["named_human_approval"] = {
        "approver": "Casey Barton",
        "authorized": True,
        "approval_ref": "operator-command:turn-user-message",
    }
    assert validate_apex_startup_receipt(policy, receipt) == ()


def test_generic_or_malformed_external_approval_is_rejected() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["action_scope"] = "external"
    receipt["apex_startup"]["named_human_approval"] = {
        "approver": "operator",
        "authorized": True,
        "approval_ref": "false",
    }
    errors = validate_apex_startup_receipt(policy, receipt)
    assert "named_human_approval.approver must identify a named human" in errors
    assert "named_human_approval.approval_ref must be a receipt reference" in errors


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
    assert validate_state_transition(
        policy,
        "ATTEMPTED",
        "EXECUTED",
        evidence={"execution_receipt": "sha256:abc"},
    ) == ()


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
