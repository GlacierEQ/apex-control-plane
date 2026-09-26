from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID

import pytest

from src.supabase_receipt_projection import (
    ReceiptProjectionError,
    SupabaseReceiptProjection,
    SupabaseReceiptProjectionConfig,
)

TEST_KEY = "test_api_key_do_not_use_in_production"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _digest(value):
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _receipt(*, expected=None, observed=None, provider_ids=("github:merge:42",)):
    receipt = {
        "receipt_id": "rcpt_test_001",
        "mission_id": "mission_001",
        "correlation_id": "corr_001",
        "result": "SUCCEEDED",
        "expected": {"merged": True} if expected is None else expected,
        "observed": {"merged": True} if observed is None else observed,
        "provider_receipt_ids": provider_ids,
        "previous_receipt_hash": "GENESIS_ROOT",
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


class _StatefulOpener:
    def __init__(self, *, ambiguous_post=False):
        self.rows = []
        self.calls = []
        self.post_count = 0
        self.ambiguous_post = ambiguous_post

    def __call__(self, request, timeout):
        self.calls.append(request)
        if request.method == "GET" and "action=eq." in request.full_url:
            action = request.full_url.split("action=eq.", 1)[1]
            from urllib.parse import unquote

            action = unquote(action)
            return _Response([r for r in self.rows if r.get("action") == action])
        if request.method == "POST":
            self.post_count += 1
            body = json.loads(request.data.decode())
            row = {"id": len(self.rows) + 77, **body}
            self.rows.append(row)
            if self.ambiguous_post:
                self.ambiguous_post = False
                raise OSError("connection lost after commit")
            return _Response([row])
        if request.method == "GET" and "id=eq." in request.full_url:
            rid = request.full_url.split("id=eq.", 1)[1]
            return _Response([r for r in self.rows if str(r.get("id")) == str(rid)])
        raise AssertionError(request.full_url)


def test_unconfigured_projection_is_unavailable_not_mock_success():
    projection = SupabaseReceiptProjection(SupabaseReceiptProjectionConfig("", ""))
    assert projection.project(_receipt()) == {
        "status": "UNAVAILABLE",
        "reason": "SUPABASE_NOT_CONFIGURED",
    }


def test_non_tls_remote_endpoint_is_rejected_before_network_use():
    with pytest.raises(ReceiptProjectionError, match="https"):
        SupabaseReceiptProjectionConfig("http://example.supabase.co", TEST_KEY)


def test_projection_rejects_scalar_provider_receipt_ids():
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("network should not run")
        ),
    )
    receipt = _receipt()
    receipt["provider_receipt_ids"] = "github:merge:42"
    with pytest.raises(ReceiptProjectionError, match="list or tuple"):
        projection.project(receipt)


def test_projection_rejects_receipt_hash_that_does_not_match_payload():
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("network should not run")
        ),
    )
    receipt = _receipt()
    receipt["observed"] = {"merged": False}
    with pytest.raises(ReceiptProjectionError, match="receipt_hash"):
        projection.project(receipt)


def test_projection_preserves_current_receipt_identity_and_stores_digests_not_raw_state():
    opener = _StatefulOpener()
    raw_secret = "private-body-DO-NOT-PROJECT"
    receipt = _receipt(
        expected={"body": raw_secret},
        observed={"body": raw_secret},
    )
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=opener,
    )
    applied = projection.project(receipt)
    assert applied["status"] == "APPLIED"
    row = opener.rows[0]
    details = json.loads(row["details"])
    assert row["action"] == "receipt_projection:rcpt_test_001"
    assert details["receipt_id"] == "rcpt_test_001"
    assert details["mission_id"] == "mission_001"
    assert details["correlation_id"] == "corr_001"
    assert details["result"] == "SUCCEEDED"
    assert details["expected_digest"] == _digest({"body": raw_secret})
    assert details["observed_digest"] == _digest({"body": raw_secret})
    assert raw_secret not in row["details"]
    assert "expected" not in details and "observed" not in details


def test_projection_accepts_receipt_values_supported_by_hash_canonicalization():
    opener = _StatefulOpener()
    receipt = _receipt(
        expected={
            "at": datetime(2026, 9, 25, tzinfo=UTC),
            "amount": Decimal("1.25"),
        },
        observed={
            "id": UUID("12345678-1234-5678-1234-567812345678"),
        },
    )
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=opener,
    )
    assert projection.project(receipt)["status"] == "APPLIED"


def test_verify_binds_readback_to_exact_projected_receipt_content():
    opener = _StatefulOpener()
    receipt = _receipt()
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=opener,
    )
    applied = projection.project(receipt)
    readback = projection.readback(applied["remote_id"])
    assert projection.verify(applied["remote_id"], readback, receipt) is True

    tampered = dict(readback)
    record = dict(readback["record"])
    details = json.loads(record["details"])
    details["receipt_hash"] = "different"
    record["details"] = json.dumps(details, sort_keys=True)
    tampered["record"] = record
    assert projection.verify(applied["remote_id"], tampered, receipt) is False


def test_retry_reuses_existing_projection_instead_of_inserting_duplicate():
    opener = _StatefulOpener()
    receipt = _receipt()
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=opener,
    )
    first = projection.project(receipt)
    second = projection.project(receipt)
    assert first["remote_id"] == second["remote_id"]
    assert opener.post_count == 1
    assert second.get("idempotent_reuse") is True


def test_ambiguous_post_is_reconciled_by_readback_without_duplicate_retry():
    opener = _StatefulOpener(ambiguous_post=True)
    receipt = _receipt()
    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", TEST_KEY),
        opener=opener,
    )
    result = projection.project(receipt)
    assert result["status"] == "APPLIED"
    assert result.get("reconciled_after_ambiguous_write") is True
    assert opener.post_count == 1
