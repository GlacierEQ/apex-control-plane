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
    reused_context_refs: tuple[str, ...] = ()
    applied_context_refs: tuple[str, ...] = ()
    research_questions: tuple[str, ...] = ()
    research_applied: bool = False
    research_source_refs: tuple[str, ...] = ()
    research_applied_refs: tuple[str, ...] = ()


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

    Understand -> Orient -> research and study -> maximize quality and skill
    -> Execute -> Verify -> Repair -> Continue. Reuse previously consulted,
    relevant source-bearing context instead of demanding repetitive retrieval.
    Application of material context must be linked to consulted source refs;
    action-specific research gaps do not freeze unrelated reversible progress.
    The host still owns real source verification and provider authorization.
    """
    turn_id = receipt.turn_id.strip()
    if not turn_id:
        raise ValueError("turn_id must be non-empty")

    digest = _digest_receipt(receipt)

    # The host may reuse source-bearing context without repeated retrieval.
    # Exact consulted identifiers, not an ungrounded self-report, anchor reuse.
    consulted = set(receipt.sources_consulted)
    reusable = bool(receipt.reused_context_refs) and all(
        isinstance(ref, str) and ref.strip() and ref in consulted
        for ref in receipt.reused_context_refs
    )
    if (not receipt.retrieval_attempted or not consulted) and not reusable:
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

    if receipt.material_context_found and (
        not receipt.material_context_applied
        or not receipt.applied_context_refs
        or any(
            not isinstance(ref, str) or not ref.strip() or ref not in consulted
            for ref in receipt.applied_context_refs
        )
    ):
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="APPLY_MATERIAL_CONTEXT_THEN_CONTINUE",
            mission_stopped=False,
            confidence_mode="PENDING_CONTEXT_APPLICATION",
            reason="material context lacks source-linked application evidence for action selection",
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

    # A bare research_applied=True flag cannot substitute for studied sources
    # materially informing the proposed action. The host must verify provenance
    # and the actual application separately before accepting this receipt.
    studied = receipt.research_source_refs
    research_applied = receipt.research_applied_refs
    research_evidenced = (
        receipt.research_applied is True
        and bool(studied)
        and bool(research_applied)
        and all(isinstance(ref, str) and ref.strip() and ref in consulted for ref in studied)
        and all(isinstance(ref, str) and ref.strip() and ref in studied for ref in research_applied)
    )
    if receipt.research_questions and not research_evidenced:
        return TurnContextDecision(
            turn_id=turn_id,
            next_action="RESEARCH_STUDY_MAXIMIZE_QUALITY_THEN_CONTINUE",
            mission_stopped=False,
            confidence_mode="TARGETED_RESEARCH_IN_PROGRESS",
            reason="open action-specific research gaps should improve the action without stopping independent work",
            receipt_sha256=digest,
        )

    return TurnContextDecision(
        turn_id=turn_id,
        next_action="EXECUTE_OPERATOR_ALIGNED_TURN",
        mission_stopped=False,
        confidence_mode="CONTEXT_APPLIED",
        reason="relevant context was consulted or reused and corrections, applied understanding, and targeted research were accounted for",
        receipt_sha256=digest,
    )


def _digest_receipt(receipt: TurnContextReceipt) -> str:
    payload: dict[str, Any] = asdict(receipt)
    payload["sources_consulted"] = list(receipt.sources_consulted)
    payload["unresolved_conflicts"] = list(receipt.unresolved_conflicts)
    payload["reused_context_refs"] = list(receipt.reused_context_refs)
    payload["applied_context_refs"] = list(receipt.applied_context_refs)
    payload["research_questions"] = list(receipt.research_questions)
    payload["research_source_refs"] = list(receipt.research_source_refs)
    payload["research_applied_refs"] = list(receipt.research_applied_refs)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()
