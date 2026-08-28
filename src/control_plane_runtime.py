#!/usr/bin/env python3
"""APEX CASEBRAIN control plane.

A standard-library-only reference runtime for deterministic case-event ingestion,
timeline calculation, threat-signal triage, bounded recommendations, worker
routing, and immutable audit receipts.

Design constraints:
- One truth, many projections.
- Facts, allegations, inferences, and recommendations never collapse together.
- Threat signals never authorize external action.
- Connector presence is not runtime proof.
- Secrets are referenced by environment-variable name, never embedded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from hashlib import sha256
import json
import time
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from approved_operation_bridge import (
    ApprovedConnectorAction,
    ConnectorExecutionReceipt,
    action_audit_scope,
    execution_receipt_audit_details,
    validate_approved_action_request,
    validate_execution_receipt,
)
from connector_receipts import (
    ConnectorReadReceipt,
    receipt_audit_details,
    validate_read_receipt,
)

ENVELOPE_VERSION = "1.0.0"
CASE_EVENT_SCHEMA_ID = "urn:casebrain:schema:case-event:1.0.0"


class ClaimClass(str, Enum):
    VERIFIED_FACT = "verified_fact"
    ALLEGATION = "allegation"
    MODEL_INFERENCE = "model_inference"
    RECOMMENDATION = "recommendation"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class SourcePointer:
    """Stable provenance pointer to an original or authoritative source."""

    system: str
    canonical_uri: str
    locator: str | None = None
    sha256: str | None = None
    version: str | None = None

    def validate(self) -> None:
        if not self.system.strip():
            raise ValueError("source.system is required")
        if not self.canonical_uri.strip():
            raise ValueError("source.canonical_uri is required")
        if self.sha256 is not None and not _is_sha256(self.sha256):
            raise ValueError(
                "source.sha256 must be a 64-character lowercase hex digest"
            )


@dataclass(frozen=True, slots=True)
class Deadline:
    name: str
    due_at: datetime
    source: SourcePointer
    confirmed: bool = False

    def __post_init__(self) -> None:
        _require_aware(self.due_at, "deadline.due_at")
        self.source.validate()

    def days_remaining(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        _require_aware(current, "now")
        return (self.due_at.date() - current.date()).days


@dataclass(frozen=True, slots=True)
class CaseEvent:
    event_id: str
    case_id: str
    occurred_at: datetime
    event_type: str
    title: str
    summary: str
    claim_class: ClaimClass
    verification_status: VerificationStatus
    sources: tuple[SourcePointer, ...]
    actors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    deadlines: tuple[Deadline, ...] = ()
    sensitivity: str = "restricted_case_data"

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "event.occurred_at")
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if not self.event_type.strip():
            raise ValueError("event_type is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.sources:
            raise ValueError("at least one source pointer is required")
        for source in self.sources:
            source.validate()
        if (
            self.claim_class is ClaimClass.VERIFIED_FACT
            and self.verification_status is not VerificationStatus.VERIFIED
        ):
            raise ValueError("verified_fact requires verification_status=verified")


@dataclass(frozen=True, slots=True)
class ThreatSignal:
    signal_id: str
    category: str
    severity: int
    description: str
    evidence_refs: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    claim_class: ClaimClass = ClaimClass.MODEL_INFERENCE
    verification_status: VerificationStatus = VerificationStatus.PENDING_REVIEW
    external_action_authorized: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.severity <= 100:
            raise ValueError("severity must be between 0 and 100")
        if self.external_action_authorized:
            raise ValueError("threat signals may never authorize external action")
        if self.claim_class is ClaimClass.VERIFIED_FACT:
            raise ValueError(
                "threat signals are analytical outputs, not verified facts"
            )
        if not self.alternative_explanations:
            raise ValueError(
                "threat signals must preserve at least one alternative explanation"
            )

    @property
    def level(self) -> ThreatLevel:
        if self.severity >= 85:
            return ThreatLevel.CRITICAL
        if self.severity >= 65:
            return ThreatLevel.HIGH
        if self.severity >= 40:
            return ThreatLevel.MODERATE
        if self.severity > 0:
            return ThreatLevel.LOW
        return ThreatLevel.NONE


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: str
    action: str
    rationale: str
    confidence: float
    prerequisites: tuple[str, ...]
    risks: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    claim_class: ClaimClass = ClaimClass.RECOMMENDATION
    verification_status: VerificationStatus = VerificationStatus.PENDING_REVIEW
    human_review_required: bool = True
    external_action_authorized: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.human_review_required:
            raise ValueError("case recommendations require human review")
        if self.external_action_authorized:
            raise ValueError("recommendations cannot self-authorize external actions")


@dataclass(frozen=True, slots=True)
class Producer:
    repo: str
    commit_sha: str
    component: str

    def __post_init__(self) -> None:
        if not self.repo.strip() or "/" not in self.repo:
            raise ValueError("producer.repo must use owner/name form")
        if len(self.commit_sha) != 40 or any(
            c not in "0123456789abcdef" for c in self.commit_sha
        ):
            raise ValueError(
                "producer.commit_sha must be a 40-character lowercase hex SHA"
            )
        if not self.component.strip():
            raise ValueError("producer.component is required")


@dataclass(frozen=True, slots=True)
class TransportEnvelope:
    envelope_version: str
    trace_id: str
    idempotency_key: str
    producer: Producer
    payload_schema_id: str
    payload_sha256: str
    emitted_at: datetime
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_aware(self.emitted_at, "envelope.emitted_at")
        if self.envelope_version != ENVELOPE_VERSION:
            raise ValueError(f"unsupported envelope version: {self.envelope_version}")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not _is_sha256(self.payload_sha256):
            raise ValueError(
                "payload_sha256 must be a 64-character lowercase hex digest"
            )
        actual = canonical_sha256(self.payload)
        if actual != self.payload_sha256:
            raise ValueError("payload hash mismatch")


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    receipt_id: str
    trace_id: str
    action: str
    status: str
    recorded_at: datetime
    input_sha256: str
    output_sha256: str | None
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_aware(self.recorded_at, "receipt.recorded_at")
        if not _is_sha256(self.input_sha256):
            raise ValueError("receipt input_sha256 is invalid")
        if self.output_sha256 is not None and not _is_sha256(self.output_sha256):
            raise ValueError("receipt output_sha256 is invalid")


@dataclass(slots=True)
class Worker:
    id: str
    capacity: int
    capabilities: frozenset[str] = field(default_factory=frozenset)
    load: int = 0
    healthy: bool = True
    last_heartbeat_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("worker.id is required")
        if self.capacity < 1:
            raise ValueError("worker.capacity must be >= 1")
        if self.load < 0:
            raise ValueError("worker.load must be >= 0")

    def supports(self, capability: str | None) -> bool:
        return capability is None or capability in self.capabilities


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at_monotonic: float | None = None

    def allow_request(self, now_monotonic: float | None = None) -> bool:
        now = now_monotonic if now_monotonic is not None else time.monotonic()
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.OPEN:
            if self.opened_at_monotonic is None:
                return False
            if now - self.opened_at_monotonic >= self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at_monotonic = None
        self.state = CircuitState.CLOSED

    def record_failure(self, now_monotonic: float | None = None) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at_monotonic = (
                now_monotonic if now_monotonic is not None else time.monotonic()
            )


@dataclass(slots=True)
class ControlPlane:
    """Capacity-aware worker router retained for backward compatibility."""

    workers: dict[str, Worker] = field(default_factory=dict)

    def register(self, worker: Worker) -> None:
        self.workers[worker.id] = worker

    def heartbeat(
        self, worker_id: str, *, healthy: bool = True, at: datetime | None = None
    ) -> None:
        worker = self.workers[worker_id]
        heartbeat_at = at or datetime.now(UTC)
        _require_aware(heartbeat_at, "heartbeat.at")
        worker.healthy = healthy
        worker.last_heartbeat_at = heartbeat_at

    def dispatch(
        self, job_cost: int = 1, capability: str | None = None
    ) -> dict[str, Any]:
        if job_cost < 1:
            raise ValueError("job_cost must be >= 1")
        candidates = [
            worker
            for worker in self.workers.values()
            if worker.healthy
            and worker.supports(capability)
            and worker.load + job_cost <= worker.capacity
        ]
        if not candidates:
            return {"ok": False, "error": "no_capacity", "capability": capability}
        worker = min(
            candidates,
            key=lambda item: (item.load / max(item.capacity, 1), item.id),
        )
        worker.load += job_cost
        return {
            "ok": True,
            "worker": worker.id,
            "load": worker.load,
            "capability": capability,
        }

    def release(self, worker_id: str, job_cost: int = 1) -> None:
        if job_cost < 1:
            raise ValueError("job_cost must be >= 1")
        worker = self.workers[worker_id]
        worker.load = max(0, worker.load - job_cost)


@dataclass(slots=True)
class TimelineBrain:
    """Deterministic timeline and deadline calculator."""

    events: dict[str, CaseEvent] = field(default_factory=dict)

    def add(self, event: CaseEvent) -> None:
        existing = self.events.get(event.event_id)
        if existing is not None and canonical_sha256(
            event_to_payload(existing)
        ) != canonical_sha256(event_to_payload(event)):
            raise ValueError(
                f"event_id collision with different content: {event.event_id}"
            )
        self.events[event.event_id] = event

    def ordered_events(self) -> list[CaseEvent]:
        return sorted(
            self.events.values(), key=lambda item: (item.occurred_at, item.event_id)
        )

    def deadline_snapshot(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(UTC)
        output: list[dict[str, Any]] = []
        for event in self.ordered_events():
            for deadline in event.deadlines:
                output.append(
                    {
                        "event_id": event.event_id,
                        "name": deadline.name,
                        "due_at": deadline.due_at.isoformat(),
                        "days_remaining": deadline.days_remaining(current),
                        "confirmed": deadline.confirmed,
                        "source_uri": deadline.source.canonical_uri,
                    }
                )
        return sorted(output, key=lambda item: (item["due_at"], item["event_id"]))


@dataclass(slots=True)
class ThreatIntelligenceHub:
    """Converts bounded indicators into review-only analytical signals."""

    category_weights: Mapping[str, int] = field(
        default_factory=lambda: {
            "deadline_proximity": 35,
            "source_conflict": 30,
            "service_or_notice_gap": 25,
            "unexpected_docket_change": 30,
            "law_enforcement_contact": 25,
            "retaliation_indicator": 20,
            "record_integrity_gap": 30,
        }
    )

    def assess(
        self,
        *,
        category: str,
        description: str,
        evidence_refs: Sequence[str],
        alternative_explanations: Sequence[str],
        corroboration_count: int = 0,
        urgency_bonus: int = 0,
    ) -> ThreatSignal:
        base = self.category_weights.get(category, 10)
        corroboration = min(max(corroboration_count, 0), 5) * 7
        severity = min(100, max(0, base + corroboration + urgency_bonus))
        alternatives = tuple(
            item.strip() for item in alternative_explanations if item.strip()
        )
        if not alternatives:
            alternatives = (
                "insufficient information or benign procedural explanation",
            )
        return ThreatSignal(
            signal_id=str(uuid4()),
            category=category,
            severity=severity,
            description=description,
            evidence_refs=tuple(evidence_refs),
            alternative_explanations=alternatives,
        )


@dataclass(slots=True)
class AutonomousDecisionEngine:
    """Deterministic recommendation engine with hard external-action denial."""

    def recommend(
        self,
        *,
        event: CaseEvent,
        deadline_snapshot: Sequence[Mapping[str, Any]],
        threat_signals: Sequence[ThreatSignal],
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        evidence_refs = tuple(source.canonical_uri for source in event.sources)

        nearest = min(
            (
                item["days_remaining"]
                for item in deadline_snapshot
                if item["event_id"] == event.event_id
            ),
            default=None,
        )
        if nearest is not None and nearest <= 7:
            recommendations.append(
                self._make(
                    action="verify_deadline_and_prepare_review_packet",
                    rationale=(
                        f"A linked deadline is {nearest} day(s) away; confirmation and source-checked "
                        "preparation should precede any filing or external action."
                    ),
                    confidence=0.92,
                    prerequisites=(
                        "confirm deadline from authoritative source",
                        "human review",
                    ),
                    risks=("deadline may be unconfirmed", "source may have changed"),
                    evidence_refs=evidence_refs,
                )
            )

        if event.claim_class is ClaimClass.ALLEGATION:
            recommendations.append(
                self._make(
                    action="build_corroboration_matrix",
                    rationale="The event is an allegation and must remain separated from verified facts.",
                    confidence=0.98,
                    prerequisites=(
                        "identify independent sources",
                        "preserve contradictory evidence",
                    ),
                    risks=("confirmation bias", "premature factual promotion"),
                    evidence_refs=evidence_refs,
                )
            )

        highest = max((signal.severity for signal in threat_signals), default=0)
        if highest >= 65:
            recommendations.append(
                self._make(
                    action="freeze_external_automation_and_route_operator_review",
                    rationale=(
                        "One or more analytical threat signals are high; external automation must remain "
                        "disabled while alternative explanations and evidence quality are reviewed."
                    ),
                    confidence=0.95,
                    prerequisites=("operator review", "source integrity check"),
                    risks=("false positive", "unnecessary escalation"),
                    evidence_refs=tuple(
                        ref for signal in threat_signals for ref in signal.evidence_refs
                    ),
                )
            )

        if not recommendations:
            recommendations.append(
                self._make(
                    action="index_and_monitor",
                    rationale="No deterministic escalation condition was met.",
                    confidence=0.75,
                    prerequisites=("preserve provenance",),
                    risks=("new evidence may change priority",),
                    evidence_refs=evidence_refs,
                )
            )
        return recommendations

    @staticmethod
    def _make(
        *,
        action: str,
        rationale: str,
        confidence: float,
        prerequisites: Sequence[str],
        risks: Sequence[str],
        evidence_refs: Sequence[str],
    ) -> Recommendation:
        return Recommendation(
            recommendation_id=str(uuid4()),
            action=action,
            rationale=rationale,
            confidence=confidence,
            prerequisites=tuple(prerequisites),
            risks=tuple(risks),
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        )


@dataclass(slots=True)
class CaseBrainOrchestrator:
    """Unified bounded orchestrator for the first audited CASEBRAIN slice."""

    producer: Producer
    timeline: TimelineBrain = field(default_factory=TimelineBrain)
    threat_hub: ThreatIntelligenceHub = field(default_factory=ThreatIntelligenceHub)
    decision_engine: AutonomousDecisionEngine = field(
        default_factory=AutonomousDecisionEngine
    )
    receipts: list[AuditReceipt] = field(default_factory=list)
    idempotency_index: dict[str, str] = field(default_factory=dict)
    dead_letter: list[dict[str, Any]] = field(default_factory=list)
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    connector_receipts: list[ConnectorReadReceipt] = field(default_factory=list)
    connector_receipt_index: dict[str, str] = field(default_factory=dict)
    connector_execution_receipts: list[ConnectorExecutionReceipt] = field(
        default_factory=list
    )
    connector_execution_receipt_index: dict[str, str] = field(default_factory=dict)
    connector_action_idempotency_index: dict[str, str] = field(default_factory=dict)

    def process_event(
        self,
        event: CaseEvent,
        *,
        threat_inputs: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        payload = event_to_payload(event)
        envelope = create_envelope(payload=payload, producer=self.producer)

        prior_hash = self.idempotency_index.get(envelope.idempotency_key)
        if prior_hash is not None:
            if prior_hash != envelope.payload_sha256:
                raise ValueError("idempotency key collision with different payload")
            return {
                "status": "duplicate",
                "trace_id": envelope.trace_id,
                "payload_sha256": envelope.payload_sha256,
                "external_action_authorized": False,
            }

        self.timeline.add(event)
        signals = [self._assess_threat(item) for item in threat_inputs]
        deadlines = self.timeline.deadline_snapshot()
        recommendations = self.decision_engine.recommend(
            event=event,
            deadline_snapshot=deadlines,
            threat_signals=signals,
        )
        result = {
            "status": "completed",
            "trace_id": envelope.trace_id,
            "event_id": event.event_id,
            "payload_sha256": envelope.payload_sha256,
            "claim_class": event.claim_class.value,
            "verification_status": event.verification_status.value,
            "deadline_snapshot": deadlines,
            "threat_signals": [to_jsonable(item) for item in signals],
            "recommendations": [to_jsonable(item) for item in recommendations],
            "human_review_required": True,
            "external_action_authorized": False,
        }
        output_hash = canonical_sha256(result)
        self.idempotency_index[envelope.idempotency_key] = envelope.payload_sha256
        self.receipts.append(
            AuditReceipt(
                receipt_id=str(uuid4()),
                trace_id=envelope.trace_id,
                action="process_case_event",
                status="completed",
                recorded_at=datetime.now(UTC),
                input_sha256=envelope.payload_sha256,
                output_sha256=output_hash,
                details={
                    "event_id": event.event_id,
                    "recommendation_count": len(recommendations),
                    "threat_signal_count": len(signals),
                    "external_action_authorized": False,
                },
            )
        )
        return result

    def admit_connector_read_receipt(
        self,
        payload: Mapping[str, Any],
        catalog: Any,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Admit a bridge-issued read receipt without authorizing an external action."""
        receipt = validate_read_receipt(payload, catalog, now=now)
        input_sha256 = canonical_sha256(payload)
        prior_hash = self.connector_receipt_index.get(receipt.receipt_id)
        details = receipt_audit_details(receipt)
        if prior_hash is not None:
            if prior_hash != input_sha256:
                raise ValueError(
                    "connector receipt ID collision with different payload"
                )
            return {
                "status": "duplicate",
                "receipt_id": receipt.receipt_id,
                "external_action_authorized": False,
            }

        self.connector_receipts.append(receipt)
        self.connector_receipt_index[receipt.receipt_id] = input_sha256
        self.receipts.append(
            AuditReceipt(
                receipt_id=str(uuid4()),
                trace_id=str(uuid4()),
                action="admit_connector_read_receipt",
                status="accepted",
                recorded_at=datetime.now(UTC),
                input_sha256=input_sha256,
                output_sha256=canonical_sha256(details),
                details=details,
            )
        )
        return {
            "status": "accepted",
            "receipt_id": receipt.receipt_id,
            "connector": receipt.connector,
            "operation": receipt.operation,
            "external_action_authorized": False,
        }

    def admit_connector_execution_receipt(
        self,
        action_request: Mapping[str, Any],
        receipt_payload: Mapping[str, Any],
        catalog: Any,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Admit a completed exact-approved provider action without provider content.

        The runtime revalidates the active catalog rule, immutable approval scope, and
        mutation readiness. A duplicate idempotency key may only name the same approval
        scope, and a duplicate execution receipt may only repeat its original payload.
        """
        action: ApprovedConnectorAction = validate_approved_action_request(
            action_request,
            catalog,
            now=now,
        )
        prior_scope = self.connector_action_idempotency_index.get(
            action.idempotency_key
        )
        if prior_scope is not None and prior_scope != action.approval_scope_sha256:
            raise ValueError(
                "connector action idempotency key collision with different approval scope"
            )

        receipt = validate_execution_receipt(receipt_payload, action)
        input_sha256 = canonical_sha256(receipt_payload)
        prior_receipt = self.connector_execution_receipt_index.get(
            receipt.execution_receipt_id
        )
        if prior_receipt is not None:
            if prior_receipt != input_sha256:
                raise ValueError(
                    "connector execution receipt ID collision with different payload"
                )
            return {
                "status": "duplicate",
                "execution_receipt_id": receipt.execution_receipt_id,
                "action_request_id": action.action_request_id,
                "external_action_authorized": True,
            }

        self.connector_action_idempotency_index[action.idempotency_key] = (
            action.approval_scope_sha256
        )
        self.connector_execution_receipts.append(receipt)
        self.connector_execution_receipt_index[receipt.execution_receipt_id] = (
            input_sha256
        )
        details = execution_receipt_audit_details(receipt, action)
        self.receipts.append(
            AuditReceipt(
                receipt_id=str(uuid4()),
                trace_id=str(uuid4()),
                action="admit_connector_execution_receipt",
                status=receipt.result_state,
                recorded_at=datetime.now(UTC),
                input_sha256=canonical_sha256(
                    {"action": action_audit_scope(action), "receipt": receipt_payload}
                ),
                output_sha256=canonical_sha256(details),
                details=details,
            )
        )
        return {
            "status": "accepted",
            "execution_receipt_id": receipt.execution_receipt_id,
            "action_request_id": action.action_request_id,
            "connector": action.connector,
            "operation": action.operation,
            "result_state": receipt.result_state,
            "external_action_authorized": True,
        }

    def call_connector(
        self,
        connector_name: str,
        operation: Callable[[], Any],
        *,
        attempts: int = 3,
        base_delay_seconds: float = 0.05,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Any:
        """Execute a connector call with bounded retries, breaker, and dead-letter receipt."""
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        breaker = self.breakers.setdefault(connector_name, CircuitBreaker())
        if not breaker.allow_request():
            raise RuntimeError(f"connector circuit open: {connector_name}")

        errors: list[str] = []
        for attempt in range(1, attempts + 1):
            try:
                value = operation()
                breaker.record_success()
                return value
            except (
                Exception
            ) as exc:  # boundary wrapper intentionally catches connector failures
                errors.append(f"{type(exc).__name__}: {exc}")
                breaker.record_failure()
                if attempt < attempts and breaker.allow_request():
                    sleep(base_delay_seconds * (2 ** (attempt - 1)))

        record = {
            "connector": connector_name,
            "errors": tuple(errors),
            "recorded_at": datetime.now(UTC).isoformat(),
            "external_action_authorized": False,
        }
        self.dead_letter.append(record)
        raise RuntimeError(
            f"connector failed after {attempts} attempt(s): {connector_name}"
        )

    def export_receipts_jsonl(self) -> str:
        return "\n".join(
            canonical_json(to_jsonable(receipt)) for receipt in self.receipts
        )

    def _assess_threat(self, item: Mapping[str, Any]) -> ThreatSignal:
        return self.threat_hub.assess(
            category=str(item.get("category", "unknown")),
            description=str(
                item.get("description", "unspecified analytical indicator")
            ),
            evidence_refs=tuple(str(value) for value in item.get("evidence_refs", ())),
            alternative_explanations=tuple(
                str(value) for value in item.get("alternative_explanations", ())
            ),
            corroboration_count=int(item.get("corroboration_count", 0)),
            urgency_bonus=int(item.get("urgency_bonus", 0)),
        )


def create_envelope(
    *, payload: Mapping[str, Any], producer: Producer
) -> TransportEnvelope:
    payload_hash = canonical_sha256(payload)
    event_id = str(payload.get("event_id", "unknown"))
    case_id = str(payload.get("case_id", "unknown"))
    return TransportEnvelope(
        envelope_version=ENVELOPE_VERSION,
        trace_id=str(uuid4()),
        idempotency_key=f"{producer.repo}/{case_id}/{event_id}/{payload_hash}",
        producer=producer,
        payload_schema_id=CASE_EVENT_SCHEMA_ID,
        payload_sha256=payload_hash,
        emitted_at=datetime.now(UTC),
        payload=payload,
    )


def event_to_payload(event: CaseEvent) -> dict[str, Any]:
    return to_jsonable(event)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json(to_jsonable(value)).encode("utf-8")).hexdigest()


def to_jsonable(value: Any) -> Any:
    if isinstance(value, ThreatSignal):
        payload = {key: to_jsonable(item) for key, item in asdict(value).items()}
        payload["level"] = value.level.value
        return payload
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [to_jsonable(item) for item in value]
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


if __name__ == "__main__":
    # Local smoke test only. It performs no network or external action.
    source = SourcePointer(
        system="local", canonical_uri="file://example/court-record.pdf"
    )
    event = CaseEvent(
        event_id="example-event",
        case_id="1FDV-23-0001009",
        occurred_at=datetime.now(UTC),
        event_type="court_record_received",
        title="Example read-only ingestion",
        summary="Synthetic smoke-test event.",
        claim_class=ClaimClass.MODEL_INFERENCE,
        verification_status=VerificationStatus.PENDING_REVIEW,
        sources=(source,),
        tags=("dry_run",),
    )
    orchestrator = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha="0" * 40,
            component="local-smoke-test",
        )
    )
    print(canonical_json(orchestrator.process_event(event)))
