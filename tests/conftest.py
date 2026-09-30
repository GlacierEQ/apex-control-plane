"""Shared pytest fixtures for active runtime tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _arm_strict_frontier_for_legacy_strong_boot_tests(request, monkeypatch):
    """Supply the legacy strong-boot harness with its new prerequisite proof.

    `test_apex_strong_boot.py` already synthesizes every prerequisite proof
    object rather than constructing a provider-backed boot receipt. The strict
    frontier cutover has dedicated adversarial tests, so this compatibility
    fixture gives only that legacy harness an explicit authorized proof. No
    production path or strict-frontier test is bypassed.
    """
    if request.node.path.name != "test_apex_strong_boot.py":
        return

    import apex_strong_boot as boot
    from executable_frontier_authority import FrontierAuthorizationResult

    monkeypatch.setattr(
        boot,
        "validate_runtime_strict_frontier",
        lambda: FrontierAuthorizationResult(True, "frontier_authorized", ()),
    )
