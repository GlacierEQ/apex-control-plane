from __future__ import annotations

import hashlib
from pathlib import Path

import operator_fidelity_lock as lock
from operator_fidelity_lock import validate_operator_fidelity_lock
from operator_fidelity_preflight import digest_operator_words

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "operator_source_fixture.txt"


def _sha256_ref(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _source_bindings(words: list[str]) -> list[dict]:
    source = FIXTURE_PATH.read_bytes()
    bindings: list[dict] = []
    cursor = 0
    for index, word in enumerate(words):
        encoded = word.encode("utf-8")
        start = source.index(encoded, cursor)
        end = start + len(encoded)
        cursor = end
        bindings.append(
            {
                "literal_index": index,
                "proposition_id": f"test-operator-proposition-{index}",
                "source_kind": "operator_message",
                "source_ref": f"file:{FIXTURE_PATH.name}",
                "source_sha256": _sha256_ref(source),
                "span_start_byte": start,
                "span_end_byte": end,
                "span_sha256": _sha256_ref(source[start:end]),
                "temporal_context": "synthetic-test-fixture-only",
                "contradiction_state": "active",
                "verification_state": "source_resolved",
            }
        )
    return bindings


def _receipt() -> dict:
    words = [
        "Context first hard work second answer last",
        "DO NOT LOOK DOWN - you look UP",
        "Powerful code elite excellence",
        "Function before governance; governance serves function",
    ]
    lock.os.environ["GLACIEREQ_OPERATOR_SOURCE_ROOT"] = str(FIXTURE_PATH.parent)
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
            "improvement_dominates_prior_valid_state": True,
            "narrative_plurality_preserved": True,
            "operator_words_digest": digest_operator_words(*words),
            "literal_constraints": words,
            "operator_source_bindings": _source_bindings(words),
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
                "inspection_scope_expansion": False,
                "operator_owned_asset_identity_preserved": True,
                "improvement_dominates_prior_valid_state": True,
                "simplification_as_objective": False,
                "narrative_plurality_preserved": True,
                "audience_curation_may_hide_but_not_erase": True,
                "preserves_prior_valid_gain": True,
                "maximum_coherent_advance": True,
                "pro_code_elite_humanized_engineered": True,
                "functional_advance": "source-bound fidelity evidence with semantic inspection",
                "strongest_coherent_path": (
                    "continue known executable frontiers while fidelity findings are repaired, "
                    "then reverify without redefining the mission"
                ),
            },
            "next_ceiling": "propagate execution-uplift semantics across every entrypoint",
        }
    }


def test_valid_lock_receipt_passes() -> None:
    assert validate_operator_fidelity_lock(_receipt()) == ()


def test_request_mode_without_receipt_yields_uplift_and_preserves_execution(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "request")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    monkeypatch.delenv("GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED", raising=False)
    lock._IN_PROCESS = None

    validation = lock.automatic_operator_fidelity_lock()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "uplift_required"
    assert "receipt" in validation.errors[0]
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "uplift_required"
    assert "GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED" not in lock.os.environ


