"""Composite executable-frontier evidence validator with runtime-owned dependency discovery.

The runtime derives execution dependencies from independently resolved material
inputs before base frontier authorization. Caller-supplied execution_claim_ids
are treated as derivative projection only and are never the authority source.

This boundary composes source/entailment/execution-lineage frontier validation,
automatic dependency discovery, material-input collector attestation,
content-addressed verifier identity, and provider-readback proof that the bound
verifier implementation actually ran.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from executable_frontier_authority import (
    FrontierAuthorizationResult,
    SourceResolver,
    validate_executable_frontier_authority,
)
from material_input_collector_authority import validate_material_input_collector_authority
from runtime_dependency_discovery import discover_execution_dependencies
from verifier_execution_authority import validate_verifier_execution_authority
from verifier_identity_authority import validate_verifier_identity_authority


def validate_strict_executable_frontier_authority(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> FrontierAuthorizationResult:
    """Authorize from runtime-derived dependencies, never caller dependency claims."""
    row = receipt.get("frontier_authority")
    if not isinstance(row, Mapping):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_required",
            ("frontier_authority must be an object",),
        )

    discovery = discover_execution_dependencies(receipt, resolver=resolver)
    if not discovery.ok:
        details = list(discovery.errors)
        details.extend(
            f"source/provider readback unresolved: {ref}"
            for ref in discovery.unresolved_refs
        )
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    f"frontier_authority.runtime_dependency_discovery: {item}"
                    for item in details
                )
            ),
        )

    # Normalize a private copy so the caller's declared dependency list cannot
    # control authorization. The runtime-derived set is the only set presented
    # to downstream frontier, lineage, completeness, and entailment validation.
    normalized_receipt = deepcopy(dict(receipt))
    normalized_row = normalized_receipt.get("frontier_authority")
    if not isinstance(normalized_row, dict):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_required",
            ("frontier_authority must be a mutable object after normalization",),
        )
    normalized_row["execution_claim_ids"] = list(discovery.execution_claim_ids)

    base = validate_executable_frontier_authority(
        normalized_receipt, resolver=resolver
    )
    if not base.ok:
        return base

    frontier_id = normalized_row.get("frontier_id")
    if not isinstance(frontier_id, str) or not frontier_id:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            ("frontier_authority.frontier_id must be non-empty",),
        )

    collector_result = validate_material_input_collector_authority(
        normalized_row, resolver=resolver
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

    verifier_result = validate_verifier_identity_authority(
        normalized_row, resolver=resolver
    )
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

    execution_result = validate_verifier_execution_authority(
        normalized_row, resolver=resolver
    )
    if not execution_result.ok:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            tuple(
                dict.fromkeys(
                    [
                        f"frontier_authority.verifier_execution_attestation: {error}"
                        for error in execution_result.errors
                    ]
                )
            ),
        )

    return FrontierAuthorizationResult(True, "frontier_authorized", ())
