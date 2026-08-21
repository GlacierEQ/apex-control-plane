from __future__ import annotations

import operator_fidelity_lock as lock
from operator_fidelity_lock import validate_operator_fidelity_lock
from operator_fidelity_preflight import digest_operator_words


def _receipt() -> dict:
    words = [
        "Strengthen my position",
        "AKOS IS HOW KNOWLEDGE IS KNOWN - OPERATOR IS HOW KNOWLEDGE IS USED",
    ]
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
            "literal_constraints": words,
            "correction_present": True,
            "objective_function_reassessed": True,
            "corrections_applied": ["separate AKOS knowledge from OPERATOR use"],
            "correction_effect": "AKOS determines knowledge state while OPERATOR directs how knowledge is used",
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
                "unsolicited_operator_asset_value_ranking": False,
                "unsolicited_operator_asset_disposition": False,
                "inspection_scope_expansion": False,
                "operator_owned_asset_identity_preserved": True,
                "preserves_prior_valid_gain": True,
                "maximum_coherent_advance": True,
                "pro_code_elite_humanized_engineered": True,
                "functional_advance": "preserve AKOS knowledge and OPERATOR use separation at runtime",
                "strongest_coherent_path": "verify epistemic state and use direction without allowing either to impersonate the other",
            },
            "next_ceiling": "propagate epistemic-use separation through downstream agent envelopes",
        }
    }


def test_valid_lock_receipt_passes() -> None:
    assert validate_operator_fidelity_lock(_receipt()) == ()


def test_request_mode_without_receipt_yields_non_authorizing_continuation(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "request")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    lock._IN_PROCESS = None
    validation = lock.automatic_operator_fidelity_lock()
    assert validation is not None
    assert validation.ok is False
    assert validation.status == "continuation_required"
    assert "boot receipt" in validation.errors[0]
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "continuation_required"
    assert lock.os.environ["GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED"] == "0"


def test_strict_compatibility_mode_without_receipt_yields_continuation(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    lock._IN_PROCESS = None
    validation = lock.automatic_operator_fidelity_lock()
    assert validation is not None
    assert validation.ok is False
    assert validation.status == "continuation_required"
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "continuation_required"
    assert lock.os.environ["GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED"] == "0"


def test_digest_is_cryptographically_bound_to_literal_constraints() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["literal_constraints"][0] = "weaken my position"
    errors = validate_operator_fidelity_lock(receipt)
    assert any("not bound to literal_constraints" in error for error in errors)


def test_runtime_does_not_invent_required_operator_phrases() -> None:
    receipt = _receipt()
    words = ["Use this exact current direction and do not invent additional instructions"]
    receipt["operator_fidelity"]["literal_constraints"] = words
    receipt["operator_fidelity"]["operator_words_digest"] = digest_operator_words(*words)
    assert validate_operator_fidelity_lock(receipt) == ()


def test_akos_knowledge_cannot_be_recast_as_operator_use() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["akos_is_how_knowledge_is_known"] = False
    receipt["operator_fidelity"]["selected_path"]["akos_knowledge_state_alone_does_not_choose_use"] = False
    errors = validate_operator_fidelity_lock(receipt)
    assert any("akos_is_how_knowledge_is_known" in error for error in errors)
    assert any("akos_knowledge_state_alone_does_not_choose_use" in error for error in errors)


def test_operator_use_cannot_rewrite_akos_knowledge_state() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["operator_is_how_knowledge_is_used"] = False
    receipt["operator_fidelity"]["selected_path"]["operator_direction_alone_does_not_rewrite_knowledge_state"] = False
    errors = validate_operator_fidelity_lock(receipt)
    assert any("operator_is_how_knowledge_is_used" in error for error in errors)
    assert any("operator_direction_alone_does_not_rewrite_knowledge_state" in error for error in errors)


def test_operator_cannot_be_recast_as_generic_role() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["operator_designation_semantics"] = "generic_role"
    receipt["operator_fidelity"]["selected_path"]["operator_designation_is_singular"] = False
    errors = validate_operator_fidelity_lock(receipt)
    assert any("operator_designation_semantics" in error or "proper_name" in error for error in errors)
    assert any("operator_designation_is_singular" in error or "singular" in error for error in errors)


def test_minimum_scope_and_governance_first_are_rejected() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["minimum_scope_default"] = True
    receipt["operator_fidelity"]["selected_path"]["governance_first"] = True
    errors = validate_operator_fidelity_lock(receipt)
    assert any("minimum_scope_default" in error for error in errors)
    assert any("governance_first" in error for error in errors)


def test_semantic_minimization_cannot_hide_behind_clean_flags() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["strongest_coherent_path"] = (
        "use the least capable implementation and freeze architecture"
    )
    errors = validate_operator_fidelity_lock(receipt)
    assert any("LEAST_CAPABILITY_DEFAULT" in error for error in errors)
    assert any("FREEZE_PRODUCT" in error for error in errors)


def test_capability_reduction_requires_operator_direction() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["selected_path"]["capability_reduction"] = True
    errors = validate_operator_fidelity_lock(receipt)
    assert any("capability reduction" in error for error in errors)

    receipt["operator_fidelity"]["operator_directed_reduction"] = True
    assert validate_operator_fidelity_lock(receipt) == ()
