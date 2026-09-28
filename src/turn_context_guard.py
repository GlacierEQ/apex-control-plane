"""Per-turn context-first routing for APEX workers.

This module closes the gap between a saved personalization preference and an
actually applied turn-start invariant. It never turns missing context into a
mission-wide stop. Instead it routes the next step to context recovery,
reconciliation, or degraded reversible continuation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class TurnContextReceipt:
    turn_id: str
    retrieval_attempted: bool
    sources_consulted: tuple[str, ...]
    prior_corrections_checked: bool
    material_context_found: bool
    material_context_applied: bool
    retrieval_available: bool = True
    unresolved_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnContextDecision:
    turn_id: str
    next_action: str
    mission_stopped: bool
    confidence_mode: str
    reason: str
    receipt_sha256: str


def route_turn_context(receipt: TurnContextReceipt) -> TurnContextDecision:
    """Choose the next context action without creating a generalized gate.

    The Operator's standing rule is context-first on every turn. The model may
    not skip retrieval merely because the current conversation appears sufficient.
    When retrieval is unavailable, the mission continues in a degraded,
    reversible lane while alternate context sources are pursued.
    """
    turn_id = receipt.turn_id.strip()
    if not turn_id:
        raise ValueError("turn_id must be non-empty")

    digest = _digest_receipt(receipt)

    if not receipt.retrieval_attempted:
        if receipt.retrieval_available:
            return TurnContextDecision(
                turn_id=turn_id,
                next_action="RETRIEVE_CONTEXT_THEN_CONTINUE",
                mission_stopped=False,
                confidence_mode="PENDING_CONTEXT_RECOVERY",
                reason="turn-start retrieval was skipped; recover context before discretionary action selection",
                receipt_sha256=digest,
            )
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="CONTINUE_DEGRADED_REVERSIBLE_AND_TRY_ALTERNATE_CONTEXT_SOURCES",
            mission_stopped=False,
            confidence_mode="DEGRADED_CONTEXT_COVERAGE",
            reason="retrieval is unavailable; preserve mission and pursue alternate context sources",
            receipt_sha256=digest,
        )

    if receipt.material_context_found and not receipt.prior_corrections_checked:
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="RECONCILE_PRIOR_CORRECTIONS_THEN_CONTINUE",
            mission_stopped=False,
            confidence_mode="PENDING_CORRECTION_RECONCILIATION",
            reason="material context exists but prior corrections were not reconciled before action selection",
            receipt_sha256=digest,
        )

    if receipt.material_context_found and not receipt.material_context_applied:
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="APPLY_MATERIAL_CONTEXT_THEN_CONTINUE",
            mission_stopped=False,
            confidence_mode="PENDING_CONTEXT_APPLICATION",
            reason="retrieval occurred but material context did not causally affect action selection",
            receipt_sha256=digest,
        )

    if receipt.unresolved_conflicts:
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="CONTINUE_WITH_CONFLICT_AWARE_RETRIEVAL_AND_REVERSIBLE_WORK",
            mission_stopped=False,
            confidence_mode="CONFLICT_AWARE",
            reason="context conflicts remain; investigate them without freezing unrelated reversible progress",
            receipt_sha256=digest,
        )

    return TurnContextDecision(
        turn_id=turn_id,
        next_action="EXECUTE_OPERATOR_ALIGNED_TURN",
        mission_stopped=False,
        confidence_mode="CONTEXT_APPLIED",
        reason="turn-start retrieval and material correction/application requirements are satisfied",
        receipt_sha256=digest,
    )


def _digest_receipt(receipt: TurnContextReceipt) -> str:
    payload: dict[str, Any] = asdict(receipt)
    payload["sources_consulted"] = list(receipt.sources_consulted)
    payload["unresolved_conflicts"] = list(receipt.unresolved_conflicts)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()
