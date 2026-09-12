"""Fail-closed runtime preflight for strict executable-frontier authority.

Generic source bytes and provider-native readback bytes resolve through separate
roots. A provider-looking URI in the generic source root cannot authorize
provider execution.
"""
from __future__ import annotations

import os
from pathlib import Path

from executable_frontier_authority import FrontierAuthorizationResult
from prime_directive_boot import receipt_from_environment
from strict_executable_frontier_authority import (
    validate_strict_executable_frontier_authority,
)


def _resolve_beneath(root_value: str, relative: str, *, label: str) -> bytes:
    if not root_value.strip():
        raise FileNotFoundError(f"{label} root is not set")
    root = Path(root_value).expanduser().resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} reference escapes root") from exc
    return resolved.read_bytes()


def _resolve_frontier_source(source_ref: str) -> bytes:
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("frontier source_ref must be non-empty")
    if not source_ref.startswith("file:"):
        raise ValueError("frontier source_ref must use file: scheme")
    relative = source_ref.removeprefix("file:").lstrip("/")
    if not relative:
        raise ValueError("frontier source_ref is empty")
    return _resolve_beneath(
        os.getenv("GLACIEREQ_FRONTIER_SOURCE_ROOT", ""),
        relative,
        label="frontier source",
    )


def _resolve_provider_readback(provider: str, source_ref: str) -> bytes:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be non-empty")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("provider source_ref must be non-empty")
    prefix = f"provider://{provider}/"
    if not source_ref.startswith(prefix):
        raise ValueError("provider source_ref does not match provider trust root")
    relative = source_ref.removeprefix(prefix).lstrip("/")
    if not relative:
        raise ValueError("provider source_ref is empty")

    provider_root_value = os.getenv("GLACIEREQ_PROVIDER_READBACK_ROOT", "")
    if not provider_root_value.strip():
        raise FileNotFoundError("provider readback root is not set")
    provider_root = Path(provider_root_value).expanduser().resolve() / provider
    return _resolve_beneath(
        str(provider_root),
        relative,
        label=f"provider readback {provider}",
    )


def validate_runtime_strict_frontier() -> FrontierAuthorizationResult:
    """Require the live boot receipt to pass strict frontier authority."""
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
        provider_resolver=_resolve_provider_readback,
    )
