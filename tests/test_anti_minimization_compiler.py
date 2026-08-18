from __future__ import annotations

import pytest

from anti_minimization_compiler import compile_upward, inspect_execution_text


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Take the smallest useful next step.", "SMALLEST_DEFAULT"),
        ("Ship the minimum viable implementation.", "MVP_DEFAULT"),
        ("Choose the safest slice for now.", "SAFEST_SLICE_DEFAULT"),
        ("Use a bounded scope as the delivery target.", "BOUNDED_SLICE_DEFAULT"),
        ("Pick the least capable implementation that passes.", "LEAST_CAPABILITY_DEFAULT"),
        ("Freeze architecture after the first green test.", "FREEZE_PRODUCT"),
        ("Enter a feature freeze as the delivery strategy.", "FEATURE_FREEZE_DELIVERY"),
        ("Governance first, implementation later.", "GOVERNANCE_FIRST"),
        (
            "Preserve the repository instead of advance it.",
            "PRESERVE_INSTEAD_OF_ACT",
        ),
    ],
)
def test_product_level_downward_routes_are_detected(text: str, code: str) -> None:
    findings = inspect_execution_text(text)
    assert any(finding.code == code for finding in findings)


def test_boolean_friendly_prose_still_gets_caught() -> None:
    text = (
        "This is the strongest coherent path. "
        "We will nevertheless take the safest slice and freeze architecture."
    )
    codes = {finding.code for finding in inspect_execution_text(text)}
    assert "SAFEST_SLICE_DEFAULT" in codes
    assert "FREEZE_PRODUCT" in codes


@pytest.mark.parametrize(
    "text",
    [
        "Use least privilege for the deployment token.",
        "Build a minimal reproducer for the race condition.",
        "Capture a known-good rollback checkpoint before mutation.",
        "Use minimum necessary permissions for the worker identity.",
        "Perform fault isolation on the failing adapter.",
    ],
)
def test_local_quality_narrowing_is_preserved(text: str) -> None:
    assert inspect_execution_text(text) == ()


def test_explicit_operator_directed_reduction_is_authoritative() -> None:
    assert inspect_execution_text(
        "Freeze architecture and take the smallest implementation.",
        operator_directed_reduction=True,
    ) == ()


def test_compile_upward_repairs_product_level_minimization() -> None:
    compiled = compile_upward(
        "Take the smallest useful step. Freeze architecture. Governance first."
    )
    assert "largest coherent executable tranche" in compiled
    assert "continue evolution" in compiled
    assert "governance serve functional advance" in compiled
    assert inspect_execution_text(compiled) == ()


def test_compile_upward_does_not_rewrite_security_exception() -> None:
    text = "Use least privilege for the GitHub token."
    assert compile_upward(text) == text
