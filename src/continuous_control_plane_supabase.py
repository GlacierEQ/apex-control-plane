"""Source-bound Supabase execution plans harvested from continuous-control-plane-v1.

Donor provenance: continuous-control-plane-v1/src/continuous_control_plane_supabase.py.
The donor's approval_required/operator_approved permission union and legacy context-packet
builder are intentionally excluded. Authorization here is attributable Operator-source
provenance checked against an existing explicit-action, plan/batch, or action-class
envelope; verification/readback remains evidence, never permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from source_bound_authorization import SourceBoundAuthorization, authorize_constituent_action

BACKEND_PROJECT_REF = "dyhprklicgewmrimecey"
DOMAIN_PROJECT_REF = "kjebemdgvjvuutzvhbtp"
CONNECTOR = "supabase"


@dataclass(frozen=True, slots=True)
class SupabaseRPCPlan:
    project_ref: str
    rpc: str
    args: Mapping[str, Any]
    mutation: bool
    purpose: str
    authority_source_ref: str | None = None
    authority_envelope_sha256: str | None = None

    def target(self) -> dict[str, Any]:
        return {"project_ref": self.project_ref, "rpc": self.rpc, "args": dict(self.args)}


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _authorized_plan(*, authorization: SourceBoundAuthorization, rpc: str,
                     args: Mapping[str, Any], purpose: str,
                     project_ref: str = BACKEND_PROJECT_REF,
                     destructive: bool = False,
                     material_strategy_delta: bool = False) -> SupabaseRPCPlan:
    target = {"project_ref": project_ref, "rpc": rpc}
    digest = authorize_constituent_action(
        authorization,
        connector=CONNECTOR,
        operation=rpc,
        target=target,
        destructive=destructive,
        material_strategy_delta=material_strategy_delta,
    )
    return SupabaseRPCPlan(
        project_ref=project_ref, rpc=rpc, args=dict(args), mutation=True,
        purpose=purpose, authority_source_ref=authorization.source_ref,
        authority_envelope_sha256=digest,
    )


def continuity_event_plan(*, authorization: SourceBoundAuthorization, source_system: str,
                          account_key: str, external_id: str, external_type: str,
                          occurred_at: datetime, payload: Mapping[str, Any],
                          matter_key: str | None = None) -> SupabaseRPCPlan:
    rpc = "continuity_ingest_external_event_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_source_system": source_system, "p_account_key": account_key,
              "p_external_id": external_id, "p_external_type": external_type,
              "p_occurred_at": _iso(occurred_at), "p_payload": dict(payload),
              "p_matter_key": matter_key},
        purpose="Ingest a provider observation with attributable source-bound authority.",
    )


def legal_event_plan(*, authorization: SourceBoundAuthorization, matter_key: str,
                     event_key: str, event_type: str, occurred_at: datetime,
                     source_system: str, payload: Mapping[str, Any],
                     source_ref: str | None = None, provider_receipt: str | None = None,
                     desired_state: str | None = None, next_action: str | None = None,
                     next_action_due_at: datetime | None = None,
                     material_strategy_delta: bool = False) -> SupabaseRPCPlan:
    rpc = "legal_control_ingest_event_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_matter_key": matter_key, "p_event_key": event_key,
              "p_event_type": event_type, "p_occurred_at": _iso(occurred_at),
              "p_source_system": source_system, "p_source_ref": source_ref,
              "p_provider_receipt": provider_receipt, "p_payload": dict(payload),
              "p_desired_state": desired_state, "p_next_action": next_action,
              "p_next_action_due_at": _iso(next_action_due_at) if next_action_due_at else None,
              "p_authority_source_ref": authorization.source_ref,
              "p_authority_envelope_sha256": authorization.envelope_sha256},
        purpose="Ingest a source-bound legal execution event without manufacturing fresh approval.",
        material_strategy_delta=material_strategy_delta,
    )


def prepare_outbound_plan(*, authorization: SourceBoundAuthorization, matter_key: str,
                          target_entity_key: str | None, channel: str, target: str,
                          action_purpose: str, idempotency_key: str) -> SupabaseRPCPlan:
    rpc = "continuity_prepare_outbound_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_matter_key": matter_key, "p_target_entity_key": target_entity_key,
              "p_channel": channel, "p_target": target,
              "p_action_purpose": action_purpose, "p_idempotency_key": idempotency_key,
              "p_authority_source_ref": authorization.source_ref,
              "p_authority_envelope_sha256": authorization.envelope_sha256},
        purpose="Create or recover an idempotent outbound transaction under existing Operator authority.",
    )


def start_outbound_plan(*, authorization: SourceBoundAuthorization, action_id: str,
                        provider_ref: str | None, detail: Mapping[str, Any]) -> SupabaseRPCPlan:
    rpc = "continuity_start_outbound_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_action_id": action_id, "p_provider_ref": provider_ref,
              "p_detail": dict(detail), "p_authority_source_ref": authorization.source_ref,
              "p_authority_envelope_sha256": authorization.envelope_sha256},
        purpose="Advance an already source-authorized outbound action into provider execution.",
    )


def finish_outbound_plan(*, authorization: SourceBoundAuthorization, action_id: str,
                         terminal_status: str, provider_ref: str | None,
                         result: Mapping[str, Any] | None = None,
                         error: Mapping[str, Any] | None = None) -> SupabaseRPCPlan:
    rpc = "continuity_finish_outbound_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_action_id": action_id, "p_terminal_status": terminal_status,
              "p_provider_ref": provider_ref, "p_result": dict(result or {}),
              "p_error": dict(error or {})},
        purpose="Persist provider result/readback; readback proves outcome and does not grant permission.",
    )


def action_receipt_plan(*, authorization: SourceBoundAuthorization, action_id: str | None,
                        matter_key: str, packet_id: str | None, channel: str,
                        receipt_type: str, outcome: str, provider_ref: str | None,
                        detail: Mapping[str, Any]) -> SupabaseRPCPlan:
    rpc = "continuity_record_action_receipt_v1"
    return _authorized_plan(
        authorization=authorization, rpc=rpc,
        args={"p_action_id": action_id, "p_matter_key": matter_key,
              "p_packet_id": packet_id, "p_channel": channel,
              "p_receipt_type": receipt_type, "p_outcome": outcome,
              "p_provider_ref": provider_ref, "p_detail": dict(detail)},
        purpose="Append provider/execution evidence to the action ledger.",
    )


def legal_snapshot_plan(*, matter_key: str) -> SupabaseRPCPlan:
    return SupabaseRPCPlan(
        project_ref=BACKEND_PROJECT_REF, rpc="legal_execution_snapshot_v1",
        args={"p_matter_key": matter_key}, mutation=False,
        purpose="Read the exact current legal execution frontier before planning or retry.",
    )
