from __future__ import annotations

import pytest

from source_bound_authorization import (
    AuthorizationScopeError,
    authorize_constituent_action,
    parse_authorization_envelope,
)


def envelope(**overrides):
    payload = {
        "source_ref": "operator://2026-09-20/authority-alignment",
        "kind": "plan_batch",
        "connector": "github",
        "operations": ["issue.create", "pull_request.create"],
        "target_constraints": {"repository": "GlacierEQ/apex-control-plane"},
        "plan_ref": "plan://authority-scope-repair",
    }
    payload.update(overrides)
    return parse_authorization_envelope(payload)


def test_plan_batch_authorizes_routine_constituent_without_per_action_approval():
    auth = envelope()
    digest = authorize_constituent_action(
        auth,
        connector="github",
        operation="pull_request.create",
        target={"repository": "GlacierEQ/apex-control-plane", "head": "repair/auth-scope-2026-09-20"},
    )
    assert digest == auth.envelope_sha256


def test_explicit_action_remains_supported():
    auth = envelope(kind="explicit_action", operations=["issue.create"], plan_ref=None)
    assert authorize_constituent_action(
        auth,
        connector="github",
        operation="issue.create",
        target={"repository": "GlacierEQ/apex-control-plane"},
    ) == auth.envelope_sha256


@pytest.mark.parametrize(
    ("connector", "operation", "target"),
    [
        ("supabase", "pull_request.create", {"repository": "GlacierEQ/apex-control-plane"}),
        ("github", "repository.delete", {"repository": "GlacierEQ/apex-control-plane"}),
        ("github", "pull_request.create", {"repository": "GlacierEQ/other"}),
    ],
)
def test_out_of_scope_constituent_is_rejected(connector, operation, target):
    with pytest.raises(AuthorizationScopeError):
        authorize_constituent_action(envelope(), connector=connector, operation=operation, target=target)


def test_destructive_action_requires_explicit_authority():
    with pytest.raises(AuthorizationScopeError, match="destructive action"):
        authorize_constituent_action(
            envelope(),
            connector="github",
            operation="issue.create",
            target={"repository": "GlacierEQ/apex-control-plane"},
            destructive=True,
        )


def test_material_strategy_delta_requires_explicit_authority():
    with pytest.raises(AuthorizationScopeError, match="material strategy delta"):
        authorize_constituent_action(
            envelope(),
            connector="github",
            operation="issue.create",
            target={"repository": "GlacierEQ/apex-control-plane"},
            material_strategy_delta=True,
        )


def test_destructive_and_material_delta_can_be_explicitly_authorized():
    auth = envelope(allow_destructive=True, allow_material_strategy_delta=True)
    assert authorize_constituent_action(
        auth,
        connector="github",
        operation="issue.create",
        target={"repository": "GlacierEQ/apex-control-plane"},
        destructive=True,
        material_strategy_delta=True,
    ) == auth.envelope_sha256


def test_plan_batch_requires_plan_reference():
    with pytest.raises(AuthorizationScopeError, match="plan_ref"):
        envelope(plan_ref=None)


def test_envelope_digest_is_stable_across_operation_order():
    left = envelope(operations=["issue.create", "pull_request.create"])
    right = envelope(operations=["pull_request.create", "issue.create"])
    assert left.envelope_sha256 == right.envelope_sha256
