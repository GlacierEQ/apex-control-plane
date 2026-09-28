from __future__ import annotations

import operator_fidelity_preflight as module


def _valid_receipt() -> dict:
    return {"operator_fidelity": {}}


def test_automatic_preflight_revalidates_every_invocation(monkeypatch) -> None:
    module._IN_PROCESS = None
    calls: list[str] = []

    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.setenv("CASEY_BOOT_TASK", "first turn")
    monkeypatch.setattr(module, "receipt_from_environment", _valid_receipt)
    monkeypatch.setattr(
        module,
        "load_operator_fidelity_policy",
        lambda: {"schema_version": "test"},
    )

    def validate(policy, receipt, *, task=None):
        calls.append(str(task))
        return ()

    monkeypatch.setattr(module, "validate_operator_fidelity_receipt", validate)

    first = module.automatic_operator_fidelity_preflight()
    monkeypatch.setenv("CASEY_BOOT_TASK", "second turn")
    second = module.automatic_operator_fidelity_preflight()

    assert first is not None and first.ok is True
    assert second is not None and second.ok is True
    assert calls == ["first turn", "second turn"]


def test_verbatim_task_requires_verbatim_receipt_proof() -> None:
    policy = module.load_operator_fidelity_policy()
    receipt = {
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
            "operator_words_digest": "sha256:" + "1" * 64,
            "literal_constraints": ["quote me verbatim"],
            "operator_source_bindings": [
                {
                    "literal_index": 0,
                    "proposition_id": "p0",
                    "source_kind": "operator_message",
                    "source_ref": "file:operator-history.txt",
                    "source_sha256": "sha256:" + "2" * 64,
                    "span_start_byte": 0,
                    "span_end_byte": 17,
                    "span_sha256": "sha256:" + "3" * 64,
                    "temporal_context": "active",
                    "contradiction_state": "active",
                    "verification_state": "source_resolved",
                }
            ],
            "correction_present": False,
            "objective_function_reassessed": True,
            "corrections_applied": [],
            "correction_effect": "none",
            "operator_directed_reduction": False,
            "selected_path": {
                **policy["selected_path_requirements"],
                "capability_reduction": False,
                "functional_advance": "preserve literal source fidelity",
                "strongest_coherent_path": "recover exact source before verbatim response",
            },
            "next_ceiling": "continue with source-bound execution",
        }
    }

    errors = module.validate_operator_fidelity_receipt(
        policy,
        receipt,
        task="Give me my instructions VERBATIM",
    )

    assert any("verbatim_source_rehydrated" in error for error in errors)
    assert any("verbatim_paraphrase_substitution" in error for error in errors)
    assert any("verbatim_quote_spans_exact_source" in error for error in errors)


def test_verbatim_task_passes_when_receipt_proves_exact_source_fidelity() -> None:
    policy = module.load_operator_fidelity_policy()
    request = module.build_operator_fidelity_request(
        policy,
        task="Give me my instructions VERBATIM",
    )
    row = request["receipt_contract"]["operator_fidelity"]

    assert row["verbatim_request_active"] is True
    assert row["verbatim_source_rehydrated"] is True
    assert row["verbatim_paraphrase_substitution"] is False
    assert row["verbatim_quote_spans_exact_source"] is True
