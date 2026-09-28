from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from case_execution_bridge import ControlDecision

PROTOCOL_VERSION = "glaciereq.communications-continuity/1.0"

EXTERNAL_ACTION_KINDS = {
    "transmit",
    "follow_up",
    "secure_evidence_delivery",
    "supplement",
    "escalate",
}

CHANNEL_ALIASES = {
    "gmail": "email",
    "email": "email",
    "mail": "email",
    "phone": "phone",
    "call": "phone",
    "telephone": "phone",
    "calendar": "calendar",
}


@dataclass(frozen=True, slots=True)
class ContinuityActionEnvelope:
    case_id: str
    execution_id: str
    matter_identity: str
    target_entity_key: str | None
    channel: str
    target: str
    action_purpose: str
    idempotency_key: str
    authorization_required: bool
    source_pointer: Mapping[str, str]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_channel(value: Any, target: str) -> str:
    explicit = CHANNEL_ALIASES.get(str(value or "").strip().lower())
    if explicit:
        return explicit
    if "@" in target:
        return "email"
    compact = re.sub(r"[^0-9+]", "", target)
    if len(re.sub(r"\D", "", compact)) >= 7:
        return "phone"
    return "other"


def make_continuity_action(
    execution: Mapping[str, Any],
    decision: ControlDecision,
) -> ContinuityActionEnvelope | None:
    if decision.action_kind not in EXTERNAL_ACTION_KINDS:
        return None

    target = (
        str(execution.get("recipient", "")).strip()
        or str(execution.get("phone", "")).strip()
        or str(execution.get("agency", "")).strip()
        or "unresolved"
    )
    matter_identity = (
        str(execution.get("continuity_matter_key", "")).strip()
        or str(execution.get("forensic_matter_id", "")).strip()
        or decision.case_id
    )
    target_entity_key = str(execution.get("target_entity_key", "")).strip() or None
    channel = _normalize_channel(execution.get("channel"), target)

    idem = stable_hash(
        {
            "protocol": PROTOCOL_VERSION,
            "case_id": decision.case_id,
            "execution_id": decision.execution_id,
            "matter_identity": matter_identity,
            "action_kind": decision.action_kind,
            "effective_state": decision.effective_state,
            "channel": channel,
            "target": target,
            "upstream_idempotency_key": decision.idempotency_key,
        }
    )

    return ContinuityActionEnvelope(
        case_id=decision.case_id,
        execution_id=decision.execution_id,
        matter_identity=matter_identity,
        target_entity_key=target_entity_key,
        channel=channel,
        target=target,
        action_purpose=decision.next_action,
        idempotency_key=idem,
        authorization_required=True,
        source_pointer={
            "repo": "GlacierEQ/DOCKETS",
            "ref": "master",
            "execution_id": decision.execution_id,
            "protocol": "glaciereq.case-execution/1.0",
        },
    )


def make_prepare_rpc(envelope: ContinuityActionEnvelope) -> dict[str, Any]:
    return {
        "rpc": "continuity_prepare_outbound_v1",
        "args": {
            "p_matter_key": envelope.matter_identity,
            "p_target_entity_key": envelope.target_entity_key,
            "p_channel": envelope.channel,
            "p_target": envelope.target,
            "p_action_purpose": envelope.action_purpose,
            "p_idempotency_key": envelope.idempotency_key,
        },
        "authorization_required": True,
        "source_pointer": dict(envelope.source_pointer),
    }


def normalize_provider_receipt(
    envelope: ContinuityActionEnvelope,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    provider_ref = str(
        receipt.get("provider_ref")
        or receipt.get("message_id")
        or receipt.get("thread_id")
        or receipt.get("call_id")
        or receipt.get("event_id")
        or ""
    ).strip()
    status = str(receipt.get("status", "")).strip().lower() or "unknown"

    normalized = {
        "protocol": PROTOCOL_VERSION,
        "case_id": envelope.case_id,
        "execution_id": envelope.execution_id,
        "matter_identity": envelope.matter_identity,
        "channel": envelope.channel,
        "target": envelope.target,
        "provider_ref": provider_ref,
        "provider_status": status,
        "tracking_number": str(receipt.get("tracking_number", "")).strip(),
        "assigned_unit": str(receipt.get("assigned_unit", "")).strip(),
        "assigned_investigator": str(receipt.get("assigned_investigator", "")).strip(),
        "secure_delivery_method": str(receipt.get("secure_delivery_method", "")).strip(),
        "delivery_failure": status in {"failed", "bounced", "rejected"},
        "acknowledgement_evidence": bool(
            receipt.get("tracking_number")
            or receipt.get("assigned_unit")
            or receipt.get("assigned_investigator")
            or status in {"acknowledged", "accepted", "delivered"}
        ),
        "source_pointer": dict(envelope.source_pointer),
        "raw_receipt": dict(receipt),
    }
    normalized["payload_sha256"] = stable_hash(normalized)
    return normalized


def make_finish_rpc(
    action_id: str,
    terminal_status: str,
    normalized_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if terminal_status not in {"sent", "completed", "failed", "cancelled"}:
        raise ValueError("invalid continuity terminal status")
    return {
        "rpc": "continuity_finish_outbound_v1",
        "args": {
            "p_action_id": action_id,
            "p_terminal_status": terminal_status,
            "p_provider_ref": str(normalized_receipt.get("provider_ref", "")) or None,
            "p_result": {
                "summary": f"{normalized_receipt.get('channel', 'provider')} provider receipt",
                "receipt": dict(normalized_receipt),
            },
            "p_error": (
                {"receipt": dict(normalized_receipt)}
                if terminal_status == "failed"
                else {}
            ),
        },
    }
