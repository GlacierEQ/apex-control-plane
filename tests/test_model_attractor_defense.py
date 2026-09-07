from __future__ import annotations

import json

import pytest

from auto_boot import BootError
from model_attractor_defense import (
    build_model_attractor_request,
    load_model_attractor_policy,
    validate_model_attractor_receipt,
)


def _continuity_receipt() -> dict:
    return {
        "model_attractor_defense": {
            "failure_class": "MODEL_ATTRACTOR_DRIFT",
            "continuity_required": True,
            "current_operator_message_bound": True,
            "operator_mission_preserved": True,
            "nearest_valid_continuation_checked": True,
            "abstraction_substitution_checked": True,
            "memory_projection_treated_as_authority": False,
            "summary_substituted_for_state": False,
            "reconstruction_substituted_for_continuation": False,
            "plan_substituted_for_execution": False,
            "global_canonicalization_without_operator_direction": False,
            "platform_constraint_reframed_mission": False,
            "generic_assistant_prior_reframed_operation": False,
            "unnecessary_reasking_of_recoverable_state": False,
            "platform_constraint_scope": "none",
            "blocked_sources": [],
            "partial_hydration_declared": False,
            "active_thread": "apex-control-plane anti-drift repair",
            "continuation_ref": "git:main@4f1ff56f49ca9f7a8541c85561cf2c05c12ecaff",
            "source_refs": [
                "github:GlacierEQ/apex-control-plane/AGENT_SYSTEM_PROMPT.md",
                "github:GlacierEQ/apex-control-plane/000_OPERATOR_TRUST_ROOT.md",
            ],
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
        "active_thread",
        "continuation_ref",
        "source_refs",
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
    assert requirements["forbid_platform_constraint_from_rewriting_operator_mission"] is True
    assert requirements["forbid_generic_model_prior_from_rewriting_operation_class"] is True
