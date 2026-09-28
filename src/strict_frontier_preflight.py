"""Fail-closed runtime preflight for strict executable-frontier authority.

This adapter keeps source-bearing bytes and provider readback bytes in separate
mounted trust roots. A provider-scoped reference can never fall through to the
ordinary source root merely because a generic resolver is used downstream.
"""
from __future__ import annotations

import os
from pathlib import Path

from executable_frontier_authority import FrontierAuthorizationResult
from prime_directive_boot import receipt_from_environment
from strict_executable_frontier_authority import (
    validate_strict_executable_frontier_authority,
)


def _root_from_env(name: str) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        raise FileNotFoundError(f"{name} is not set")
    return Path(value).expanduser().resolve()


def _read_beneath(root: Path, relative: str, *, label: str) -> bytes:
    relative = relative.lstrip("/")
    if not relative:
        raise ValueError(f"{label} reference is empty")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} reference escapes configured root") from exc
    return resolved.read_bytes()


def _resolve_frontier_source(source_ref: str) -> bytes:
    """Resolve source and provider evidence without crossing authority roots."""
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("frontier source_ref must be non-empty")

    if source_ref.startswith("file:"):
        root = _root_from_env("GLACIEREQ_FRONTIER_SOURCE_ROOT")
        return _read_beneath(
            root,
            source_ref.removeprefix("file:"),
            label="frontier source",
        )

    if source_ref.startswith("provider://"):
        root = _root_from_env("GLACIEREQ_PROVIDER_READBACK_ROOT")
        provider_relative = source_ref.removeprefix("provider://")
        return _read_beneath(
            root,
            provider_relative,
            label="provider readback",
        )

    if source_ref.startswith("provider-output:"):
        root = _root_from_env("GLACIEREQ_PROVIDER_READBACK_ROOT")
        output_relative = source_ref.removeprefix("provider-output:")
        return _read_beneath(
            root / "outputs",
            output_relative,
            label="provider output",
        )

    raise ValueError(
        "frontier source_ref must use file:, provider://, or provider-output: scheme"
    )


def validate_runtime_strict_frontier() -> FrontierAuthorizationResult:
    """Require the live boot receipt to pass strict frontier authority.

    Missing receipts are unresolved rather than silently downgraded. Source
    material and provider readback material are resolved from distinct roots so
    neither namespace can silently substitute for the other.
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
