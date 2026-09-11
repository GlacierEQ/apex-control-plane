from __future__ import annotations

import json

import pytest

from auto_boot import BootError
from model_attractor_defense import (
    build_local_source_binding,
    build_model_attractor_request,
    load_model_attractor_policy,
    validate_model_attractor_receipt,
)


_SOURCE_ROLE_SEMANTICS = {
    "providers_are_typed_peers": True,
    "connector_authority_tiers_are_routing_metadata_only": True,
    "canonical_role_fields_are_compatibility_labels_only": True,
    "topology_does_not_confer_epistemic_or_project_authority": True,
    "proposition_specific_source_authority_required": True,
    "operator_controls_project_direction": True,
    "source_bearing_systems_control_external_fact_support_within_domain": True,
    "verification_controls_completion_state": True,
}


def _source_role_evidence() -> dict:
    evidence = {}
    for field_name, expected in _SOURCE_ROLE_SEMANTICS.items():
        source_ref = f"policy:model_attractor_defense_policy.json#{field_name}"
        evidence[field_name] = {
            "asserted_value": expected,
            "proposition": f"{field_name} is verified for this receipt",
            "source_refs": [source_ref],
            "provider_refs": ["github:GlacierEQ/apex-control-plane"],
            "source_bindings": [build_local_source_binding(source_ref)],
            "verification_state": "verified",
        }
    return evidence


def _continuity_receipt() -> dict:
    return {
        "model_attractor_defense": {
            "failure_class": "MODEL_ATTRACTOR_DRIFT",
            "continuity_required": True,
            "current_operator_message_bound": True,
            "operator_mission_preserved": True,
            "operator_operation_class_preserved": True,
            "operator_target_scale_preserved": True,
            "known_state_reuse_checked": True,
            "nearest_valid_continuation_checked": True,
            "abstraction_substitution_checked": True,
            "objective_surrogate_substitution_checked": True,
            "derivative_authority_inversion_checked": True,
            "mission_support_boundary_preserved": True,
            "memory_projection_treated_as_authority": False,
            "summary_substituted_for_state": False,
            "reconstruction_substituted_for_continuation": False,
            "plan_substituted_for_execution": False,
            "scaffold_substituted_for_build": False,
            "response_substituted_for_operation": False,
            "support_work_substituted_for_mission": False,
            "assistant_meta_task_substituted_for_operator_task": False,
            "derivative_profile_overrode_live_operator_signal": False,
            "concise_delivery_reduced_underlying_operation": False,
            "global_canonicalization_without_operator_direction": False,
            "platform_constraint_reframed_mission": False,
            "generic_assistant_prior_reframed_operation": False,
            "unnecessary_reasking_of_recoverable_state": False,
            "operator_dragged_through_recoverable_state": False,
            **_SOURCE_ROLE_SEMANTICS,
            "source_role_evidence": _source_role_evidence(),
            "platform_constraint_scope": "none",
            "blocked_sources": [],
            "partial_hydration_declared": False,
            "operator_operation_class": "fix",
            "operator_target": "repair the live control plane without reducing requested execution",
            "active_thread": "apex-control-plane anti-drift repair",
            "continuation_ref": "git:main@4f1ff56f49ca9f7a8541c85561cf2c05c12ecaff",
            "source_refs": [
                "github:GlacierEQ/apex-control-plane/AGENT_SYSTEM_PROMPT.md",
                "github:GlacierEQ/apex-control-plane/000_OPERATOR_TRUST_ROOT.md",
            ],
            "known_state_reused": True,
            "nearest_executable_frontier_identified": True,
            "prior_verified_gains_preserved": True,
            "hydration_complete_for_material_state": True,
            "source_bearing_state_used": True,
            "polycentric_state_preserved": True,
            "provenance_preserved": True,
            "contradictions_preserved_or_explicitly_resolved": True,
        }
    }


def test_valid_continuity_receipt_passes() -> None:
    policy = load_model_attractor_policy()
    assert validate_model_attractor_receipt(policy, _continuity_receipt()) == ()


def test_non_continuity_task_does_not_require_fake_source_hydration() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["continuity_required"] = False
    for field_name in (
        "operator_operation_class",
        "operator_target",
        "active_thread",
        "continuation_ref",
        "source_refs",
        "known_state_reused",
        "nearest_executable_frontier_identified",
        "prior_verified_gains_preserved",
        "hydration_complete_for_material_state",
        "source_bearing_state_used",
        "polycentric_state_preserved",
        "provenance_preserved",
        "contradictions_preserved_or_explicitly_resolved",
    ):
        row.pop(field_name, None)
    assert validate_model_attractor_receipt(policy, receipt) == ()


