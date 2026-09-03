"""Pure binding plans between APEX continuous work and the live Supabase kernels.

This module does not execute SQL or provider RPCs. It produces deterministic,
reviewable provider plans for the authenticated execution host.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from continuous_control_plane import ControlEvent


BACKEND_PROJECT_REF = "dyhprklicgewmrimecey"
DOMAIN_PROJECT_REF = "kjebemdgvjvuutzvhbtp"


@dataclass(frozen=True, slots=True)
class SupabaseRPCPlan:
    project_ref: str
    rpc: str
    args: Mapping[str, Any]
    mutation: bool
    approval_required: bool
    purpose: str

    def target(self) -> dict[str, Any]:
        return {
            "project_ref": self.project_ref,
            "rpc": self.rpc,
            "args": dict(self.args),
        }


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def continuity_event_plan(
    event: ControlEvent,
    *,
    account_key: str,
    external_id: str,
    external_type: str,
    matter_key: str | None = None,
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_ingest_external_event_v1",
        args={
            "p_source_system": event.source_system,
            "p_account_key": account_key,
            "p_external_id": external_id,
            "p_external_type": external_type,
            "p_occurred_at": _iso(event.occurred_at),
            "p_payload": dict(event.payload),
            "p_matter_key": matter_key,
        },
        mutation=True,
        approval_required=False,
        purpose="Ingest provider observation into durable continuity intelligence.",
    )


def legal_event_plan(
    event: ControlEvent,
    *,
    matter_key: str,
    event_key: str,
    provider_receipt: str | None = None,
    desired_state: str | None = None,
    next_action: str | None = None,
    next_action_due_at: datetime | None = None,
    operator_approved: bool = False,
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="legal_control_ingest_event_v1",
        args={
            "p_matter_key": matter_key,
            "p_event_key": event_key,
            "p_event_type": event.event_type,
            "p_occurred_at": _iso(event.occurred_at),
            "p_source_system": event.source_system,
            "p_source_ref": event.provenance_refs[0] if event.provenance_refs else None,
            "p_provider_receipt": provider_receipt,
            "p_payload": dict(event.payload),
            "p_desired_state": desired_state,
            "p_next_action": next_action,
            "p_next_action_due_at": _iso(next_action_due_at) if next_action_due_at else None,
            "p_operator_approved": bool(operator_approved),
        },
        mutation=True,
        approval_required=bool(desired_state),
        purpose="Ingest one source-bound legal execution event and optionally request a state transition.",
    )


def context_packet_plan(
    *,
    matter_key: str,
    target_entity_key: str | None,
    action_channel: str,
    action_purpose: str,
    horizon_days: int = 30,
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_build_context_packet_v1",
        args={
            "p_matter_key": matter_key,
            "p_target_entity_key": target_entity_key,
            "p_action_channel": action_channel,
            "p_action_purpose": action_purpose,
            "p_horizon_days": horizon_days,
        },
        mutation=True,
        approval_required=False,
        purpose="Freeze a bounded, hashable preflight context packet before an external action.",
    )


def prepare_outbound_plan(
    *,
    matter_key: str,
    target_entity_key: str | None,
    channel: str,
    target: str,
    action_purpose: str,
    idempotency_key: str,
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_prepare_outbound_v1",
        args={
            "p_matter_key": matter_key,
            "p_target_entity_key": target_entity_key,
            "p_channel": channel,
            "p_target": target,
            "p_action_purpose": action_purpose,
            "p_idempotency_key": idempotency_key,
        },
        mutation=True,
        approval_required=False,
        purpose="Create or recover the idempotent outbound transaction before provider mutation.",
    )


def preflight_outbound_plan(*, packet_id: str, channel: str, target: str) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_preflight_outbound_v2",
        args={"p_packet_id": packet_id, "p_channel": channel, "p_target": target},
        mutation=True,
        approval_required=False,
        purpose="Check duplicate, freshness, target, and provider-readback gates immediately before mutation.",
    )


def start_outbound_plan(
    *,
    action_id: str,
    provider_ref: str | None,
    detail: Mapping[str, Any],
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_start_outbound_v1",
        args={
            "p_action_id": action_id,
            "p_provider_ref": provider_ref,
            "p_detail": dict(detail),
        },
        mutation=True,
        approval_required=True,
        purpose="Advance an approved outbound action into provider execution.",
    )


def finish_outbound_plan(
    *,
    action_id: str,
    terminal_status: str,
    provider_ref: str | None,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    followup_title: str | None = None,
    followup_type: str | None = None,
    followup_due_at: datetime | None = None,
    followup_priority: int | None = None,
    followup_evidence: Mapping[str, Any] | None = None,
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_finish_outbound_v1",
        args={
            "p_action_id": action_id,
            "p_terminal_status": terminal_status,
            "p_provider_ref": provider_ref,
            "p_result": dict(result or {}),
            "p_error": dict(error or {}),
            "p_followup_title": followup_title,
            "p_followup_type": followup_type,
            "p_followup_due_at": _iso(followup_due_at) if followup_due_at else None,
            "p_followup_priority": followup_priority,
            "p_followup_evidence": dict(followup_evidence or {}),
        },
        mutation=True,
        approval_required=False,
        purpose="Persist provider result/readback and derive the next follow-up state.",
    )


def action_receipt_plan(
    *,
    action_id: str | None,
    matter_key: str,
    packet_id: str | None,
    channel: str,
    receipt_type: str,
    outcome: str,
    provider_ref: str | None,
    detail: Mapping[str, Any],
) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="continuity_record_action_receipt_v1",
        args={
            "p_action_id": action_id,
            "p_matter_key": matter_key,
            "p_packet_id": packet_id,
            "p_channel": channel,
            "p_receipt_type": receipt_type,
            "p_outcome": outcome,
            "p_provider_ref": provider_ref,
            "p_detail": dict(detail),
        },
        mutation=True,
        approval_required=False,
        purpose="Append a provider/execution receipt to the immutable action ledger.",
    )


def legal_snapshot_plan(*, matter_key: str) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF,
        rpc="legal_execution_snapshot_v1",
        args={"p_matter_key": matter_key},
        mutation=False,
        approval_required=False,
        purpose="Read the exact current legal execution frontier before planning or retry.",
    )
