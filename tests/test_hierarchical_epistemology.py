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


def test_clear_tool_task_uses_react_without_global_caps():
    task = TaskSpec("fetch one known file", well_defined=True, tools_central=True, target_state="file read")
    plan = HierarchicalEpistemology.plan(task)
    assert plan.strategy is Strategy.REACT
    assert plan.resource_policy == "adaptive_evidence_driven"


def test_long_horizon_task_uses_plan_and_execute():
    task = TaskSpec("build subsystem", long_horizon=True, target_state="tested subsystem")
    plan = HierarchicalEpistemology.plan(task)
    assert plan.strategy is Strategy.PLAN_EXECUTE
    assert plan.intensity == "deep"


def test_contested_high_consequence_task_uses_debate():
    task = TaskSpec("weigh conflicting evidence", contested_evidence=True, high_consequence=True, target_state="verified position")
    assert HierarchicalEpistemology.choose_strategy(task) is Strategy.DEBATE


def test_repeated_failure_routes_to_reflexion():
    task = TaskSpec("repair recurring failure", repeated_failure=True, target_state="verified repair")
    assert HierarchicalEpistemology.choose_strategy(task) is Strategy.REFLEXION


def test_tree_of_thoughts_is_reachable_for_high_consequence_choice_points():
    task = TaskSpec("choose an architecture", multiple_plausible_paths=True, high_consequence=True, target_state="selected architecture")
    assert HierarchicalEpistemology.choose_strategy(task) is Strategy.TREE_OF_THOUGHTS


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


def test_dispatch_ledger_deduplicates_without_fixed_worker_ceiling():
    ledger = DispatchLedger()
    for index in range(12):
        ledger.record(WorkerResult(f"r{index}", unique_signal=True, retrievals=1))
    assert len(ledger.dispatched) == 12
    try:
        ledger.record(WorkerResult("r1", unique_signal=True))
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate worker was accepted")


def test_low_signal_reroutes_instead_of_truncating_mission():
    ledger = DispatchLedger()
    ledger.record(WorkerResult("r1", unique_signal=False))
    ledger.record(WorkerResult("r2", unique_signal=False))
    state, reason = ledger.continuation_signal()
    assert state == "reroute"
    assert "rather than truncate mission" in reason


def test_conflicts_remain_visible_and_route_to_investigation():
    ledger = DispatchLedger()
    ledger.record(WorkerResult("r1", unique_signal=False, conflict=True))
    ledger.record(WorkerResult("r2", unique_signal=False, conflict=True))
    assert ledger.continuation_signal()[0] == "investigate"
    assert ledger.conflicts == 2


def test_verified_result_does_not_claim_global_mission_completion():
    ledger = DispatchLedger()
    ledger.record(WorkerResult("verifier", unique_signal=True, verified=True))
    state, reason = ledger.continuation_signal()
    assert state == "verified"
    assert "if mission has remaining work" in reason


def test_artifact_only_work_is_not_forward_progress():
    result = HierarchicalEpistemology.assess_progress(target_state_changed=False, evidence_added=False, artifact_only=True)
    assert result.forward_progress is False


def test_evidence_gain_is_forward_progress():
    result = HierarchicalEpistemology.assess_progress(target_state_changed=False, evidence_added=True, artifact_only=False)
    assert result.forward_progress is True


def test_correction_changes_method_and_preserves_known_good_state():
    correction = HierarchicalEpistemology.correct(failure="duplicate retrieval", failed_assumption="more context would improve quality", preserve=("receipt:known-good", "cache:source-1"))
    assert "evidence-bearing" in correction.objective_function_change
    assert correction.preserve == ("receipt:known-good", "cache:source-1")
    assert correction.retry_policy == "adaptive"


def test_packet_encodes_mesh_and_adaptive_resource_law():
    packet = HierarchicalEpistemology.packet(TaskSpec("architect", long_horizon=True, target_state="tested design"), pointers=("repo:sha-1", "provider:readback-1"))
    assert validate_packet(packet) == ()
    assert packet["pointers"] == ["repo:sha-1", "provider:readback-1"]
    assert packet["resource_policy"] == "adaptive_evidence_driven"
    assert "UNIQUE_CONTRIBUTION=0" in packet["mesh_rule"]
    assert "max_workers" not in packet
    assert "stop_rules" not in packet


def test_invalid_packet_cannot_pass():
    assert validate_packet({"schema": "wrong", "target_state": ""})
