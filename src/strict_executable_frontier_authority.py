"""Composite executable-frontier authority with mandatory dependency enumeration.

This boundary composes the existing source/entailment/execution-lineage frontier
validator with the independently materialized execution-dependency enumerator.
Consumers can migrate to this entry point without weakening the existing
frontier authority while closing the self-attested completeness gap.
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


def validate_strict_executable_frontier_authority(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> FrontierAuthorizationResult:
    """Authorize only when base frontier authority and dependency enumeration agree."""
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

    result = validate_dependency_enumeration(
        enumeration,
        resolver=resolver,
        expected_frontier_id=frontier_id,
        declared_execution_claim_ids=execution_claim_ids,
    )
    if not result.ok:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    [
                        f"frontier_authority.dependency_enumeration: {error}"
                        for error in result.errors
                    ]
                )
            ),
        )

    return FrontierAuthorizationResult(True, "frontier_authorized", ())
