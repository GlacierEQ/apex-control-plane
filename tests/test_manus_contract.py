import hashlib
import hmac

import pytest

from src.manus_contract import (
    ManusCallbackObservation,
    ManusContractError,
    correlate_callback,
    validate_structured_output,
    verify_callback_signature,
)


def test_structured_output_is_fail_closed():
    with pytest.raises(ManusContractError):
        validate_structured_output({"facts": [], "findings": [], "recommended_changes": []})
    assert validate_structured_output({
        "status": "success", "facts": [], "findings": [], "recommended_changes": []
    })["status"] == "success"


def test_callback_signature_requires_explicit_secret_and_validates_hmac():
    payload = b'{"task_id":"provider-task"}'
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert verify_callback_signature(payload, signature, secret="secret")
    assert not verify_callback_signature(payload, "0" * 64, secret="secret")
    with pytest.raises(ManusContractError):
        verify_callback_signature(payload, signature, secret="")


def test_callback_requires_explicit_correlation_and_never_terminal_verifies():
    with pytest.raises(ManusContractError):
        correlate_callback({"event_type": "task_stopped"})
    observation = correlate_callback({
        "event_type": "task_stopped",
        "task_id": "provider-task",
        "mission_id": "mission-1",
        "status": "success",
    })
    assert observation.provider_terminal_verified is False
    with pytest.raises(ManusContractError):
        ManusCallbackObservation(
            event_type="task_stopped",
            task_id="provider-task",
            mission_id="mission-1",
            status="success",
            structured_output={},
            provider_terminal_verified=True,
        )
