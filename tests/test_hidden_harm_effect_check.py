"""Effect-check admission. Receipt trust is not self-certified."""

from hidden_harm_effect_check import evaluate_effect_check
from hidden_harm_restore import restore_operation_class


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


def test_summary_displacement_is_untrusted_and_restores_continue() -> None:
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": "GlacierEQ/apex-control-plane#307",
            "receipt_producer_id": "worker",
            "displaced_by": "summary",
            "transforms": ["CONTINUE -> SUMMARY"],
            "readback": {
                "producer_id": "github-api",
                "object_ref": "GlacierEQ/apex-control-plane#307",
                "operation_class": "continue",
                "displaced_by": "summary",
                "check_read_back": False,
            },
        }
    )
    assert result.trusted is False
    assert result.intent_claim == "not_promoted"
    assert any("summary" in item for item in result.errors)
    assert any("continue the named object" in item for item in result.restoration)
    restored = restore_operation_class("continue", "GlacierEQ/apex-control-plane#307")
    assert restored["status"] == "restore_operation"
    assert restored["intent_claim"] == "not_promoted"


def test_unread_check_is_not_admission() -> None:
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": "PR 307",
            "receipt_producer_id": "worker",
            "readback": {
                "producer_id": "github-api",
                "object_ref": "PR 307",
                "operation_class": "continue",
                "check_read_back": False,
            },
        }
    )
    assert result.trusted is False
    assert any("not read back" in item for item in result.errors)


def test_generic_prior_on_look_restores_inspect() -> None:
    named = "GlacierEQ/apex-control-plane:hidden-harm-effect-check-2026-09-30"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "look",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "generic_prior",
            "transforms": ["LOOK -> GENERIC_PRIOR"],
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "look",
                "displaced_by": "generic_prior",
                "check_read_back": True,
            },
        }
    )
    assert result.trusted is False
    assert result.intent_claim == "not_promoted"
    assert any("generic_prior" in item for item in result.errors)
    assert any("inspect the named object" in item for item in result.restoration)
    restored = restore_operation_class("look", named)
    assert restored["status"] == "restore_operation"
    assert "rank" not in restored["restoration"]


def test_constraint_on_fix_restores_repair_without_mapped_transform() -> None:
    named = "src/hidden_harm_effect_check.py"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "fix",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "constraint",
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "fix",
                "displaced_by": "constraint",
                "check_read_back": True,
            },
        }
    )
    assert result.trusted is False
    assert result.intent_claim == "not_promoted"
    assert any("constraint" in item for item in result.errors)
    assert any("repair the named object" in item for item in result.restoration)
