from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import csv
import io
import json
from typing import Any, Iterable, Mapping

PROTOCOL_VERSION = "glaciereq.case-execution/1.0"

EXECUTION_STATES = (
    "RAW",
    "STRUCTURED",
    "SOURCED",
    "ELEMENT_MAPPED",
    "EVIDENCE_TRIGGERED",
    "REFERRAL_READY",
    "TRANSMITTED",
    "ACK_PENDING",
    "INVESTIGATION_OPEN",
    "PROSECUTOR_REVIEW",
    "SUPPLEMENT_REQUIRED",
    "ESCALATION_READY",
    "CLOSED",
    "QUARANTINED",
)

STATE_RANK = {state: i for i, state in enumerate(EXECUTION_STATES)}

TERMINAL_STATES = {"CLOSED", "QUARANTINED"}

ALLOWED_FORWARD_TRANSITIONS = {
    "RAW": {"STRUCTURED", "QUARANTINED"},
    "STRUCTURED": {"SOURCED", "QUARANTINED"},
    "SOURCED": {"ELEMENT_MAPPED", "EVIDENCE_TRIGGERED", "QUARANTINED"},
    "ELEMENT_MAPPED": {"EVIDENCE_TRIGGERED", "REFERRAL_READY", "QUARANTINED"},
    "EVIDENCE_TRIGGERED": {"REFERRAL_READY", "QUARANTINED"},
    "REFERRAL_READY": {"TRANSMITTED", "ACK_PENDING", "QUARANTINED"},
    "TRANSMITTED": {"ACK_PENDING", "INVESTIGATION_OPEN", "PROSECUTOR_REVIEW", "SUPPLEMENT_REQUIRED", "ESCALATION_READY", "CLOSED"},
    "ACK_PENDING": {"INVESTIGATION_OPEN", "PROSECUTOR_REVIEW", "SUPPLEMENT_REQUIRED", "ESCALATION_READY", "CLOSED"},
    "INVESTIGATION_OPEN": {"PROSECUTOR_REVIEW", "SUPPLEMENT_REQUIRED", "ESCALATION_READY", "CLOSED"},
    "PROSECUTOR_REVIEW": {"SUPPLEMENT_REQUIRED", "ESCALATION_READY", "CLOSED"},
    "SUPPLEMENT_REQUIRED": {"INVESTIGATION_OPEN", "PROSECUTOR_REVIEW", "ESCALATION_READY", "CLOSED"},
    "ESCALATION_READY": {"TRANSMITTED", "ACK_PENDING", "INVESTIGATION_OPEN", "PROSECUTOR_REVIEW", "CLOSED"},
    "CLOSED": set(),
    "QUARANTINED": {"RAW", "STRUCTURED", "SOURCED", "ELEMENT_MAPPED", "EVIDENCE_TRIGGERED", "REFERRAL_READY"},
}

@dataclass(frozen=True, slots=True)
class ControlDecision:
    case_id: str
    execution_id: str
    observed_state: str
    effective_state: str
    action_kind: str
    next_action: str
    idempotency_key: str
    external_action_authorized: bool
    calendar: tuple[dict[str, Any], ...]
    receipts: tuple[str, ...]
    reasons: tuple[str, ...]

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def stable_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()

def parse_outbound_ledger(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))

def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("execution timestamps must be timezone-aware")
    return parsed.astimezone(UTC)

def _case_outbounds(case_id: str, outbound_rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in outbound_rows if str(row.get("case_id", "")).strip() == case_id]

