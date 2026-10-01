"""Effect-check admission. Receipt trust is not self-certified."""

from hidden_harm_effect_check import evaluate_effect_check


def test_matching_independent_readback_trusts_receipt() -> None:
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": "src/model_attractor_defense.py",
            "receipt_producer_id": "worker",
            "readback": {
                "producer_id": "preflight-reader",
                "object_ref": "src/model_attractor_defense.py",
                "operation_class": "continue",
                "new_root_created": False,
            },
        }
    )
    assert result.trusted is True
    assert result.intent_claim == "not_promoted"


def test_self_readback_is_untrusted() -> None:
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": "src/model_attractor_defense.py",
            "receipt_producer_id": "worker",
            "readback": {
                "producer_id": "worker",
                "object_ref": "src/model_attractor_defense.py",
                "operation_class": "continue",
            },
        }
    )
    assert result.trusted is False
    assert any("not independent" in item for item in result.errors)


def test_new_root_on_continue_is_displacement() -> None:
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": "src/apex_strong_boot.py",
            "receipt_producer_id": "worker",
            "readback": {
                "producer_id": "reader",
                "object_ref": "src/new_defense.py",
                "operation_class": "build",
                "new_root_created": True,
            },
        }
    )
    assert result.trusted is False
    assert result.intent_claim == "not_promoted"


def test_missing_packet_leaves_receipt_untrusted() -> None:
    result = evaluate_effect_check(None)
    assert result.trusted is False
