from __future__ import annotations

import json
from src.supabase_receipt_projection import (
    ReceiptProjectionError,
    SupabaseReceiptProjection,
    SupabaseReceiptProjectionConfig,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return json.dumps(self.payload).encode()


def _receipt():
    return {
        "step": "github.merge",
        "receipt_hash": "abc123",
        "previous_receipt_hash": "prev123",
        "provider_receipt_ids": ("github:merge:42",),
        "expected": {"merged": True},
        "observed": {"merged": True},
    }


def test_unconfigured_projection_is_unavailable_not_mock_success():
    projection = SupabaseReceiptProjection(SupabaseReceiptProjectionConfig("", ""))
    assert projection.project(_receipt()) == {"status": "UNAVAILABLE", "reason": "SUPABASE_NOT_CONFIGURED"}
    assert projection.readback("42")["observed"] is False


def test_projection_requires_provider_native_receipt_id():
    projection = SupabaseReceiptProjection(SupabaseReceiptProjectionConfig("https://example.supabase.co", "key"))
    receipt = _receipt()
    receipt["provider_receipt_ids"] = ()
    try:
        projection.project(receipt)
    except ReceiptProjectionError as exc:
        assert "provider-native receipt id" in str(exc)
    else:
        raise AssertionError("projection accepted a receipt without provider provenance")


def test_projection_then_physical_readback_verifies_exact_remote_id():
    calls = []
    def opener(request, timeout):
        calls.append(request)
        if request.method == "POST":
            body = json.loads(request.data.decode())
            details = json.loads(body["details"])
            assert body["status"] == "projected"
            assert details["projection_semantics"] == "provider_receipt_projection_only"
            assert details["provider_receipt_ids"] == ["github:merge:42"]
            return _Response([{"id": 77}])
        return _Response([{"id": 77, "status": "projected"}])

    projection = SupabaseReceiptProjection(
        SupabaseReceiptProjectionConfig("https://example.supabase.co", "key"),
        opener=opener,
    )
    applied = projection.project(_receipt())
    assert applied["status"] == "APPLIED"
    readback = projection.readback(applied["remote_id"])
    assert projection.verify(applied["remote_id"], readback) is True
    assert len(calls) == 2


def test_truthiness_without_exact_record_identity_is_not_verification():
    assert SupabaseReceiptProjection.verify(77, {"status": "OBSERVED", "observed": True, "record": {"id": 78}}) is False
