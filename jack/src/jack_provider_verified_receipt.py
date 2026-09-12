"""Provider-verified completion boundary for Jack execution receipts.

The underlying Jack gate now refuses COMPLETE unless an independent execution-
evidence validator is injected.  This module supplies that validator from the
provider-readback authority; string receipt references remain routing hints only.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from execution_evidence_authority import EvidenceResolver, validate_execution_evidence
from jack_relentless_gate import validate_receipt


def validate_provider_verified_receipt(
    receipt: Mapping[str, Any], *, resolver: EvidenceResolver
) -> None:
    """Fail closed unless COMPLETE is backed by independent provider proof."""

    def verify_execution_evidence(evidence: Mapping[str, object]) -> None:
        result = validate_execution_evidence(evidence, resolver=resolver)
        if not result.ok:
            raise ValueError(
                "independent execution evidence failed: " + "; ".join(result.errors)
            )

    validate_receipt(
        receipt,
        execution_evidence_validator=verify_execution_evidence,
    )
