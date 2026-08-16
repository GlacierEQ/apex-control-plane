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
            "continuation_resolved": True,
            "operator_intent_resolved": True,
            "operator_plan_authorized": True,
            "target_state": "integrated APEX startup",
            "prior_valid_gains_preserved": True,
            "contradiction_status": "resolved",
            "state_model_bound": True,
            "mutation_intent": "authorized",
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
                    "provenance": "github.fetch_file",
                }
            ],
        }
    }


def test_valid_apex_startup_receipt_passes() -> None:
    policy = load_apex_policy()
    assert validate_apex_startup_receipt(policy, _receipt()) == ()


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


def test_advanced_material_claim_requires_provenance() -> None:
    policy = load_apex_policy()
    receipt = _receipt()
    receipt["apex_startup"]["material_claims"] = [
        {"claim": "deployment happened", "state": "DEPLOYED"}
    ]
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any("provenance is required for DEPLOYED" in error for error in errors)


def test_state_transition_requires_exact_evidence() -> None:
    policy = load_apex_policy()
    errors = validate_state_transition(
        policy,
        "ATTEMPTED",
        "EXECUTED",
        evidence={},
    )
    assert errors == (
        "state transition ATTEMPTED->EXECUTED requires evidence: execution_receipt",
    )
    assert validate_state_transition(
        policy,
        "ATTEMPTED",
        "EXECUTED",
        evidence={"execution_receipt": "sha256:abc"},
    ) == ()


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