def test_strict_compatibility_mode_without_receipt_yields_uplift_not_process_death(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    lock._IN_PROCESS = None

    validation = lock.automatic_operator_fidelity_lock()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "uplift_required"
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "uplift_required"


def test_disable_flag_records_uplift_without_terminating_runtime(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(lock, "_testing", lambda: False)
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.setenv("CASEY_AUTO_BOOT_DISABLE", "1")
    monkeypatch.setenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", str(tmp_path))
    lock._IN_PROCESS = None

    validation = lock.automatic_operator_fidelity_lock()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "uplift_required"
    assert any("CASEY_AUTO_BOOT_DISABLE" in error for error in validation.errors)
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "uplift_required"
    assert list(tmp_path.glob("operator_fidelity_lock-*.json"))


def test_off_mode_records_uplift_without_terminating_runtime(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(lock, "_testing", lambda: False)
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "off")
    monkeypatch.delenv("CASEY_AUTO_BOOT_DISABLE", raising=False)
    monkeypatch.setenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", str(tmp_path))
    lock._IN_PROCESS = None

    validation = lock.automatic_operator_fidelity_lock()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "uplift_required"
    assert any("CASEY_AUTO_BOOT_MODE=off" in error for error in validation.errors)
    assert lock.os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] == "uplift_required"
    assert list(tmp_path.glob("operator_fidelity_lock-*.json"))


def test_digest_is_cryptographically_bound_to_literal_constraints() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["literal_constraints"][1] = "look sideways"
    errors = validate_operator_fidelity_lock(receipt)
    assert any("not bound to literal_constraints" in error for error in errors)


def test_source_binding_is_required_even_when_receipt_digest_is_self_consistent() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"].pop("operator_source_bindings")
    errors = validate_operator_fidelity_lock(receipt)
    assert any("independently bind every literal constraint" in error for error in errors)


def test_forged_span_digest_is_detected_for_repair() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["operator_source_bindings"][0]["span_sha256"] = (
        "sha256:" + "0" * 64
    )
    errors = validate_operator_fidelity_lock(receipt)
    assert any("span_sha256 does not match" in error for error in errors)


def test_source_span_must_exactly_equal_literal_constraint() -> None:
    receipt = _receipt()
    binding = receipt["operator_fidelity"]["operator_source_bindings"][1]
    binding["span_start_byte"] = 0
    binding["span_end_byte"] = len(
        receipt["operator_fidelity"]["literal_constraints"][0].encode("utf-8")
    )
    source = FIXTURE_PATH.read_bytes()
    binding["span_sha256"] = _sha256_ref(
        source[binding["span_start_byte"] : binding["span_end_byte"]]
    )
    errors = validate_operator_fidelity_lock(receipt)
    assert any("does not exactly equal literal_constraints[1]" in error for error in errors)


def test_derivative_working_model_cannot_substitute_for_verbatim_operator_words() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["operator_source_bindings"][0]["source_kind"] = (
        "working_model"
    )
    errors = validate_operator_fidelity_lock(receipt)
    assert any("derivative" in error and "cannot authorize" in error for error in errors)


def test_retrieval_failure_is_unresolved_readback_not_evidence_absence(monkeypatch) -> None:
    receipt = _receipt()
    monkeypatch.delenv("GLACIEREQ_OPERATOR_SOURCE_ROOT", raising=False)
    errors = validate_operator_fidelity_lock(receipt)
    assert any("source readback unresolved" in error for error in errors)
    assert not any("no evidence" in error.lower() for error in errors)


def test_superseded_source_cannot_silently_remain_authoritative() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["operator_source_bindings"][0][
        "contradiction_state"
    ] = "superseded"
    errors = validate_operator_fidelity_lock(receipt)
    assert any("superseded/conflicted source" in error for error in errors)


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


def test_minimum_scope_and_governance_first_are_flagged_for_repair() -> None:
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

def test_better_not_simpler_dominance_is_machine_bound() -> None:
    receipt = _receipt()
    receipt["operator_fidelity"]["improvement_dominates_prior_valid_state"] = False
    receipt["operator_fidelity"]["selected_path"]["simplification_as_objective"] = True
    errors = validate_operator_fidelity_lock(receipt)
    assert any("improvement_dominates_prior_valid_state" in error for error in errors)
    assert any("simplification_as_objective" in error for error in errors)


def test_lock_revalidates_every_invocation(monkeypatch) -> None:
    lock._IN_PROCESS = None
    calls: list[str] = []
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.setenv("CASEY_BOOT_TASK", "first lock turn")
    monkeypatch.setattr(lock, "receipt_from_environment", _receipt)

    def validate(receipt, *, task=None):
        calls.append(str(task))
        return ()

    monkeypatch.setattr(lock, "validate_operator_fidelity_lock", validate)

    first = lock.automatic_operator_fidelity_lock()
    monkeypatch.setenv("CASEY_BOOT_TASK", "second lock turn")
    second = lock.automatic_operator_fidelity_lock()

    assert first is not None and first.ok is True
    assert second is not None and second.ok is True
    assert calls == ["first lock turn", "second lock turn"]


def test_lock_applies_verbatim_task_requirements() -> None:
    receipt = _receipt()
    errors = validate_operator_fidelity_lock(
        receipt,
        task="Return the Operator instruction VERBATIM",
    )
    assert any("verbatim_request_active" in error for error in errors)
    assert any("verbatim_source_rehydrated" in error for error in errors)
