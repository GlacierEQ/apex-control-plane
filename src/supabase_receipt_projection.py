"""Projection-only Supabase persistence for provider-native execution receipts.

Donor provenance: ``feat/durable-workflow-machine/adapters/supabase/adapter.py``.
This compatibility harvest keeps the donor's useful receipt projection + physical
readback mechanism while rejecting RootTruth/single-owner authority, evidentiary
fact promotion, and mock-success semantics.

Supabase is a projection target here. The originating provider receipt remains
authoritative for the provider action it describes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ReceiptProjectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SupabaseReceiptProjectionConfig:
    url: str
    api_key: str
    table: str = "apex_ops_log"
    timeout_seconds: float = 10.0

    @property
    def configured(self) -> bool:
        return bool(self.url.strip() and self.api_key.strip())


class SupabaseReceiptProjection:
    """Project an existing provider receipt and verify the projection by readback."""

    def __init__(
        self,
        config: SupabaseReceiptProjectionConfig,
        *,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.config = config
        self._opener = opener

    def _headers(self, *, representation: bool = False) -> dict[str, str]:
        headers = {
            "apikey": self.config.api_key,
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if representation:
            headers["Prefer"] = "return=representation"
        return headers

    def project(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        if not self.config.configured:
            return {"status": "UNAVAILABLE", "reason": "SUPABASE_NOT_CONFIGURED"}
        provider_ids = tuple(str(v) for v in receipt.get("provider_receipt_ids", ()) if v)
        if not provider_ids:
            raise ReceiptProjectionError("provider-native receipt id required before projection")
        receipt_hash = str(receipt.get("receipt_hash", "")).strip()
        if not receipt_hash:
            raise ReceiptProjectionError("receipt_hash required before projection")

        payload = {
            "action": f"receipt_projection:{receipt.get('step', 'unknown')}",
            "status": "projected",
            "details": json.dumps(
                {
                    "projection_semantics": "provider_receipt_projection_only",
                    "provider_receipt_ids": provider_ids,
                    "receipt_hash": receipt_hash,
                    "previous_receipt_hash": receipt.get("previous_receipt_hash"),
                    "expected": receipt.get("expected"),
                    "observed": receipt.get("observed"),
                },
                sort_keys=True,
            ),
        }
        endpoint = f"{self.config.url.rstrip('/')}/rest/v1/{self.config.table}"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(representation=True),
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return {"status": "FAILED", "reason": "NO_PROVIDER_RECORD_RETURNED"}
        remote_id = rows[0].get("id")
        if remote_id is None:
            return {"status": "FAILED", "reason": "PROVIDER_RECORD_ID_MISSING"}
        return {"status": "APPLIED", "remote_id": remote_id, "provider_record": rows[0]}

    def readback(self, remote_id: Any) -> dict[str, Any]:
        if not self.config.configured:
            return {"status": "UNAVAILABLE", "observed": False, "reason": "SUPABASE_NOT_CONFIGURED"}
        query = urlencode({"select": "*", "id": f"eq.{remote_id}"}, safe=".*:,")
        endpoint = f"{self.config.url.rstrip('/')}/rest/v1/{self.config.table}?{query}"
        request = Request(endpoint, headers=self._headers(), method="GET")
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"status": "FAILED", "observed": False, "error": str(exc)}
        observed = isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict)
        return {"status": "OBSERVED" if observed else "NOT_OBSERVED", "observed": observed, "record": rows[0] if observed else None}

    @staticmethod
    def verify(remote_id: Any, readback: Mapping[str, Any]) -> bool:
        if readback.get("status") != "OBSERVED" or readback.get("observed") is not True:
            return False
        record = readback.get("record")
        return isinstance(record, Mapping) and str(record.get("id")) == str(remote_id)
