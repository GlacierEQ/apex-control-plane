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
        "authority": "OPERATOR_INTENT",
        "task": "continue existing APEX work",
        "objective": "execute Operator-aligned coherent verified delta",
        "apex_owner": "GlacierEQ/apex-control-plane",
        "sources_opened": [
            {"system": "Notion", "object_id": "continuity", "opened": True}
        ],
        "actions_executed": [
            {
                "action": "write",
                "target": "existing topology",
                "provider_receipt": "git:commit",
                "executed": True,
                "verified": True,
                "state": "VERIFIED",
            }
        ],
        "verification": [
            {"check": "test", "receipt_ref": "pytest:green", "passed": True}
        ],
        "persistence_receipts": ["git:commit"],
        "readback_receipts": ["git:readback"],
        "gates": gates,
        "status": status,
        "exact_blockers": blockers or [],
        "resolved_blockers": [],
        "next_material_action": "resume next Operator-aligned unresolved delta",
    }


def test_all_true_is_complete():
    g = GateState(**_all_true())
    assert completion_ready(g)
    assert evaluate(g) == Status.COMPLETE
    assert missing(g) == []


def test_operator_asset_sovereignty_is_required_for_execution():
    values = _all_true()
    values["operator_asset_sovereignty_preserved"] = False
    g = GateState(**values)
    assert evaluate(g) == Status.RECOVERING
    assert "operator_asset_sovereignty_preserved" in missing(g)


def test_apex_owner_topology_is_required_for_execution():
    values = _all_true()
    values["apex_owner_topology_resolved"] = False
    g = GateState(**values)
    assert evaluate(g) == Status.RECOVERING
    assert "apex_owner_topology_resolved" in missing(g)


def test_legacy_owner_gate_is_not_present():
    assert "apex_owner_topology_resolved" in GateState.__dataclass_fields__
    assert "canonical_owner_resolved" not in GateState.__dataclass_fields__


def test_operator_aligned_delta_replaces_highest_value_ranking_gate():
    assert "operator_aligned_delta_selected" in GateState.__dataclass_fields__
    assert "highest_value_delta_selected" not in GateState.__dataclass_fields__


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


def test_legacy_owner_gate_is_rejected_as_unknown():
    values = _all_true()
    values["canonical_owner_resolved"] = True
    try:
        from_mapping(values)
    except ValueError as exc:
        assert "unknown Jack gate" in str(exc)
    else:
        raise AssertionError("legacy owner gate was accepted")


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
        assert "gates; missing=" in str(exc)
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


def test_receipt_requires_operator_intent_authority():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["authority"] = "repository_governance"
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "authority must be OPERATOR_INTENT" in str(exc)
    else:
        raise AssertionError("non-Operator project authority was accepted")


def test_receipt_requires_apex_owner_field():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt.pop("apex_owner")
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "apex_owner must be a non-empty string" in str(exc)
    else:
        raise AssertionError("receipt without apex_owner was accepted")


def test_executed_action_requires_execution_state_and_receipt():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["actions_executed"][0]["state"] = "PROPOSED"
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "weaker than EXECUTED" in str(exc)
    else:
        raise AssertionError("PROPOSED action was promoted to executed")

    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["actions_executed"][0]["provider_receipt"] = ""
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "requires string provider_receipt" in str(exc)
    else:
        raise AssertionError("executed action without receipt was accepted")


def test_executed_action_rejects_non_string_provider_receipts():
    for invalid in (False, 1, {}, [], ["git:commit"]):
        receipt = _receipt(_all_true(), "COMPLETE")
        receipt["actions_executed"][0]["provider_receipt"] = invalid
        try:
            validate_receipt(receipt)
        except ValueError as exc:
            assert "requires string provider_receipt" in str(exc)
        else:
            raise AssertionError(f"malformed provider receipt was accepted: {invalid!r}")


def test_verified_action_requires_executed_true():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["actions_executed"][0]["executed"] = False
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "verified action requires executed=true" in str(exc)
    else:
        raise AssertionError("verified action without execution was accepted")


def test_verified_action_requires_verified_or_stronger_state():
    receipt = _receipt(_all_true(), "COMPLETE")
    receipt["actions_executed"][0]["state"] = "EXECUTED"
    try:
        validate_receipt(receipt)
    except ValueError as exc:
        assert "weaker than VERIFIED" in str(exc)
    else:
        raise AssertionError("EXECUTED action was promoted to verified")


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
