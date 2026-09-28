from __future__ import annotations

import json
from pathlib import Path

from apex_enforced_startup import load_apex_policy
from operator_working_model import load_operator_working_model


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "config" / "continuous_maintenance_execution_contract.json"


def _maintenance_contract() -> dict:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_loaded_worker_contract_binds_continuous_maintenance_execution() -> None:
    policy = load_apex_policy()
    model = load_operator_working_model(policy)
    worker = model["worker_execution_contract"]
    maintenance = worker["continuous_maintenance_execution"]

    assert maintenance["contract_path"] == "config/continuous_maintenance_execution_contract.json"
    assert maintenance["required_for_recurring_and_continuation_dependent_execution"] is True
    assert maintenance["maintenance_repair_and_strengthening_precede_reporting"] is True
    assert maintenance["recover_prior_verified_gain_before_selecting_work"] is True
    assert maintenance["repair_recoverable_faults_same_run"] is True
    assert maintenance["reconcile_material_drift_same_run"] is True
    assert maintenance["strengthen_weak_invariants_when_evidence_backed"] is True
    assert maintenance["isolate_partial_failures_and_continue_unaffected_work"] is True
    assert maintenance["provider_native_verification_required_for_provider_state"] is True
    assert maintenance["readback_required_after_mutation_when_available"] is True
    assert maintenance["healthy_component_is_not_global_stop_condition"] is True
    assert maintenance["no_forced_churn"] is True
    assert maintenance["no_activity_theater"] is True
    assert maintenance["operator_intervention_only_after_system_side_paths_exhausted"] is True
    assert maintenance["rerank_after_every_material_state_change"] is True
    assert worker["startup_receipt_requirements"]["continuous_maintenance_execution_loaded"] is True


def test_continuous_maintenance_contract_preserves_action_economy_and_truth_state() -> None:
    contract = _maintenance_contract()

    assert contract["authority"] == "operator_intent"
    assert contract["objective"] == "continuous_useful_state_improvement"
    assert contract["requirements"]["maintenance_first"] is True
    assert contract["requirements"]["no_forced_churn"] is True
    assert contract["requirements"]["no_activity_theater"] is True
    assert contract["requirements"]["healthy_component_is_not_a_global_stop_condition"] is True
    assert contract["requirements"]["operator_intervention_only_after_system_side_paths_are_exhausted"] is True

    assert contract["state_semantics"]["draft_is_not_sent"] is True
    assert contract["state_semantics"]["sent_is_not_delivered"] is True
    assert contract["state_semantics"]["delivered_is_not_acknowledged"] is True
    assert contract["state_semantics"]["attempt_is_not_success"] is True
    assert contract["state_semantics"]["pending_is_not_completed"] is True
    assert contract["state_semantics"]["provider_native_receipts_control_provider_state"] is True

    rejected = set(contract["action_economy"]["reject"])
    assert {
        "KNOWN_STATE",
        "REPEATED_DIAGNOSIS",
        "SUMMARY_ONLY_DELTA",
        "FRAMEWORK_REBUILD",
        "NO_DOWNSTREAM_DELTA",
        "COSMETIC_CHURN",
    } <= rejected


def test_continuous_maintenance_contract_preserves_authority_topology() -> None:
    contract = _maintenance_contract()
    compatibility = contract["compatibility"]

    assert compatibility["lane_specific_authority_boundaries_remain_binding"] is True
    assert compatibility["external_actions_still_require_applicable_authority"] is True
    assert compatibility["legal_case_truth_is_not_mutated_by_platform_maintenance"] is True
    assert compatibility["source_specific_authority_is_preserved"] is True
    assert compatibility["no_single_provider_becomes_universal_truth_by_convenience"] is True
