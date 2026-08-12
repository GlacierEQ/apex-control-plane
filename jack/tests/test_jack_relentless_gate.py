from src.jack_relentless_gate import GateState, Status, completion_ready, evaluate, missing

def test_all_true_is_complete():
    g = GateState(**{name: True for name in GateState.__dataclass_fields__})
    assert completion_ready(g)
    assert evaluate(g) == Status.COMPLETE
    assert missing(g) == []

def test_one_missing_cannot_complete():
    values = {name: True for name in GateState.__dataclass_fields__}
    values["readback_verified"] = False
    g = GateState(**values)
    assert not completion_ready(g)
    assert evaluate(g) == Status.EXECUTING
    assert missing(g) == ["readback_verified"]

def test_preflight_failure_with_exact_blocker_is_blocked():
    g = GateState()
    assert evaluate(g, exact_blockers=["provider unavailable"]) == Status.BLOCKED
