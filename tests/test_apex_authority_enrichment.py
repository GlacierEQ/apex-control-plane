from __future__ import annotations

import json
import os

import pytest

import apex_enforced_startup as apex


def _reset_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", str(tmp_path))
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.delenv("CASEY_AUTO_BOOT_DISABLE", raising=False)
    monkeypatch.delenv("GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED", raising=False)
    monkeypatch.setattr(apex, "_IN_PROCESS", None)


def test_missing_receipt_is_durable_nonblocking_enrichment(monkeypatch, tmp_path) -> None:
    _reset_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(apex, "receipt_from_environment", lambda: None)

    validation = apex.automatic_apex_enforced_startup()

    assert validation is not None
    assert validation.ok is True
    assert validation.status == "complete"
    assert validation.errors == (
        "startup proof enrichment pending: no boot receipt supplied",
    )
    assert os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] == "complete_enrichment_pending"
    assert "GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED" not in os.environ

    records = list(tmp_path.glob("apex_enforced_startup-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["status"] == "enrichment_pending"
    assert record["execution_permission_effect"] == "none"
    assert record["state_promotion_limited"] is True
    assert record["retryable"] is True


def test_pending_enrichment_retries_and_promotes_without_restart(monkeypatch, tmp_path) -> None:
    _reset_runtime(monkeypatch, tmp_path)
    current_receipt = {"value": None}
    monkeypatch.setattr(apex, "receipt_from_environment", lambda: current_receipt["value"])

    first = apex.automatic_apex_enforced_startup()
    assert first is not None
    assert first.errors

    current_receipt["value"] = {"apex_startup": {"proof": "now-present"}}
    monkeypatch.setattr(apex, "validate_apex_startup_receipt", lambda policy, receipt: ())

    assert apex.get_in_process_apex_validation() is None
    second = apex.automatic_apex_enforced_startup()

    assert second is not None
    assert second.ok is True
    assert second.status == "complete"
    assert second.errors == ()
    assert apex.get_in_process_apex_validation() is second
    assert os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] == "complete"
    assert os.environ["GLACIEREQ_STARTUP_ENRICHMENT_STATUS"] == "complete"


def test_incomplete_receipt_is_enrichment_not_global_permission_gate(monkeypatch, tmp_path) -> None:
    _reset_runtime(monkeypatch, tmp_path)
    receipt = {"apex_startup": {}}
    monkeypatch.setattr(apex, "receipt_from_environment", lambda: receipt)
    monkeypatch.setattr(
        apex,
        "validate_apex_startup_receipt",
        lambda policy, value: ("apex_startup.target_state must be non-empty",),
    )

    validation = apex.automatic_apex_enforced_startup()

    assert validation is not None
    assert validation.ok is True
    assert validation.status == "complete"
    assert validation.errors == (
        "startup proof enrichment pending: apex_startup.target_state must be non-empty",
    )
    assert os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] == "complete_enrichment_pending"


def test_explicit_contradiction_remains_route_local_while_global_state_is_uplift(monkeypatch, tmp_path) -> None:
    _reset_runtime(monkeypatch, tmp_path)
    receipt = {"apex_startup": {"contradiction_status": "open_blocker"}}
    monkeypatch.setattr(apex, "receipt_from_environment", lambda: receipt)
    monkeypatch.setattr(
        apex,
        "validate_apex_startup_receipt",
        lambda policy, value: ("apex_startup has an unresolved contradiction blocker",),
    )

    validation = apex.automatic_apex_enforced_startup()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "continuation_required"
    assert os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] == "uplift_required"

    records = list(tmp_path.glob("apex_enforced_startup-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["status"] == "uplift_required"


def test_explicit_authority_and_scope_negatives_are_blocking() -> None:
    policy = {
        "authority": "operator_intent",
        "objective": "maximum_coherent_advance",
        "mutation_interlock": {"required_true_fields": ["standing_authorizations_preserved"]},
        "path_requirements": {"unsupported_scope_narrowing": False},
    }
    receipt = {
        "apex_startup": {
            "authority": "operator_intent",
            "objective": "maximum_coherent_advance",
            "standing_authorizations_preserved": False,
            "operator_plan_authorized": False,
            "operator_scope_binding": {
                "preserved": False,
                "narrowed": True,
                "operator_narrowing_authorization_ref": "",
            },
            "selected_path": {"unsupported_scope_narrowing": True},
            "operator_authorization": {"authorized": False},
        }
    }

    blockers = apex._explicit_blocking_receipt_errors(policy, receipt)

    assert "apex_startup.standing_authorizations_preserved is explicitly false" in blockers
    assert "operator_plan_authorized is explicitly false" in blockers
    assert "operator_scope_binding explicitly does not preserve Operator scope" in blockers
    assert "Operator scope was explicitly narrowed without Operator authorization" in blockers
    assert any("unsupported_scope_narrowing" in item for item in blockers)
    assert "operator_authorization.authorized is explicitly false" in blockers



def test_policy_rejects_authorization_semantic_drift(tmp_path) -> None:
    policy = apex.load_apex_policy()
    policy["mutation_interlock"]["startup_receipt_is_execution_permission"] = True
    target = tmp_path / "bad-policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(
        apex.BootError,
        match="startup_receipt_is_execution_permission must be False",
    ):
        apex.load_apex_policy(target)


def test_runtime_consumes_nonblocking_proof_policy() -> None:
    policy = apex.load_apex_policy()
    assert apex._incomplete_proof_is_nonblocking(policy) is True
