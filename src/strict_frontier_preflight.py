"""Fail-closed runtime preflight for strict executable-frontier authority.

This module is deliberately small: it adapts the provider/source-backed boot
receipt into the strict frontier authority boundary without creating a new
source of truth.  Source bytes remain outside the receipt and are resolved from
the explicitly mounted frontier source root.
"""
from __future__ import annotations

import os
from pathlib import Path

from executable_frontier_authority import FrontierAuthorizationResult
from prime_directive_boot import receipt_from_environment
from strict_executable_frontier_authority import (
    validate_strict_executable_frontier_authority,
)


def _resolve_frontier_source(source_ref: str) -> bytes:
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("frontier source_ref must be non-empty")
    if not source_ref.startswith("file:"):
        raise ValueError("frontier source_ref must use file: scheme")

    root_value = os.getenv("GLACIEREQ_FRONTIER_SOURCE_ROOT", "").strip()
    if not root_value:
        raise FileNotFoundError("GLACIEREQ_FRONTIER_SOURCE_ROOT is not set")
    root = Path(root_value).expanduser().resolve()
    relative = source_ref.removeprefix("file:").lstrip("/")
    if not relative:
        raise ValueError("frontier source_ref is empty")

    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("frontier source_ref escapes source root") from exc
    return resolved.read_bytes()


def validate_runtime_strict_frontier() -> FrontierAuthorizationResult:
    """Require the live boot receipt to pass strict frontier authority.

    Missing receipts are unresolved rather than silently downgraded to an empty
    dependency set.  The strict validator then composes source binding,
    entailment, current execution lineage, dependency-completeness evidence, and
    independently materialized dependency enumeration.
    """
    receipt = receipt_from_environment()
    if receipt is None:
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_unresolved",
            ("strict frontier preflight requires a boot receipt",),
        )
    return validate_strict_executable_frontier_authority(
        receipt,
        resolver=_resolve_frontier_source,
    )