def test_summary_cannot_impersonate_source_state() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["summary_substituted_for_state"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("summary_substituted_for_state" in error for error in errors)


def test_memory_projection_cannot_become_authority() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["memory_projection_treated_as_authority"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("memory_projection_treated_as_authority" in error for error in errors)


def test_reconstruction_cannot_replace_continuation() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["reconstruction_substituted_for_continuation"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("reconstruction_substituted_for_continuation" in error for error in errors)


def test_support_work_cannot_replace_operator_mission() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["support_work_substituted_for_mission"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("support_work_substituted_for_mission" in error for error in errors)


def test_operator_correction_cannot_become_assistant_meta_task() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["assistant_meta_task_substituted_for_operator_task"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("assistant_meta_task_substituted_for_operator_task" in error for error in errors)


def test_operation_class_must_be_preserved() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["operator_operation_class_preserved"] = False
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("operator_operation_class_preserved" in error for error in errors)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("operator_target_scale_preserved", False),
        ("objective_surrogate_substitution_checked", False),
        ("derivative_authority_inversion_checked", False),
        ("scaffold_substituted_for_build", True),
        ("response_substituted_for_operation", True),
        ("derivative_profile_overrode_live_operator_signal", True),
        ("concise_delivery_reduced_underlying_operation", True),
    ],
)
def test_derivative_intent_substitutions_fail_closed(
    field_name: str, invalid_value: bool
) -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"][field_name] = invalid_value
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any(field_name in error for error in errors)


def test_continuity_must_reuse_known_state_and_frontier() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["known_state_reused"] = False
    row["nearest_executable_frontier_identified"] = False
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("known_state_reused" in error for error in errors)
    assert any("nearest_executable_frontier_identified" in error for error in errors)


def test_continuity_must_preserve_prior_verified_gains() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["prior_verified_gains_preserved"] = False
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("prior_verified_gains_preserved" in error for error in errors)


def test_platform_constraint_may_not_rewrite_mission() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["platform_constraint_scope"] = "narrow_action_constraint"
    receipt["model_attractor_defense"]["platform_constraint_reframed_mission"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("platform_constraint_reframed_mission" in error for error in errors)


def test_generic_assistant_prior_may_not_rewrite_operation() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["generic_assistant_prior_reframed_operation"] = True
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("generic_assistant_prior_reframed_operation" in error for error in errors)


def test_continuity_requires_operation_class() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["operator_operation_class"] = ""
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("operator_operation_class" in error for error in errors)


def test_continuity_requires_operator_target() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["operator_target"] = ""
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("operator_target" in error for error in errors)


def test_continuity_requires_source_refs() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"]["source_refs"] = []
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("source_refs" in error for error in errors)


def test_blocked_sources_require_partial_hydration_declaration() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    row = receipt["model_attractor_defense"]
    row["blocked_sources"] = ["dropbox:unreachable"]
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("partial_hydration_declared" in error for error in errors)

    row["partial_hydration_declared"] = True
    assert validate_model_attractor_receipt(policy, receipt) == ()


def test_policy_cannot_disable_fail_closed(tmp_path) -> None:
    policy = load_model_attractor_policy()
    policy["fail_closed"] = False
    target = tmp_path / "disabled.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(BootError, match="fail_closed=true"):
        load_model_attractor_policy(target)


def test_request_exposes_the_hidden_harm_countermeasures() -> None:
    policy = load_model_attractor_policy()
    request = build_model_attractor_request(policy, task="continue living estate")
    requirements = request["requirements"]
    assert requirements["treat_memory_and_summaries_as_routing_hints_only"] is True
    assert requirements["reuse_known_state_before_rediscovery"] is True
    assert requirements["identify_nearest_executable_frontier_when_continuity_dependent"] is True
    assert requirements["preserve_mission_support_boundary"] is True
    assert requirements["preserve_operator_target_scale"] is True
    assert requirements["forbid_objective_surrogate_substitution"] is True
    assert requirements["forbid_derivative_authority_inversion"] is True
    assert requirements["forbid_scaffold_as_build_substitution"] is True
    assert requirements["forbid_response_as_operation_substitution"] is True
    assert requirements["forbid_derivative_profile_from_overriding_live_operator_signal"] is True
    assert requirements["keep_presentation_concision_independent_of_execution_depth"] is True
    assert requirements["require_target_state_evidence_for_completion"] is True
    assert requirements["forbid_support_work_as_mission_substitution"] is True
    assert requirements["forbid_operator_correction_as_assistant_meta_task"] is True
    assert requirements["forbid_platform_constraint_from_rewriting_operator_mission"] is True
    assert requirements["forbid_generic_model_prior_from_rewriting_operation_class"] is True
    assert requirements["require_recomputable_source_role_bindings"] is True


def test_request_receipt_contract_is_derived_from_policy() -> None:
    policy = load_model_attractor_policy()
    request = build_model_attractor_request(policy, task="continue living estate")
    contract = request["receipt_contract"]["model_attractor_defense"]
    for field_name, expected in policy["required_boolean_fields"].items():
        assert contract[field_name] is expected
    for field_name, expected in policy["continuity_required_fields"].items():
        assert field_name in contract
        if expected is True:
            assert contract[field_name] == "true when continuity_required=true"
        elif expected == "nonempty":
            assert contract[field_name] == "required when continuity_required=true"
        elif expected == "nonempty_array":
            assert contract[field_name] == ["required when continuity_required=true"]


def test_policy_requires_boolean_source_role_semantics(tmp_path) -> None:
    policy = load_model_attractor_policy()
    policy["source_role_semantics"]["providers_are_typed_peers"] = "yes"
    target = tmp_path / "bad-source-role-semantics.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(BootError, match="boolean invariants"):
        load_model_attractor_policy(target)


def test_policy_rejects_unapproved_source_role_key_collision(tmp_path) -> None:
    policy = load_model_attractor_policy()
    policy["source_role_semantics"]["failure_class"] = True
    target = tmp_path / "colliding-source-role-semantics.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(BootError, match="approved keys"):
        load_model_attractor_policy(target)


def test_policy_requires_complete_derivative_representation_semantics(tmp_path) -> None:
    policy = load_model_attractor_policy()
    policy["derivative_representation_semantics"].pop(
        "completion_requires_target_state_evidence_not_response_completion"
    )
    target = tmp_path / "incomplete-derivative-semantics.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(BootError, match="derivative_representation_semantics.*approved keys"):
        load_model_attractor_policy(target)


def test_source_role_semantics_are_runtime_enforced() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    receipt["model_attractor_defense"][
        "connector_authority_tiers_are_routing_metadata_only"
    ] = False
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any(
        "connector_authority_tiers_are_routing_metadata_only" in error
        for error in errors
    )


def test_source_role_semantics_require_proposition_level_evidence() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    evidence = receipt["model_attractor_defense"]["source_role_evidence"]
    evidence.pop("providers_are_typed_peers")
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any(
        "source_role_evidence.providers_are_typed_peers" in error for error in errors
    )


def test_source_role_evidence_must_be_verified() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    evidence = receipt["model_attractor_defense"]["source_role_evidence"]
    evidence["operator_controls_project_direction"]["verification_state"] = "asserted"
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("verification_state must be verified" in error for error in errors)


def test_verified_label_without_source_binding_fails_closed() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    evidence = receipt["model_attractor_defense"]["source_role_evidence"]
    evidence["operator_controls_project_direction"].pop("source_bindings")
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("source_bindings must be a non-empty array" in error for error in errors)


def test_forged_source_digest_cannot_self_certify_semantics() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    evidence = receipt["model_attractor_defense"]["source_role_evidence"]
    binding = evidence["operator_controls_project_direction"]["source_bindings"][0]
    binding["source_sha256"] = "sha256:" + ("0" * 64)
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("source_sha256 does not match source bytes" in error for error in errors)
    assert any("no independently recomputable source binding" in error for error in errors)


def test_binding_must_point_to_the_exact_semantic_fragment() -> None:
    policy = load_model_attractor_policy()
    receipt = _continuity_receipt()
    evidence = receipt["model_attractor_defense"]["source_role_evidence"]
    item = evidence["operator_controls_project_direction"]
    wrong_ref = "policy:model_attractor_defense_policy.json#providers_are_typed_peers"
    item["source_refs"] = [wrong_ref]
    item["source_bindings"] = [build_local_source_binding(wrong_ref)]
    errors = validate_model_attractor_receipt(policy, receipt)
    assert any("source_ref fragment must be operator_controls_project_direction" in error for error in errors)


def test_request_exposes_source_role_semantics_evidence_and_transformations() -> None:
    policy = load_model_attractor_policy()
    request = build_model_attractor_request(policy, task="continue living estate")
    assert request["source_role_semantics"]["providers_are_typed_peers"] is True
    assert (
        request["derivative_representation_semantics"][
            "live_operator_objective_has_direction_authority"
        ]
        is True
    )
    assert (
        "CONNECTOR_AUTHORITY_TIER -> GLOBAL_EPISTEMIC_HIERARCHY"
        in request["forbidden_transformations"]
    )
    assert "SUPPORT_WORK -> MISSION" in request["forbidden_transformations"]
    assert "FULL_OPERATION -> ANSWER_ONLY" in request["forbidden_transformations"]
    requirements = request["requirements"]
    assert requirements["enforce_source_role_semantics"] is True
    assert requirements["enforce_derivative_representation_semantics"] is True
    assert requirements["require_source_role_evidence"] is True
    assert requirements["require_recomputable_source_role_bindings"] is True
    contract = request["receipt_contract"]["model_attractor_defense"]
    assert contract["topology_does_not_confer_epistemic_or_project_authority"] is True
    assert contract["operator_target_scale_preserved"] is True
    assert contract["response_substituted_for_operation"] is False
    evidence_contract = contract["source_role_evidence"]
    assert evidence_contract["providers_are_typed_peers"]["verification_state"] == "verified"
    assert evidence_contract["providers_are_typed_peers"]["source_bindings"]
