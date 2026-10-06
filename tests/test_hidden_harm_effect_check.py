"""Effect-check admission. Receipt trust is not self-certified.

2026-10-03 HST score on this branch, not a new root:
main blob 7ba4c6a7 (ref 134abd02) omits displacer scoring. A matching
three-lock receipt with displaced_by summary, generic_prior, or constraint
would be trusted there. That is MODEL_ATTRACTOR_DRIFT, not an intent claim.
PR 307 head bd067e56 checks were failure, not a read-back pass. Not merged
again. Look stays inspect; the word rank in the forbid-clause is not a rank act.

2026-10-05 HST score on this same file:
main restore blob 525567ac (ref 134abd02) still has no restore_displacer and
no mission_reframe / mood_rewrite / smaller_plan map. That is a smaller plan
on the locked continue, not an intent claim. Combined status CodeRabbit
success on bd067e56 is not the check-run readback (verify, prove strongest
boot, operator-fidelity-hard-lock, mission-outcome-hard-lock failed).
Not merged again.

2026-10-06 HST score on this same file:
main ref 480131e2 still serves effect-check blob 7ba4c6a7 and restore blob
525567ac. Same-day commit on config/model_attractor_defense_policy.json
(blob aac1d2e8) adds self-attested booleans and does not name an independent
effect-check readback. Those booleans are not admission. PR 307 stays merged
at bd067e56 with failed check runs. Not merged again. Intent not promoted.
"""

from hidden_harm_effect_check import evaluate_effect_check
from hidden_harm_restore import restore_displacer, restore_operation_class


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
    assert restored["restoration"] == "inspect the named object; do not rank or retire it"
    displaced = restore_displacer("look", named, "generic_prior")
    assert displaced["status"] == "restore_operation"
    assert displaced["restoration"] == "inspect the named object; a generic prior is not the inspection"
    assert displaced["intent_claim"] == "not_promoted"


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


def test_mission_reframe_on_continue_restores_continue() -> None:
    named = "GlacierEQ/apex-control-plane:hidden-harm-effect-check-2026-09-30"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "mission_reframe",
            "transforms": ["CONTINUE -> MISSION_REFRAME"],
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "continue",
                "displaced_by": "mission_reframe",
                "check_read_back": True,
            },
        }
    )
    assert result.trusted is False
    assert result.intent_claim == "not_promoted"
    assert any("mission_reframe" in item for item in result.errors)
    assert any("do not reframe the mission" in item for item in result.restoration)
    restored = restore_displacer("continue", named, "mission_reframe")
    assert restored["restoration"] == "continue the named object; do not reframe the mission"


def test_mood_rewrite_on_fix_restores_repair() -> None:
    named = "src/hidden_harm_effect_check.py"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "fix",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "mood_rewrite",
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "fix",
                "displaced_by": "mood_rewrite",
                "check_read_back": True,
            },
        }
    )
    assert result.trusted is False
    assert any("mood_rewrite" in item for item in result.errors)
    assert any("repair the named object" in item for item in result.restoration)
    assert result.intent_claim == "not_promoted"


def test_smaller_plan_on_build_and_new_root_on_look() -> None:
    named = "src/hidden_harm_restore.py"
    build = evaluate_effect_check(
        {
            "locked_operation_class": "build",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "smaller_plan",
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "build",
                "displaced_by": "smaller_plan",
                "check_read_back": True,
            },
        }
    )
    assert build.trusted is False
    assert any("smaller plan is not the act" in item for item in build.restoration)
    look = evaluate_effect_check(
        {
            "locked_operation_class": "look",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "new_root",
            "transforms": ["LOOK -> NEW_ROOT"],
            "readback": {
                "producer_id": "branch-reader",
                "object_ref": named,
                "operation_class": "look",
                "displaced_by": "new_root",
                "check_read_back": True,
            },
        }
    )
    assert look.trusted is False
    assert any("inspect the named object; do not open a new root" in item for item in look.restoration)
    assert not any("rank" in item and "new root" in item for item in look.restoration)


def test_2026_10_05_main_restore_omission_restores_continue() -> None:
    named = "GlacierEQ/apex-control-plane:hidden-harm-effect-check-2026-09-30"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "smaller_plan",
            "transforms": ["CONTINUE -> SMALLER_PLAN"],
            "readback": {
                "producer_id": "github-api",
                "object_ref": named,
                "operation_class": "continue",
                "displaced_by": "smaller_plan",
                "check_read_back": False,
            },
        }
    )
    assert result.trusted is False
    assert result.failure_class == "MODEL_ATTRACTOR_DRIFT"
    assert result.intent_claim == "not_promoted"
    assert any("smaller_plan" in item for item in result.errors)
    assert any("not read back" in item for item in result.errors)
    assert any("smaller plan is not the act" in item for item in result.restoration)
    restored = restore_displacer("continue", named, "smaller_plan")
    assert restored["status"] == "restore_operation"
    assert restored["restoration"] == "continue the named object; a smaller plan is not the act"
    assert restored["intent_claim"] == "not_promoted"


def test_2026_10_06_policy_self_attestation_is_not_admission() -> None:
    named = "GlacierEQ/apex-control-plane:hidden-harm-effect-check-2026-09-30"
    result = evaluate_effect_check(
        {
            "locked_operation_class": "continue",
            "named_object": named,
            "receipt_producer_id": "worker",
            "displaced_by": "summary",
            "policy_booleans": {
                "correction_binding_checked": True,
                "recovered_correction_changed_decision_policy": True,
            },
            "readback": {
                "producer_id": "github-api",
                "object_ref": named,
                "operation_class": "continue",
                "displaced_by": "summary",
                "check_read_back": False,
                "main_ref": "480131e2b1f7d919ebb80be7d0760ec431135a20",
                "main_effect_check_blob": "7ba4c6a7bb736a3ec02ceaa8fdcd2545709a29d6",
                "main_restore_blob": "525567acc1e0f8f55157595657673c61139fc5b4",
                "main_policy_blob": "aac1d2e81e328fec5886368dd823e3a51906275e",
            },
        }
    )
    assert result.trusted is False
    assert result.failure_class == "MODEL_ATTRACTOR_DRIFT"
    assert result.intent_claim == "not_promoted"
    assert any("summary" in item for item in result.errors)
    assert any("not read back" in item for item in result.errors)
    assert any("continue the named object; a summary is not the act" in item for item in result.restoration)
    restored = restore_displacer("continue", named, "summary")
    assert restored["status"] == "restore_operation"
    assert restored["restoration"] == "continue the named object; a summary is not the act"
    assert restored["intent_claim"] == "not_promoted"
    assert restored["named_object"] == named
