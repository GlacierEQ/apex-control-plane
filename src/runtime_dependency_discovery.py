"""Automatic runtime discovery of execution dependencies.

The runtime, not the caller, owns dependency discovery. A caller-supplied
execution_claim_ids field is derivative projection only. This module resolves
source/provider material already bound into the turn and derives execution claim
identities from those bytes.

When the stronger dependency-enumeration artifact is present, it is authoritative
for discovery and is validated independently. A conservative direct-reference
fallback exists for partially migrated receipts so all-turn runtime can still
recover provider/source claim identities without trusting assistant prose.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from execution_dependency_enumerator_authority import validate_dependency_enumeration

SourceResolver = Callable[[str], bytes]

_SKIP_CONTAINERS = {
    "assistant_summary",
    "dependency_completeness_verification",
    "entailment_verifications",
    "execution_claim_ids",
    "memory_summary",
    "profile",
    "working_model",
}


@dataclass(frozen=True, slots=True)
class RuntimeDependencyDiscoveryResult:
    ok: bool
    status: str
    execution_claim_ids: tuple[str, ...]
    resolved_refs: tuple[str, ...]
    unresolved_refs: tuple[str, ...]
    errors: tuple[str, ...] = ()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _collect_refs(value: Any, found: set[str], *, container_key: str | None = None) -> None:
    if container_key in _SKIP_CONTAINERS:
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _SKIP_CONTAINERS:
                continue
            if key.endswith("_ref") and _nonempty(nested):
                found.add(str(nested))
                continue
            if key.endswith("_refs") and isinstance(nested, list):
                for item in nested:
                    if _nonempty(item):
                        found.add(str(item))
                continue
            _collect_refs(nested, found, container_key=str(key))
    elif isinstance(value, list):
        for nested in value:
            _collect_refs(nested, found, container_key=container_key)


def _collect_claim_ids(value: Any, found: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "execution_claim_id" and _nonempty(nested):
                found.add(str(nested))
            elif key in {
                "execution_claim_ids",
                "required_execution_claim_ids",
                "candidate_execution_claim_ids",
            } and isinstance(nested, list):
                for item in nested:
                    if _nonempty(item):
                        found.add(str(item))
            else:
                _collect_claim_ids(nested, found)
    elif isinstance(value, list):
        for nested in value:
            _collect_claim_ids(nested, found)


def discover_execution_dependencies(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> RuntimeDependencyDiscoveryResult:
    """Derive execution dependencies from resolved turn material.

    Caller-authored execution_claim_ids are intentionally ignored as authority.
    """
    row = receipt.get("frontier_authority")
    if not isinstance(row, Mapping):
        return RuntimeDependencyDiscoveryResult(
            False,
            "DEPENDENCY_DISCOVERY_UNRESOLVED",
            (),
            (),
            (),
            ("frontier_authority must be an object",),
        )

    enumeration = row.get("dependency_enumeration")
    frontier_id = row.get("frontier_id")
    if isinstance(enumeration, Mapping) and _nonempty(frontier_id):
        enumerated = validate_dependency_enumeration(
            enumeration,
            resolver=resolver,
            expected_frontier_id=str(frontier_id),
            declared_execution_claim_ids=None,
        )
        if enumerated.ok:
            return RuntimeDependencyDiscoveryResult(
                True,
                "DEPENDENCY_DISCOVERY_VERIFIED",
                enumerated.required_execution_claim_ids,
                (),
                (),
                (),
            )
        return RuntimeDependencyDiscoveryResult(
            False,
            "DEPENDENCY_DISCOVERY_UNRESOLVED",
            enumerated.required_execution_claim_ids,
            (),
            (),
            enumerated.errors,
        )

    refs: set[str] = set()
    _collect_refs(row, refs)
    claims: set[str] = set()
    resolved: list[str] = []
    unresolved: list[str] = []

    for ref in sorted(refs):
        try:
            payload = resolver(ref)
        except Exception:  # noqa: BLE001 - preserve unresolved source/provider state
            unresolved.append(ref)
            continue
        if not isinstance(payload, bytes):
            unresolved.append(ref)
            continue
        resolved.append(ref)
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        _collect_claim_ids(parsed, claims)

    return RuntimeDependencyDiscoveryResult(
        not unresolved,
        "DEPENDENCY_DISCOVERY_VERIFIED" if not unresolved else "DEPENDENCY_DISCOVERY_PARTIAL",
        tuple(sorted(claims)),
        tuple(resolved),
        tuple(unresolved),
        (),
    )
