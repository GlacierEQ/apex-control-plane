from hierarchical_epistemology import (
    Claim,
    ClaimState,
    DispatchLedger,
    HierarchicalEpistemology,
    Strategy,
    TaskSpec,
    WorkerResult,
    validate_packet,
)


def test_clear_tool_task_uses_cheap_react_path():
    task = TaskSpec("fetch one known file", well_defined=True, tools_central=True, target_state="file read")
    plan = HierarchicalEpistemology.budget(task)
    assert plan.strategy is Strategy.REACT
    assert plan.max_workers == 1
    assert plan.lane.value == "cold"


def test_long_horizon_task_uses_plan_and_execute_without_full_hot_swarm():
    task = TaskSpec("build subsystem", long_horizon=True, target_state="tested subsystem")
    plan = HierarchicalEpistemology.budget(task)
    assert plan.strategy is Strategy.PLAN_EXECUTE
    assert plan.max_workers == 3
    assert plan.lane.value == "warm"


def test_contested_high_consequence_task_uses_debate():
    task = TaskSpec(
        "weigh conflicting evidence",
        contested_evidence=True,
        high_consequence=True,
        target_state="verified position",
    )
    plan = HierarchicalEpistemology.budget(task)
    assert plan.strategy is Strategy.DEBATE
    assert plan.lane.value == "hot"
    assert plan.max_workers == 5


def test_claim_promotion_requires_receipt():
    claim = Claim("worker emitted a result", ClaimState.PROPOSED, "task:1")
    try:
        claim.promote(ClaimState.ATTEMPTED, receipt="")
    except ValueError as error:
        assert "authorization_ref" in str(error)
    else:
        raise AssertionError("unreceipted promotion was accepted")


def test_claim_promotion_is_monotonic_and_receipt_bound():
    claim = Claim("worker emitted a result", ClaimState.PROPOSED, "task:1")
    attempted = claim.promote(ClaimState.ATTEMPTED, receipt="operator:receipt-1")
    executed = attempted.promote(ClaimState.EXECUTED, receipt="runner:receipt-2")
    assert executed.state is ClaimState.EXECUTED
    assert executed.receipt == "runner:receipt-2"


def test_dispatch_ledger_deduplicates_and_early_stops_on_no_signal():
    plan = HierarchicalEpistemology.budget(TaskSpec("research", target_state="answer"))
    ledger = DispatchLedger(plan)
    ledger.record(WorkerResult("r1", unique_signal=False, retrievals=1, quota_units=1))
    ledger.record(WorkerResult("r2", unique_signal=False, retrievals=1, quota_units=1))
    stop, reason = ledger.should_stop()
    assert stop is True
    assert "marginal" in reason


def test_dispatch_ledger_preserves_conflicts_instead_of_stopping_as_if_done():
    plan = HierarchicalEpistemology.budget(TaskSpec("research", target_state="answer"))
    ledger = DispatchLedger(plan)
    ledger.record(WorkerResult("r1", unique_signal=False, conflict=True, retrievals=1))
    ledger.record(WorkerResult("r2", unique_signal=False, conflict=True, retrievals=1))
    stop, _ = ledger.should_stop()
    assert stop is False
    assert ledger.conflicts == 2


def test_verified_result_stops_dispatch():
    plan = HierarchicalEpistemology.budget(TaskSpec("verify", target_state="verified"))
    ledger = DispatchLedger(plan)
    ledger.record(WorkerResult("verifier", unique_signal=True, verified=True, retrievals=1))
    assert ledger.should_stop() == (True, "verification achieved")


def test_artifact_only_work_is_not_forward_progress():
    result = HierarchicalEpistemology.assess_progress(
        target_state_changed=False, evidence_added=False, artifact_only=True
    )
    assert result.forward_progress is False


def test_evidence_gain_is_forward_progress():
    result = HierarchicalEpistemology.assess_progress(
        target_state_changed=False, evidence_added=True, artifact_only=False
    )
    assert result.forward_progress is True


def test_correction_changes_routing_objective_and_preserves_known_good_state():
    correction = HierarchicalEpistemology.correct(
        failure="duplicate retrieval",
        failed_assumption="more context would improve quality",
        preserve=("receipt:known-good", "cache:source-1"),
    )
    assert "evidence-bearing" in correction.objective_function_change
    assert correction.preserve == ("receipt:known-good", "cache:source-1")
    assert correction.bounded_retry is True


def test_packet_is_compact_and_machine_valid():
    packet = HierarchicalEpistemology.packet(
        TaskSpec("architect", long_horizon=True, target_state="tested design"),
        pointers=("repo:sha-1", "notion:page-1"),
    )
    assert validate_packet(packet) == ()
    assert packet["pointers"] == ["repo:sha-1", "notion:page-1"]
    assert "duck" in packet["easter_egg"]


def test_invalid_packet_cannot_pass():
    assert validate_packet({"schema": "wrong", "budget": {}, "target_state": ""})
