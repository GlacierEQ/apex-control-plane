"""PRIME established-state guard.

This module is a counter-engineered semantic primitive for GlacierEQ PRIME
machinery. It preserves verification/falsification power while preventing
generic uncertainty or contradiction-hunting from resetting established state.

It does not alter platform safety, security, provider, or access-control rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ConflictDecision:
    blocks: bool
    reason: str
    affected_dimensions: tuple[str, ...] = ()


def _receipt_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    prefix, sep, locator = value.strip().partition(":")
    return bool(sep and prefix.strip() and locator.strip())


def evaluate_conflict(
    *,
    status: str,
    positive_conflict: Mapping[str, Any] | None = None,
) -> ConflictDecision:
    """Return whether a contradiction may block the current action.

    Legacy/open/generic contradiction labels are deliberately non-blocking.
    A blocker exists only when a positive, source-bearing, materially relevant
    conflict is supplied.
    """
    normalized = str(status or "").strip().upper()
    if normalized != "POSITIVE_CONFLICT_BLOCKER":
        return ConflictDecision(
            blocks=False,
            reason="no positive source-bearing material conflict",
        )

    row = positive_conflict if isinstance(positive_conflict, Mapping) else {}
    if row.get("positive_conflict") is not True:
        return ConflictDecision(False, "positive_conflict=true is required")
    if not _receipt_ref(row.get("source_ref")):
        return ConflictDecision(False, "source_ref receipt is required")
    if not _receipt_ref(row.get("conflicts_with_source_ref")):
        return ConflictDecision(False, "conflicts_with_source_ref receipt is required")
    if row.get("material_to_current_action") is not True:
        return ConflictDecision(False, "conflict is not material to current action")

    dims = row.get("affected_dimensions")
    if not isinstance(dims, list) or not dims or not all(
        isinstance(item, str) and item.strip() for item in dims
    ):
        return ConflictDecision(False, "affected_dimensions are required")

    return ConflictDecision(
        blocks=True,
        reason="positive source-bearing conflict affects current action",
        affected_dimensions=tuple(item.strip() for item in dims),
    )


def should_reopen_established_state(
    *,
    established: bool,
    operator_directed_reexamination: bool = False,
    conflict: ConflictDecision | None = None,
) -> bool:
    """Established state reopens only by Operator direction or real conflict."""
    if not established:
        return True
    if operator_directed_reexamination:
        return True
    return bool(conflict and conflict.blocks)


def dimension_effect(
    *,
    established_dimensions: Mapping[str, Any],
    conflict: ConflictDecision,
) -> dict[str, Any]:
    """Return a preservation map: only named affected dimensions reopen."""
    affected = set(conflict.affected_dimensions if conflict.blocks else ())
    return {
        key: {
            "value": value,
            "state": "REOPEN_FOR_CONFLICT_RESOLUTION" if key in affected else "PRESERVE",
        }
        for key, value in established_dimensions.items()
    }
