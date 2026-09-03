import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from case_execution_bridge import decide, make_case_execution_event, parse_outbound_ledger, validate_transition

NOW = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)

def base(**overrides):
    data = {
        "execution_id": "EXE-1",
        "case_id": "CASE-1",
        "lane": "criminal_referral",
        "state": "REFERRAL_READY",
        "next_action": "Transmit referral",
        "agency": "FBI",
        "recipient": "FBI Honolulu",
    }
    data.update(overrides)
    return data

def test_referral_ready_without_receipt_transmits():
    d = decide(base(), now=NOW)
    assert d.action_kind == "transmit"
    assert d.external_action_authorized is False

def test_existing_outbound_suppresses_duplicate_send_and_promotes_state():
    ledger = parse_outbound_ledger(
        "outbound_id,case_id,channel,utc_timestamp,recipient,cc,subject,provider_receipt,thread_or_run,status,next_action\n"
        "OUT-1,CASE-1,GMAIL,2026-09-03T08:00:00Z,x,,s,msg1,thread1,ACK_PENDING,Follow up\n"
    )
    d = decide(base(), ledger, now=NOW)
    assert d.effective_state == "ACK_PENDING"
    assert d.action_kind == "await_ack"
    assert "msg1" in d.receipts

def test_due_followup_advances_same_lane():
    d = decide(base(state="ACK_PENDING", follow_up_due="2026-09-03T09:00:00Z", next_action="Call intake"), now=NOW)
    assert d.action_kind == "follow_up"
    assert d.calendar[0]["kind"] == "follow_up"

def test_tracking_promotes_ack_to_investigation_open():
    d = decide(base(state="ACK_PENDING", tracking_number="IC3-123", next_action="Deliver evidence"), now=NOW)
    assert d.effective_state == "INVESTIGATION_OPEN"
    assert d.action_kind == "secure_evidence_delivery"

def test_idempotency_is_stable():
    a = decide(base(), now=NOW)
    b = decide(base(), now=NOW + timedelta(hours=4))
    assert a.idempotency_key == b.idempotency_key

def test_event_has_source_and_hash():
    d = decide(base(), now=NOW)
    event = make_case_execution_event(base(), d)
    assert event["source_pointer"]["repo"] == "GlacierEQ/DOCKETS"
    assert len(event["payload_sha256"]) == 64

def test_invalid_transition_rejected():
    with pytest.raises(ValueError):
        validate_transition("RAW", "PROSECUTOR_REVIEW")
