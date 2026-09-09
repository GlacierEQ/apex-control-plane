from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_estate_execution_routes.py"
SPEC = importlib.util.spec_from_file_location("validate_estate_execution_routes", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class EstateExecutionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = validator.load_registry(ROOT / "config" / "estate_execution_routes.json")

    def test_live_registry_is_valid(self) -> None:
        self.assertEqual([], validator.validate_registry(self.registry))

    def test_destructive_workload_requires_operator_approval(self) -> None:
        mutated = copy.deepcopy(self.registry)
        workload = next(
            item for item in mutated["initial_reconciliation"] if item["destructive"]
        )
        workload["operator_approval_required"] = False
        errors = validator.validate_registry(mutated)
        self.assertTrue(any("must require operator approval" in error for error in errors))

    def test_public_action_face_requires_explicit_catalog_admission(self) -> None:
        mutated = copy.deepcopy(self.registry)
        workload = mutated["initial_reconciliation"][0]
        workload["target_route"] = "public_action_face"
        errors = validator.validate_registry(mutated)
        self.assertTrue(any("catalog_admission='explicit'" in error for error in errors))

    def test_source_cannot_be_disabled_before_target_verification(self) -> None:
        mutated = copy.deepcopy(self.registry)
        workload = mutated["initial_reconciliation"][0]
        workload["migration_state"] = "source_disabled"
        errors = validator.validate_registry(mutated)
        self.assertTrue(any("before target_route_verified=true" in error for error in errors))

    def test_private_github_actions_cannot_become_default_target(self) -> None:
        mutated = copy.deepcopy(self.registry)
        workload = mutated["initial_reconciliation"][0]
        workload["target_route"] = "private_github_actions_exception"
        errors = validator.validate_registry(mutated)
        self.assertTrue(any("requires exception_reason" in error for error in errors))
        self.assertTrue(any("requires exception_review_at" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
