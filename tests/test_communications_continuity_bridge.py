import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from case_execution_bridge import decide
from communications_continuity_bridge import (
    make_continuity_action,
    make_finish_rpc,
    make_prepare_rpc,
    normalize_provider_receipt,
)

ROOT = Path(__file__).resolve().parents[1]


def execution(**overrides):
    value = {
        "execution_id": "EXE-CONT-1",
        "case_id": "CASE-CONT-1",
        "lane": "criminal_referral",
        "state": "REFERRAL_READY",
        "next_action": "Transmit referral",
        "recipient": "intake@example.test",
    }
    value.update(overrides)
    return value


def test_case_decision_becomes_non_authorized_continuity_envelope():
    source = execution()
    decision = decide(source)
    envelope = make_continuity_action(source, decision)
    assert envelope is not None
    assert envelope.channel == "email"
    assert envelope.authorization_required is True
    prepare = make_prepare_rpc(envelope)
    assert prepare["rpc"] == "continuity_prepare_outbound_v1"
    assert prepare["authorization_required"] is True


def test_non_external_decision_does_not_create_provider_action():
    source = execution(state="ACK_PENDING", next_action="Wait")
    decision = decide(source)
    assert decision.action_kind == "await_ack"
    assert make_continuity_action(source, decision) is None


def test_phone_channel_infers_from_phone_target():
    source = execution(recipient="", phone="+1 555 555 0100", channel="phone")
    decision = decide(source)
    envelope = make_continuity_action(source, decision)
    assert envelope is not None
    assert envelope.channel == "phone"
    assert envelope.target == "+1 555 555 0100"


def test_continuity_idempotency_is_stable():
    source = execution()
    decision = decide(source)
    a = make_continuity_action(source, decision)
    b = make_continuity_action(source, decision)
    assert a is not None and b is not None
    assert a.idempotency_key == b.idempotency_key


def test_provider_receipt_normalization_does_not_claim_more_than_receipt():
    source = execution()
    envelope = make_continuity_action(source, decide(source))
    assert envelope is not None
    receipt = normalize_provider_receipt(
        envelope,
        {"message_id": "msg-1", "status": "sent"},
    )
    assert receipt["provider_ref"] == "msg-1"
    assert receipt["provider_status"] == "sent"
    assert receipt["acknowledgement_evidence"] is False
    assert receipt["delivery_failure"] is False
    assert len(receipt["payload_sha256"]) == 64


def test_bounce_receipt_is_failure_not_acknowledgement():
    source = execution()
    envelope = make_continuity_action(source, decide(source))
    assert envelope is not None
    receipt = normalize_provider_receipt(
        envelope,
        {"message_id": "msg-2", "status": "bounced"},
    )
    assert receipt["delivery_failure"] is True
    assert receipt["acknowledgement_evidence"] is False


def test_tracking_number_is_acknowledgement_evidence():
    source = execution()
    envelope = make_continuity_action(source, decide(source))
    assert envelope is not None
    receipt = normalize_provider_receipt(
        envelope,
        {"call_id": "call-1", "status": "completed", "tracking_number": "T-123"},
    )
    assert receipt["acknowledgement_evidence"] is True
    assert receipt["tracking_number"] == "T-123"


def test_finish_rpc_rejects_invalid_terminal_state():
    source = execution()
    envelope = make_continuity_action(source, decide(source))
    assert envelope is not None
    receipt = normalize_provider_receipt(envelope, {"status": "sent"})
    try:
        make_finish_rpc("action-1", "acknowledged", receipt)
    except ValueError as exc:
        assert "invalid continuity terminal status" in str(exc)
    else:
        raise AssertionError("invalid terminal state was accepted")


def test_manifest_composes_with_case_execution_mesh():
    continuity = json.loads(
        (ROOT / "integration" / "communications_continuity_mesh.json").read_text()
    )
    case_mesh = json.loads((ROOT / "integration" / "case_execution_mesh.json").read_text())
    assert continuity["peers"]["case_execution"]["protocol"] == case_mesh["protocol"]
    assert continuity["outbound_transaction"]["external_action_authorized_default"] is False
    assert continuity["calendar"]["source_of_truth"] is False
    assert continuity["failure_policy"]["ambiguous_matter_binding_fails_closed"] is True


def test_sql_contracts_preserve_security_and_fail_closed_behavior():
    sql = "\n".join(
        path.read_text()
        for path in sorted((ROOT / "db" / "migrations").glob("*continuity*.sql"))
    ).lower()
    assert "enable row level security" in sql
    assert "continuity_action_receipts_v1 is append-only" in sql
    assert "context_packet_stale" in sql
    assert "recent_duplicate_action" in sql
    assert "target_has_unrepaired_delivery_failure" in sql
    assert "ambiguous" in sql
    assert "continuity_ingest_and_resolve_v1" in sql
