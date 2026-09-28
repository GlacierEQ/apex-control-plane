from datetime import UTC, datetime, timedelta

import pytest

from continuous_execution_kernel import ContinuousExecutionKernel, DurableWork, ExecutionState, ProviderReceipt
from source_bound_authorization import AuthorizationScopeKind, AuthorizationScopeError, SourceBoundAuthorization


def _auth(**overrides):
    values = dict(
        source_ref="operator:mission-42",
        kind=AuthorizationScopeKind.PLAN_BATCH,
        connector="github",
        operations=frozenset({"update_file", "merge"}),
        target_constraints={"repo": "GlacierEQ/apex-control-plane"},
        plan_ref="plan:harvest",
    )
    values.update(overrides)
    return SourceBoundAuthorization(**values)


def test_idempotent_submission_returns_original_work():
    kernel = ContinuousExecutionKernel()
    first = kernel.submit(DurableWork("m1", "c1", "harvest donor", "idem-1"))
    second = kernel.submit(DurableWork("m1", "c1", "duplicate", "idem-1"))
    assert second.work_id == first.work_id
    assert len(kernel.work) == 1


def test_plan_authority_binds_constituent_without_fresh_per_action_approval():
    kernel = ContinuousExecutionKernel()
    item = kernel.submit(DurableWork("m1", "c1", "compose donor", "idem-2"))
    bound = kernel.bind_authority(
        item.work_id, _auth(), connector="github", operation="update_file",
        target={"repo": "GlacierEQ/apex-control-plane"},
    )
    assert bound.authority_source_ref == "operator:mission-42"
    assert bound.authority_envelope_sha256


def test_out_of_scope_action_fails_membership_not_missing_fresh_approval():
    kernel = ContinuousExecutionKernel()
    item = kernel.submit(DurableWork("m1", "c1", "compose donor", "idem-3"))
    with pytest.raises(AuthorizationScopeError, match="outside the Operator authorization envelope"):
        kernel.bind_authority(item.work_id, _auth(), connector="github", operation="delete_repo",
                              target={"repo": "GlacierEQ/apex-control-plane"})


def test_material_strategy_delta_requires_renewed_operator_authority():
    kernel = ContinuousExecutionKernel()
    item = kernel.submit(DurableWork("m1", "c1", "strategy delta", "idem-4"))
    with pytest.raises(AuthorizationScopeError, match="material strategy delta"):
        kernel.bind_authority(item.work_id, _auth(), connector="github", operation="merge",
                              target={"repo": "GlacierEQ/apex-control-plane"}, material_strategy_delta=True)


def test_completion_requires_provider_receipts():
    kernel = ContinuousExecutionKernel()
    item = kernel.submit(DurableWork("m1", "c1", "execute", "idem-5", required_receipts=("mutation", "readback")))
    kernel.record_receipt(ProviderReceipt(item.work_id, "mutation", "github", "success", provider_receipt_id="commit:abc"))
    with pytest.raises(RuntimeError, match="readback"):
        kernel.complete(item.work_id)
    kernel.record_receipt(ProviderReceipt(item.work_id, "readback", "github", "verified", provider_receipt_id="blob:def"))
    assert kernel.complete(item.work_id).state is ExecutionState.COMPLETE


def test_expired_lease_reenters_waiting_without_dropping_work():
    kernel = ContinuousExecutionKernel()
    item = kernel.submit(DurableWork("m1", "c1", "execute", "idem-6"))
    leased = kernel.acquire_lease(item.work_id, "worker-a", seconds=1)
    reconciled = kernel.reconcile_expired_lease(item.work_id, now=leased.lease_expires_at + timedelta(seconds=1))
    assert reconciled.state is ExecutionState.WAITING
    assert reconciled.lease_owner is None
    assert reconciled.work_id == item.work_id
