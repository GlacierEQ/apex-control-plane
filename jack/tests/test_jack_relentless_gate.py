from jack.src.jack_relentless_gate import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    GateState,
    Status,
    completion_ready,
    evaluate,
    from_mapping,
    missing,
    validate_receipt,
)


def _all_true():
    return {name: True for name in GateState.__dataclass_fields__}


def _receipt(gates: dict[str, bool], status: str, blockers=None):
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "task": "continue canonical work",
        "objective": "execute verified delta",
        "canonical_owner": "GlacierEQ/apex-control-plane",
        "sources_opened": [{"system": "Notion", "object_id": "canon", "opened": True}],
        "actions_executed": [{"action": "write", "target": "canonical", "executed": True, "verified": True}],
        "verification": [{"check": "test", "receipt_ref": "pytest:green", "passed": True}],
        "persistence_receipts": ["git:commit"],
        "readback_receipts": ["git:readback"],
        "gates": gates,
        "status": status,
        "exact_blockers": blockers or [],
        "resolved_blockers": [],
        "next_material_action": "resume next unresolved delta",
    }


def test_all_true_is_complete():
    g = GateState(**_all_true())
    assert completion_ready(g)
    assert evaluate(g) == Status.COMPLETE
    assert missing(g) == []


def test_one_missing_cannot_complete():
    values = _all_true()
    values["readback_verified"] = False
    g = GateState(**values)
    assert not completion_ready(g)
    assert evaluate(g) == Status.EXECUTING
    assert missing(g) == ["readback_verified"]


def test_cold_start_without_blocker_is_recovering():
    assert evaluate(GateState()) == Status.RECOVERING


def test_preflight_failure_with_exact_blocker_is_blocked():
    assert evaluate(GateState(), exact_blockers=["provider unavailable"]) == Status.BLOCKED


def test_current_blocker_precedes_complete():
    g = GateState(**_all_true())
    assert evaluate(g, exact_blockers=["current provider hold"]) == Status.BLOCKED


def test_non_boolean_gate_is_rejected():
    values = _all_true()
    values["readback_verified"] = "false"
    try:
        from_mapping(values)
    except ValueError as exc:
        assert "must be a bool" in str(exc)
    else:
        raise AssertionError("string gate value was accepted")


def test_receipt_rejects_false_complete():
    values = _all_true()
    values["readback_verified"] = False
    try:
        validate_receipt(_receipt(values, "COMPLETE"))
    except ValueError as exc:
        assert "contradicts gate state" in str(exc) or "COMPLETE requires" in str(exc)
    else:
        raise AssertionError("false COMPLETE receipt was accepted")


def test_receipt_rejects_missing_gate():
    values = _all_true()
    values.pop("readback_verified")
    try:
        validate_receipt(_receipt(values, "EXECUTING"))
    except ValueError as exc:
        assert "exactly 16 gates" in str(exc)
    else:
        raise AssertionError("receipt with missing gate was accepted")


def test_receipt_rejects_string_boolean():
    values = _all_true()
    values["readback_verified"] = "false"
    try:
        validate_receipt(_receipt(values, "COMPLETE"))
    except ValueError as exc:
        assert "must be a bool" in str(exc)
    else:
        raise AssertionError("receipt with string boolean was accepted")


def test_receipt_rejects_complete_without_persistence_receipt():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["persistence_receipts"] = []
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "persistence_written requires" in str(exc)
    else:
        raise AssertionError("COMPLETE without persistence receipt was accepted")


def test_receipt_rejects_complete_without_readback_receipt():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["readback_receipts"] = []
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "readback_verified requires" in str(exc)
    else:
        raise AssertionError("COMPLETE without readback receipt was accepted")


def test_receipt_rejects_complete_without_verification_receipt():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["verification"] = []
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "verification_passed requires" in str(exc)
    else:
        raise AssertionError("COMPLETE without verification receipt was accepted")


def test_receipt_accepts_consistent_complete():
    validate_receipt(_receipt(_all_true(), "COMPLETE"))


def test_receipt_accepts_current_blocker_only_as_blocked():
    receipt = _receipt(_all_true(), "BLOCKED", ["current provider hold"])
    validate_receipt(receipt)
