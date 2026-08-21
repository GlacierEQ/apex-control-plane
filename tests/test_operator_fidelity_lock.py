from __future__ import annotations

import pytest

import operator_fidelity_lock as lock
from operator_fidelity_lock import validate_operator_fidelity_lock
from operator_fidelity_preflight import digest_operator_words


def _receipt() -> dict:
    words = [
        "Context first hard work second answer last",
        "DO NOT LOOK DOWN - you look UP",
        "Powerful code elite excellence",
        "Function before governance; governance serves function",
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
            "corrections_applied": ["restore upward functional objective"],
            "correction_effect": "maximum coherent advance controls path selection",
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
                "unsolicited_operator_asset_value_ranking": False,
                "unsolicited_operator_asset_disposition": False,
                "operator_owned_asset_identity_preserved": True,
                "preserves_prior_valid_gain": True,
                "maximum_coherent_advance": True,
                "pro_code_elite_humanized_engineered": True,
                "functional_advance": "hard runtime fidelity lock with semantic inspection",
                "strongest_coherent_path": "runtime is rejected before loading on fidelity failure",
            },
            "next_ceiling": "propagate enforcement across every execution entrypoint",
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


def test_strict_mode_without_receipt_fails_closed_after_recording_continuation(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    lock._IN_PROCESS = None
    with pytest.raises(SystemExit) as exc:
        lock.automatic_operator_fidelity_lock()
    assert exc.value.code == 78
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "continuation_required"
    assert lock.os.environ["GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED"] == "0"


def test_digest_is_cryptographically_bound_to_literal_constraints() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["literal_constraints"][1] = "look sideways"
    errors = validate_operator_fidelity_lock(receipt)
    assert any("not bound to literal_constraints" in error for error in errors)


def test_durable_context_anchor_is_required() -> None:
    receipt = _receipt()
    words = [
        "hard work second answer last",
        "DO NOT LOOK DOWN - you look UP",
        "Powerful code elite excellence",
        "Function before governance",
    ]
    receipt["operator_fidelity"]["literal_constraints"] = words
    receipt["operator_fidelity"]["operator_words_digest"] = digest_operator_words(*words)
    errors = validate_operator_fidelity_lock(receipt)
    assert any("context first" in error for error in errors)


def test_durable_upward_anchor_is_required() -> None:
    receipt = _receipt()
    words = [
        "Context first hard work second answer last",
        "stay bounded",
        "Powerful code elite excellence",
        "Function before governance",
    ]
    receipt["operator_fidelity"]["literal_constraints"] = words
    receipt["operator_fidelity"]["operator_words_digest"] = digest_operator_words(*words)
    errors = validate_operator_fidelity_lock(receipt)
    assert any("look up" in error or "do not look down" in error for error in errors)


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
    assert any("non-operator-directed capability reduction" in error for error in errors)

    receipt["operator_fidelity"]["operator_directed_reduction"] = True
    assert validate_operator_fidelity_lock(receipt) == ()