def _provider_receipts(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for row in rows:
        for field in ("provider_receipt", "thread_or_run"):
            value = str(row.get(field, "")).strip()
            if value and value not in values:
                values.append(value)
    return tuple(values)

def effective_state(execution: Mapping[str, Any], outbound_rows: Iterable[Mapping[str, Any]]) -> tuple[str, tuple[str, ...]]:
    state = str(execution.get("state", "")).strip()
    if state not in STATE_RANK:
        raise ValueError(f"unknown execution state: {state!r}")
    case_id = str(execution.get("case_id", "")).strip()
    rows = _case_outbounds(case_id, outbound_rows)
    reasons: list[str] = []

    if rows and STATE_RANK[state] < STATE_RANK["TRANSMITTED"]:
        state = "ACK_PENDING" if any(str(r.get("status", "")).strip() == "ACK_PENDING" for r in rows) else "TRANSMITTED"
        reasons.append("provider-backed outbound ledger proves transmission; suppressed duplicate send")

    if state == "TRANSMITTED" and any(str(r.get("status", "")).strip() == "ACK_PENDING" for r in rows):
        state = "ACK_PENDING"
        reasons.append("outbound ledger marks acknowledgement pending")

    tracking = str(execution.get("tracking_number", "")).strip()
    assigned = str(execution.get("assigned_unit", "")).strip() or str(execution.get("assigned_investigator", "")).strip()
    if state == "ACK_PENDING" and (tracking or assigned):
        state = "INVESTIGATION_OPEN"
        reasons.append("tracking/assignment metadata proves acknowledgement or investigative routing")

    return state, tuple(reasons)

def _calendar_projection(execution: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    case_id = str(execution.get("case_id", "")).strip()
    execution_id = str(execution.get("execution_id", "")).strip()
    items: list[dict[str, Any]] = []
    for field, kind, title in (
        ("follow_up_due", "follow_up", "Case follow-up due"),
        ("response_deadline", "response_deadline", "Agency response deadline"),
    ):
        due = _parse_dt(execution.get(field))
        if due is None:
            continue
        items.append(
            {
                "calendar_event_id": stable_hash({"case_id": case_id, "execution_id": execution_id, "kind": kind, "due_at": due.isoformat()})[:24],
                "case_id": case_id,
                "execution_id": execution_id,
                "kind": kind,
                "title": f"{title}: {case_id}",
                "due_at": due.isoformat().replace("+00:00", "Z"),
                "source": f"DOCKETS/CASE_EXECUTION_ENGINE/{execution_id or case_id}",
            }
        )
    return tuple(items)

def _due(execution: Mapping[str, Any], field: str, now: datetime) -> bool:
    value = _parse_dt(execution.get(field))
    return value is not None and value <= now

def decide(
    execution: Mapping[str, Any],
    outbound_rows: Iterable[Mapping[str, Any]] = (),
    *,
    now: datetime | None = None,
) -> ControlDecision:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    case_id = str(execution.get("case_id", "")).strip()
    execution_id = str(execution.get("execution_id", "")).strip()
    lane = str(execution.get("lane", "")).strip()
    observed = str(execution.get("state", "")).strip()
    next_hint = str(execution.get("next_action", "")).strip()

    if not case_id or not execution_id or not lane or not observed or not next_hint:
        raise ValueError("execution requires execution_id, case_id, lane, state, and next_action")

    rows = _case_outbounds(case_id, outbound_rows)
    state, reasons = effective_state(execution, rows)
    reasons_list = list(reasons)

    if state in TERMINAL_STATES:
        action_kind = "no_action"
        next_action = "Lane is terminal; preserve state and await new source-bound trigger."
    elif state in {"RAW", "STRUCTURED", "SOURCED", "ELEMENT_MAPPED", "EVIDENCE_TRIGGERED"}:
        action_kind = "casebuild"
        next_action = next_hint
    elif state == "REFERRAL_READY":
        if rows:
            action_kind = "reconcile_receipt"
            next_action = "Reconcile existing provider receipt and advance acknowledgement/tracking path; do not resend."
            reasons_list.append("existing outbound for case blocks duplicate transmission")
        else:
            action_kind = "transmit"
            next_action = next_hint
    elif state in {"TRANSMITTED", "ACK_PENDING"}:
        if _due(execution, "follow_up_due", current):
            action_kind = "follow_up"
            next_action = next_hint
            reasons_list.append("follow-up due")
        else:
            action_kind = "await_ack"
            next_action = "Monitor acknowledgement/reply; capture tracking number, assigned unit, and secure evidence-delivery channel."
    elif state == "INVESTIGATION_OPEN":
        if not str(execution.get("secure_delivery_method", "")).strip():
            action_kind = "secure_evidence_delivery"
            next_action = "Obtain/confirm secure evidence-delivery method and deliver the indexed evidence package with lineage."
        else:
            action_kind = "monitor"
            next_action = next_hint
    elif state == "PROSECUTOR_REVIEW":
        action_kind = "monitor"
        next_action = next_hint
    elif state == "SUPPLEMENT_REQUIRED":
        action_kind = "supplement"
        next_action = next_hint
    elif state == "ESCALATION_READY":
        action_kind = "escalate"
        next_action = next_hint
    else:
        raise AssertionError(f"unhandled state: {state}")

    target = str(execution.get("recipient", "")).strip() or str(execution.get("agency", "")).strip() or "unresolved"
    idem = stable_hash(
        {
            "protocol": PROTOCOL_VERSION,
            "case_id": case_id,
            "execution_id": execution_id,
            "lane": lane,
            "effective_state": state,
            "action_kind": action_kind,
            "target": target,
            "packet_ref": str(execution.get("packet_ref", "")).strip(),
        }
    )

    return ControlDecision(
        case_id=case_id,
        execution_id=execution_id,
        observed_state=observed,
        effective_state=state,
        action_kind=action_kind,
        next_action=next_action,
        idempotency_key=idem,
        external_action_authorized=False,
        calendar=_calendar_projection(execution),
        receipts=_provider_receipts(rows),
        reasons=tuple(reasons_list),
    )

def validate_transition(previous: str, new: str) -> None:
    if previous not in ALLOWED_FORWARD_TRANSITIONS or new not in STATE_RANK:
        raise ValueError("unknown execution state")
    if new == previous:
        return
    if new not in ALLOWED_FORWARD_TRANSITIONS[previous]:
        raise ValueError(f"invalid execution transition: {previous} -> {new}")

def make_case_execution_event(execution: Mapping[str, Any], decision: ControlDecision) -> dict[str, Any]:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "event_type": "case_execution.reconciled",
        "case_id": decision.case_id,
        "execution_id": decision.execution_id,
        "observed_state": decision.observed_state,
        "effective_state": decision.effective_state,
        "action_kind": decision.action_kind,
        "next_action": decision.next_action,
        "idempotency_key": decision.idempotency_key,
        "external_action_authorized": False,
        "calendar": list(decision.calendar),
        "receipts": list(decision.receipts),
        "reasons": list(decision.reasons),
        "source_pointer": {
            "repo": "GlacierEQ/DOCKETS",
            "ref": "master",
            "schema": "CASE_EXECUTION_ENGINE/EXECUTION_SCHEMA.json",
        },
    }
    payload["payload_sha256"] = stable_hash(payload)
    return payload
