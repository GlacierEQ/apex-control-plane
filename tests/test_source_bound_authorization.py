from __future__ import annotations

import hashlib
import json

import pytest

from source_bound_authorization import (
    AuthorizationScopeError,
    authorize_constituent_action,
    parse_authorization_envelope,
    verify_authorization_source,
)


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def envelope(**overrides):
    source_ref = "source:operator-authority"
    payload = {
        "source_ref": source_ref,
        "kind": "plan_batch",
        "connector": "github",
        "operations": ["issue.create", "pull_request.create"],
        "target_constraints": {"repository": "GlacierEQ/apex-control-plane"},
        "provider_input_constraints": {"title": "Authority repair"},
        "consequence_prefixes": ["Creates one bounded"],
        "plan_ref": "plan://authority-scope-repair",
        "allow_destructive": False,
    }
    payload.update(overrides)
    scope = {
        "schema_version": 1,
        "source_ref": payload["source_ref"],
        "kind": payload["kind"],
        "connector": payload["connector"],
        "operations": sorted(payload["operations"]),
        "target_constraints": payload["target_constraints"],
        "provider_input_constraints": payload.get("provider_input_constraints", {}),
        "consequence_prefixes": payload.get("consequence_prefixes", []),
        "plan_ref": payload.get("plan_ref"),
        "allow_destructive": payload.get("allow_destructive") is True,
    }
    source = json.dumps(
        {"authorization_scope": scope},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["source_binding"] = {
        "proposition_id": "operator:authorization:test",
        "source_kind": "operator_record",
        "source_ref": source_ref,
        "source_sha256": _sha(source),
        "span_start_byte": 0,
        "span_end_byte": len(source),
        "span_sha256": _sha(source),
        "temporal_context": "test-current",
        "contradiction_state": "active",
        "superseded_by": None,
        "verification_state": "source_resolved",
    }
    return parse_authorization_envelope(payload), source


def _authorize(auth):
    return authorize_constituent_action(
        auth,
        connector="github",
        operation="pull_request.create",
        target={
            "repository": "GlacierEQ/apex-control-plane",
            "head": "repair/auth-scope",
        },
        provider_input={"title": "Authority repair", "body": "bounded payload"},
        consequence="Creates one bounded repair pull request.",
    )


def test_plan_batch_authorizes_routine_constituent_without_per_action_approval():
    auth, source = envelope()
    assert verify_authorization_source(auth, resolver=lambda ref: source) == auth.envelope_sha256
    assert _authorize(auth) == auth.envelope_sha256


def test_explicit_action_remains_supported():
    auth, source = envelope(kind="explicit_action", operations=["pull_request.create"], plan_ref=None)
    verify_authorization_source(auth, resolver=lambda ref: source)
    assert _authorize(auth) == auth.envelope_sha256


def test_submitted_scope_cannot_outvote_independently_resolved_operator_source():
    auth, source = envelope()
    forged, _ = envelope(operations=["issue.create", "pull_request.create", "repository.delete"])
    with pytest.raises(AuthorizationScopeError, match="does not match independently resolved"):
        verify_authorization_source(forged, resolver=lambda ref: source)
    assert auth.operations != forged.operations


def test_source_readback_failure_stays_unresolved_not_authorized():
    auth, _ = envelope()

    def unresolved(ref: str) -> bytes:
        raise RuntimeError("provider unavailable")

    with pytest.raises(AuthorizationScopeError, match="source readback unresolved"):
        verify_authorization_source(auth, resolver=unresolved)


@pytest.mark.parametrize(
    ("connector", "operation", "target", "provider_input", "consequence"),
    [
        (
            "supabase",
            "pull_request.create",
            {"repository": "GlacierEQ/apex-control-plane"},
            {"title": "Authority repair"},
            "Creates one bounded repair pull request.",
        ),
        (
            "github",
            "repository.delete",
            {"repository": "GlacierEQ/apex-control-plane"},
            {"title": "Authority repair"},
            "Creates one bounded repair pull request.",
        ),
        (
            "github",
            "pull_request.create",
            {"repository": "GlacierEQ/other"},
            {"title": "Authority repair"},
            "Creates one bounded repair pull request.",
        ),
        (
            "github",
            "pull_request.create",
            {"repository": "GlacierEQ/apex-control-plane"},
            {"title": "Different title"},
            "Creates one bounded repair pull request.",
        ),
        (
            "github",
            "pull_request.create",
            {"repository": "GlacierEQ/apex-control-plane"},
            {"title": "Authority repair"},
            "Deletes the repository.",
        ),
    ],
)
def test_out_of_scope_constituent_is_rejected(
    connector, operation, target, provider_input, consequence
):
    auth, _ = envelope()
    with pytest.raises(AuthorizationScopeError):
        authorize_constituent_action(
            auth,
            connector=connector,
            operation=operation,
            target=target,
            provider_input=provider_input,
            consequence=consequence,
        )


def test_destructive_action_requires_source_bound_operator_authority():
    auth, _ = envelope()
    with pytest.raises(AuthorizationScopeError, match="destructive action"):
        authorize_constituent_action(
            auth,
            connector="github",
            operation="pull_request.create",
            target={"repository": "GlacierEQ/apex-control-plane"},
            provider_input={"title": "Authority repair"},
            consequence="Creates one bounded repair pull request.",
            destructive=True,
        )


def test_destructive_action_can_be_source_authorized():
    auth, source = envelope(allow_destructive=True)
    verify_authorization_source(auth, resolver=lambda ref: source)
    assert authorize_constituent_action(
        auth,
        connector="github",
        operation="pull_request.create",
        target={"repository": "GlacierEQ/apex-control-plane"},
        provider_input={"title": "Authority repair"},
        consequence="Creates one bounded repair pull request.",
        destructive=True,
    ) == auth.envelope_sha256


def test_plan_batch_requires_plan_reference():
    with pytest.raises(AuthorizationScopeError, match="plan_ref"):
        envelope(plan_ref=None)


def test_envelope_digest_is_stable_across_operation_order():
    left, _ = envelope(operations=["issue.create", "pull_request.create"])
    right, _ = envelope(operations=["pull_request.create", "issue.create"])
    assert left.envelope_sha256 == right.envelope_sha256
