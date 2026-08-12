from jack.src.jack_relentless_gate import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    GateState,
    Status,
    completion_ready,
    evaluate,
    missing,
    validate_receipt,
)


def _all_true():
    return {name: True for name in GateState.__dataclass_fields__}


def _receipt(gates: dict[str, bool], status: str, blockers=None):
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "gates": gates,
        "status": status,
        "exact_blockers": blockers or [],
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


def test_receipt_accepts_consistent_complete():
    validate_receipt(_receipt(_all_true(), "COMPLETE"))
