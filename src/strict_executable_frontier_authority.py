"""Composite executable-frontier authority with mandatory dependency enumeration.

This boundary composes the existing source/entailment/execution-lineage frontier
validator with the independently materialized execution-dependency enumerator,
material-input collector attestation, and content-addressed verifier identity.
Consumers can migrate to this entry point without weakening existing frontier
authority while closing self-attested completeness, collector-identity, and
verifier-label spoofing gaps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from executable_frontier_authority import (
    FrontierAuthorizationResult,
    SourceResolver,
    validate_executable_frontier_authority,
)
from execution_dependency_enumerator_authority import validate_dependency_enumeration
from material_input_collector_authority import validate_material_input_collector_authority
from verifier_identity_authority import validate_verifier_identity_authority


def validate_strict_executable_frontier_authority(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> FrontierAuthorizationResult:
    """Authorize only when base, enumeration, collector, and verifier identity agree."""
    base = validate_executable_frontier_authority(receipt, resolver=resolver)
    if not base.ok:
        return base

    row = receipt.get("frontier_authority")
    if not isinstance(row, Mapping):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_required",
            ("frontier_authority must be an object",),
        )

    enumeration = row.get("dependency_enumeration")
    if not isinstance(enumeration, Mapping):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            (
                "frontier_authority.dependency_enumeration must contain independently resolved enumeration evidence",
            ),
        )

    frontier_id = row.get("frontier_id")
    execution_claim_ids = row.get("execution_claim_ids", [])
    if not isinstance(frontier_id, str) or not frontier_id:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            ("frontier_authority.frontier_id must be non-empty",),
        )
    if not isinstance(execution_claim_ids, list):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            ("frontier_authority.execution_claim_ids must be an array",),
        )

    enumeration_result = validate_dependency_enumeration(
        enumeration,
        resolver=resolver,
        expected_frontier_id=frontier_id,
        declared_execution_claim_ids=execution_claim_ids,
    )
    if not enumeration_result.ok:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    [
                        f"frontier_authority.dependency_enumeration: {error}"
                        for error in enumeration_result.errors
                    ]
                )
            ),
        )

    collector_result = validate_material_input_collector_authority(
        row, resolver=resolver
    )
    if not collector_result.ok:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    [
                        f"frontier_authority.material_input_collector_attestation: {error}"
                        for error in collector_result.errors
                    ]
                )
            ),
        )

    verifier_result = validate_verifier_identity_authority(row, resolver=resolver)
    if not verifier_result.ok:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    [
                        f"frontier_authority.verifier_identity_attestation: {error}"
                        for error in verifier_result.errors
                    ]
                )
            ),
        )

    return FrontierAuthorizationResult(True, "frontier_authorized", ())
