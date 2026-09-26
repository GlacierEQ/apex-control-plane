"""Projection-only Supabase persistence for provider-native execution receipts.

Donor provenance: ``feat/durable-workflow-machine/adapters/supabase/adapter.py``.
This compatibility harvest preserves physical Supabase projection/readback while
keeping provider-native receipts authoritative. Projection records contain only
receipt identity, provider references, and digests of provider state.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class ReceiptProjectionError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode()).hexdigest()


def _required_text(receipt: Mapping[str, Any], field: str) -> str:
    value = receipt.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReceiptProjectionError(f"{field} required before projection")
    return value.strip()


def _normalized_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    raw_ids = receipt.get("provider_receipt_ids", ())
    if isinstance(raw_ids, (str, bytes)) or not isinstance(raw_ids, (list, tuple)):
        raise ReceiptProjectionError(
            "provider_receipt_ids must be a list or tuple of ids"
        )

    provider_ids: list[str] = []
    for value in raw_ids:
        if not isinstance(value, str) or not value.strip():
            raise ReceiptProjectionError(
                "provider_receipt_ids must contain non-empty strings"
            )
        if value != value.strip():
            raise ReceiptProjectionError(
                "provider_receipt_ids must not contain surrounding whitespace"
            )
        provider_ids.append(value)

    if not provider_ids:
        raise ReceiptProjectionError(
            "provider-native receipt id required before projection"
        )

    normalized = {
        "receipt_id": _required_text(receipt, "receipt_id"),
        "mission_id": _required_text(receipt, "mission_id"),
        "correlation_id": _required_text(receipt, "correlation_id"),
        "result": _required_text(receipt, "result"),
        "expected": receipt.get("expected"),
        "observed": receipt.get("observed"),
        "provider_receipt_ids": tuple(provider_ids),
        "previous_receipt_hash": _required_text(
            receipt,
            "previous_receipt_hash",
        ),
    }
    receipt_hash = _required_text(receipt, "receipt_hash")
    if receipt_hash != _digest(normalized):
        raise ReceiptProjectionError(
            "receipt_hash does not match receipt payload"
        )
    normalized["receipt_hash"] = receipt_hash
    return normalized


def _projection_action(receipt: Mapping[str, Any]) -> str:
    return f"receipt_projection:{receipt['receipt_id']}"


def _projection_details(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "projection_semantics": "provider_receipt_projection_only",
        "receipt_id": receipt["receipt_id"],
        "mission_id": receipt["mission_id"],
        "correlation_id": receipt["correlation_id"],
        "result": receipt["result"],
        "provider_receipt_ids": list(receipt["provider_receipt_ids"]),
        "receipt_hash": receipt["receipt_hash"],
        "previous_receipt_hash": receipt["previous_receipt_hash"],
        "expected_digest": _digest(receipt.get("expected")),
        "observed_digest": _digest(receipt.get("observed")),
    }


def _decoded_details(
    record: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    raw = record.get("details")
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _record_matches_receipt(
    record: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    remote_id: Any | None = None,
) -> bool:
    if remote_id is not None and str(record.get("id")) != str(remote_id):
        return False
    if record.get("action") != _projection_action(receipt):
        return False
    if record.get("status") != "projected":
        return False
    details = _decoded_details(record)
    return details == _projection_details(receipt)


@dataclass(frozen=True, slots=True)
class SupabaseReceiptProjectionConfig:
    url: str
    api_key: str
    table: str = "apex_ops_log"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        url = self.url.strip()
        if not url:
            return
        parsed = urlparse(url)
        is_local_http = (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if parsed.scheme != "https" and not is_local_http:
            raise ReceiptProjectionError(
                "Supabase URL must use https or localhost"
            )

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

    def _headers(
        self,
        *,
        representation: bool = False,
    ) -> dict[str, str]:
        headers = {
            "apikey": self.config.api_key,
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if representation:
            headers["Prefer"] = "return=representation"
        return headers

    def _rows_for_action(
        self,
        action: str,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                "select": "*",
                "action": f"eq.{action}",
            },
            safe=".*:,",
        )
        endpoint = (
            f"{self.config.url.rstrip('/')}"
            f"/rest/v1/{self.config.table}?{query}"
        )
        request = Request(
            endpoint,
            headers=self._headers(),
            method="GET",
        )
        try:
            with self._opener(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {
                "status": "FAILED",
                "error": str(exc),
                "rows": (),
            }
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            for row in rows
        ):
            return {
                "status": "FAILED",
                "reason": "INVALID_PROVIDER_READBACK",
                "rows": (),
            }
        return {
            "status": "OBSERVED" if rows else "NOT_OBSERVED",
            "rows": tuple(rows),
        }

    def _existing_projection(
        self,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        lookup = self._rows_for_action(
            _projection_action(receipt)
        )
        if lookup["status"] == "FAILED":
            return {
                "status": "FAILED",
                "reason": "IDEMPOTENCY_READBACK_FAILED",
                **lookup,
            }

        rows = lookup["rows"]
        matches = [
            row
            for row in rows
            if _record_matches_receipt(
                row,
                receipt,
            )
        ]
        if len(matches) == 1 and len(rows) == 1:
            return {
                "status": "OBSERVED",
                "record": matches[0],
            }
        if len(matches) > 1:
            return {
                "status": "FAILED",
                "reason": "DUPLICATE_PROJECTIONS_DETECTED",
            }
        if rows:
            return {
                "status": "FAILED",
                "reason": "RECEIPT_IDENTITY_CONFLICT",
            }
        return {"status": "NOT_OBSERVED"}

    def project(
        self,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self.config.configured:
            return {
                "status": "UNAVAILABLE",
                "reason": "SUPABASE_NOT_CONFIGURED",
            }

        normalized = _normalized_receipt(receipt)
        existing = self._existing_projection(normalized)
        if existing["status"] == "FAILED":
            return existing
        if existing["status"] == "OBSERVED":
            row = existing["record"]
            return {
                "status": "APPLIED",
                "remote_id": row.get("id"),
                "provider_record": row,
                "idempotent_reuse": True,
            }

        payload = {
            "action": _projection_action(normalized),
            "status": "projected",
            "details": json.dumps(
                _projection_details(normalized),
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        endpoint = (
            f"{self.config.url.rstrip('/')}"
            f"/rest/v1/{self.config.table}"
        )
        request = Request(
            endpoint,
            data=json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers=self._headers(representation=True),
            method="POST",
        )
        try:
            with self._opener(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            reconciled = self._existing_projection(
                normalized
            )
            if reconciled.get("status") == "OBSERVED":
                row = reconciled["record"]
                return {
                    "status": "APPLIED",
                    "remote_id": row.get("id"),
                    "provider_record": row,
                    "reconciled_after_ambiguous_write": True,
                }
            return {
                "status": "FAILED",
                "error": str(exc),
                "reconciliation": reconciled,
            }

        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            return {
                "status": "FAILED",
                "reason": "NO_PROVIDER_RECORD_RETURNED",
            }

        row = rows[0]
        remote_id = row.get("id")
        if remote_id is None:
            return {
                "status": "FAILED",
                "reason": "PROVIDER_RECORD_ID_MISSING",
            }
        if not _record_matches_receipt(
            row,
            normalized,
            remote_id=remote_id,
        ):
            return {
                "status": "FAILED",
                "reason": "PROVIDER_RETURNED_MISMATCHED_PROJECTION",
            }
        return {
            "status": "APPLIED",
            "remote_id": remote_id,
            "provider_record": row,
        }

    def readback(
        self,
        remote_id: Any,
    ) -> dict[str, Any]:
        if not self.config.configured:
            return {
                "status": "UNAVAILABLE",
                "observed": False,
                "reason": "SUPABASE_NOT_CONFIGURED",
            }
        query = urlencode(
            {
                "select": "*",
                "id": f"eq.{remote_id}",
            },
            safe=".*:,",
        )
        endpoint = (
            f"{self.config.url.rstrip('/')}"
            f"/rest/v1/{self.config.table}?{query}"
        )
        request = Request(
            endpoint,
            headers=self._headers(),
            method="GET",
        )
        try:
            with self._opener(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {
                "status": "FAILED",
                "observed": False,
                "error": str(exc),
            }

        observed = (
            isinstance(rows, list)
            and len(rows) == 1
            and isinstance(rows[0], dict)
        )
        return {
            "status": (
                "OBSERVED"
                if observed
                else "NOT_OBSERVED"
            ),
            "observed": observed,
            "record": rows[0] if observed else None,
        }

    @staticmethod
    def verify(
        remote_id: Any,
        readback: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> bool:
        if (
            readback.get("status") != "OBSERVED"
            or readback.get("observed") is not True
        ):
            return False
        record = readback.get("record")
        if not isinstance(record, Mapping):
            return False
        try:
            normalized = _normalized_receipt(receipt)
        except ReceiptProjectionError:
            return False
        return _record_matches_receipt(
            record,
            normalized,
            remote_id=remote_id,
        )
