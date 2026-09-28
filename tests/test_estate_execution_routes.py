from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_estate_execution_routes.py"
SPEC = importlib.util.spec_from_file_location("validate_estate_execution_routes", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def policy() -> dict:
    return validator.load_policy(ROOT / "config" / "estate_execution_routes.json")


def test_live_policy_is_valid() -> None:
    assert validator.validate_policy(policy()) == []


def test_public_action_face_fails_without_explicit_admission() -> None:
    mutated = copy.deepcopy(policy())
    mutated["route_definitions"]["public_action_face"]["catalog_admission"] = "implicit"
    errors = validator.validate_policy(mutated)
    assert any("explicit_only" in error for error in errors)


def test_compute_fabric_fails_without_backend_promotion_gate() -> None:
    mutated = copy.deepcopy(policy())
    mutated["route_definitions"]["compute_fabric"]["requires_backend_promotion"] = False
    errors = validator.validate_policy(mutated)
    assert any("backend promotion" in error for error in errors)


def test_destructive_connector_mutation_requires_operator_approval() -> None:
    mutated = copy.deepcopy(policy())
    mutated["route_definitions"]["connector_worker_fabric"]["destructive_requires_operator_approval"] = False
    errors = validator.validate_policy(mutated)
    assert any("operator approval" in error for error in errors)


def test_private_github_actions_remains_exception_only() -> None:
    mutated = copy.deepcopy(policy())
    mutated["route_definitions"]["private_github_actions_exception"]["default_allowed"] = True
    errors = validator.validate_policy(mutated)
    assert any("default deny" in error for error in errors)


def test_static_policy_rejects_embedded_dynamic_workload_state() -> None:
    mutated = copy.deepcopy(policy())
    mutated["dynamic_workload_state"]["embedded_in_static_policy"] = True
    errors = validator.validate_policy(mutated)
    assert any("time-varying workload state" in error for error in errors)
