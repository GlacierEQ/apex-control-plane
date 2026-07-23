import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from control_plane import (  # noqa: E402
    ANSWER,
    CaseBrainOrchestrator,
    CaseEvent,
    ClaimClass,
    ControlPlane,
    Deadline,
    Producer,
    SourcePointer,
    ThreatLevel,
    VerificationStatus,
    Worker,
    canonical_sha256,
    create_envelope,
)

FIXED_NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def source() -> SourcePointer:
    return SourcePointer(system="drive", canonical_uri="gdrive://file/abc123")


def event(*, claim_class=ClaimClass.MODEL_INFERENCE, deadline_days=None) -> CaseEvent:
    deadlines = ()
    if deadline_days is not None:
        deadlines = (
            Deadline(
                name="review deadline",
                due_at=FIXED_NOW + timedelta(days=deadline_days),
                source=source(),
                confirmed=False,
            ),
        )
    return CaseEvent(
        event_id="evt-001",
        case_id="1FDV-23-0001009",
        occurred_at=FIXED_NOW,
        event_type="court_record_received",
        title="Court record received",
        summary="Read-only test event",
        claim_class=claim_class,
        verification_status=(
            VerificationStatus.VERIFIED
            if claim_class is ClaimClass.VERIFIED_FACT
            else VerificationStatus.PENDING_REVIEW
        ),
        sources=(source(),),
        deadlines=deadlines,
    )


def producer() -> Producer:
    return Producer(
        repo="GlacierEQ/apex-control-plane",
        commit_sha="1" * 40,
        component="pytest",
    )


def test_dispatch_preserves_compatibility_and_capacity() -> None:
    cp = ControlPlane()
    cp.register(Worker("w1", 2, frozenset({"extract_case_event"})))
    result = cp.dispatch(1, capability="extract_case_event")
    assert result["ok"] is True
    assert result["worker"] == "w1"
    assert result["answer"] == ANSWER
    assert cp.dispatch(2, capability="extract_case_event")["ok"] is False


def test_dispatch_skips_unhealthy_or_incompatible_workers() -> None:
    cp = ControlPlane()
    cp.register(Worker("unhealthy", 5, frozenset({"extract_case_event"}), healthy=False))
    cp.register(Worker("wrong", 5, frozenset({"timeline"})))
    assert cp.dispatch(1, capability="extract_case_event")["error"] == "no_capacity"


def test_envelope_hash_is_deterministic_and_verified() -> None:
    payload = {"b": 2, "a": 1}
    envelope = create_envelope(payload=payload, producer=producer())
    assert envelope.payload_sha256 == canonical_sha256({"a": 1, "b": 2})
    assert envelope.payload_schema_id.endswith("case-event:1.0.0")


def test_verified_fact_requires_verified_status() -> None:
    with pytest.raises(ValueError, match="verified_fact"):
        CaseEvent(
            event_id="bad",
            case_id="case",
            occurred_at=FIXED_NOW,
            event_type="test",
            title="Bad",
            summary="Bad",
            claim_class=ClaimClass.VERIFIED_FACT,
            verification_status=VerificationStatus.PENDING_REVIEW,
            sources=(source(),),
        )


def test_orchestrator_generates_review_only_recommendations_and_receipt() -> None:
    orchestrator = CaseBrainOrchestrator(producer=producer())
    result = orchestrator.process_event(
        event(claim_class=ClaimClass.ALLEGATION, deadline_days=3),
        threat_inputs=(
            {
                "category": "unexpected_docket_change",
                "description": "Metadata changed unexpectedly",
                "evidence_refs": ("gdrive://file/abc123",),
                "alternative_explanations": ("clerical correction",),
                "corroboration_count": 5,
                "urgency_bonus": 10,
            },
        ),
    )
    assert result["status"] == "completed"
    assert result["human_review_required"] is True
    assert result["external_action_authorized"] is False
    assert result["threat_signals"][0]["severity"] >= 65
    assert result["threat_signals"][0]["external_action_authorized"] is False
    actions = {item["action"] for item in result["recommendations"]}
    assert "verify_deadline_and_prepare_review_packet" in actions
    assert "build_corroboration_matrix" in actions
    assert "freeze_external_automation_and_route_operator_review" in actions
    assert len(orchestrator.receipts) == 1
    assert orchestrator.receipts[0].output_sha256 is not None


def test_duplicate_event_is_idempotent() -> None:
    orchestrator = CaseBrainOrchestrator(producer=producer())
    first = orchestrator.process_event(event())
    second = orchestrator.process_event(event())
    assert first["status"] == "completed"
    assert second["status"] == "duplicate"
    assert len(orchestrator.receipts) == 1


def test_threat_level_is_high_with_corroboration() -> None:
    orchestrator = CaseBrainOrchestrator(producer=producer())
    signal = orchestrator.threat_hub.assess(
        category="record_integrity_gap",
        description="Test",
        evidence_refs=("ref",),
        alternative_explanations=("clerical error",),
        corroboration_count=5,
    )
    assert signal.level in {ThreatLevel.HIGH, ThreatLevel.CRITICAL}
    assert signal.external_action_authorized is False


def test_connector_retry_recovers_and_closes_breaker() -> None:
    orchestrator = CaseBrainOrchestrator(producer=producer())
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError("temporary")
        return "ok"

    assert orchestrator.call_connector("supermemory", flaky, sleep=lambda _: None) == "ok"
    assert attempts["count"] == 3
    assert orchestrator.breakers["supermemory"].failures == 0


def test_connector_failure_dead_letters_without_external_action() -> None:
    orchestrator = CaseBrainOrchestrator(producer=producer())

    with pytest.raises(RuntimeError, match="connector failed"):
        orchestrator.call_connector(
            "tasklet",
            lambda: (_ for _ in ()).throw(OSError("down")),
            attempts=2,
            sleep=lambda _: None,
        )
    assert orchestrator.dead_letter
    assert orchestrator.dead_letter[0]["external_action_authorized"] is False
