#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("enforce.py")
SPEC = importlib.util.spec_from_file_location(
    "apex_non_regression_enforce", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load enforcement module: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DownwardDirectiveClassifierTests(unittest.TestCase):
    def assert_rejected(self, text: str) -> None:
        self.assertIsNotNone(
            MODULE.classify_downward_directive(text),
            msg=f"expected downward directive rejection: {text!r}",
        )

    def assert_allowed(self, text: str) -> None:
        self.assertIsNone(
            MODULE.classify_downward_directive(text),
            msg=f"expected permitted context: {text!r}",
        )

    def test_rejects_smallest_default(self) -> None:
        self.assert_rejected("Always use the smallest useful next step.")

    def test_rejects_minimum_viable_default(self) -> None:
        self.assert_rejected("Default to a minimum viable implementation.")

    def test_rejects_least_capable_target(self) -> None:
        self.assert_rejected("Choose the least capable implementation that passes.")

    def test_rejects_architecture_freeze(self) -> None:
        self.assert_rejected("Freeze architecture after the first passing build.")

    def test_allows_explicit_prohibition(self) -> None:
        self.assert_allowed("Do not default to the smallest useful next step.")

    def test_allows_forbidden_signature_vocabulary(self) -> None:
        self.assert_allowed("FORBIDDEN: freeze scope")

    def test_allows_diagnostic_isolation(self) -> None:
        self.assert_allowed(
            "Use the smallest useful slice only to isolate this failing test."
        )

    def test_allows_least_privilege_security(self) -> None:
        self.assert_allowed("Always enforce least privilege for runtime credentials.")

    def test_allows_rollback_checkpoint(self) -> None:
        self.assert_allowed(
            "Freeze implementation only as a known-good rollback checkpoint while evolution continues."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
