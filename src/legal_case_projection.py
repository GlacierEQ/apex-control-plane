"""Read-only GlacierEQ legal-case mission projection.

This adapter exposes the live structured case projection by stable ``case_id``.
It is deliberately not a source-of-truth layer: Operator firsthand records,
provider-native records, dedicated case repositories, and source bytes retain
proposition-specific authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
import re
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TABLES = {
    "case": "apex_legal_cases",
    "actors": "apex_legal_case_actors",
    "propositions": "apex_legal_case_propositions",
    "contradictions": "apex_legal_case_contradictions",
    "evidence_targets": "apex_legal_case_evidence_targets",
    "receipts": "apex_legal_projection_receipts",
}


class LegalCaseProjectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LegalCaseProjectionConfig:
    supabase_url: str
    api_key: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "LegalCaseProjectionConfig":
        url = (
            os.getenv("GLACIEREQ_SUPABASE_URL", "").strip()
            or os.getenv("SUPABASE_URL", "").strip()
        ).rstrip("/")
        key = (
            os.getenv("GLACIEREQ_SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.getenv("SUPABASE_ANON_KEY", "").strip()
        )
        if not url:
            raise LegalCaseProjectionError("GlacierEQ Supabase URL is required")
        if not key:
            raise LegalCaseProjectionError("a Supabase API key is required")
        if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise LegalCaseProjectionError("Supabase URL must use https or localhost")
        return cls(url, key)


class LegalCaseProjection:
    """Read one case-scoped projection without granting it global authority."""

    def __init__(self, config: LegalCaseProjectionConfig):
        self.config = config

    @staticmethod
    def _case_id(value: str) -> str:
        if not CASE_ID_RE.fullmatch(value):
            raise LegalCaseProjectionError("invalid case_id")
        return value

    def _get_rows(self, table_key: str, case_id: str) -> list[dict[str, Any]]:
        if table_key not in TABLES:
            raise LegalCaseProjectionError(f"unsupported table key: {table_key}")
        case_id = self._case_id(case_id)
        query = urlencode({"select": "*", "case_id": f"eq.{case_id}"}, safe=".*:,")
        request = Request(
            f"{self.config.supabase_url}/rest/v1/{TABLES[table_key]}?{query}",
            method="GET",
            headers={
                "apikey": self.config.api_key,
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
        except Exception as exc:
            raise LegalCaseProjectionError(f"projection read failed: {table_key}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise LegalCaseProjectionError("projection returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise LegalCaseProjectionError("projection response must be an array")
        return [row for row in payload if isinstance(row, dict)]

    def get_case(self, case_id: str) -> dict[str, Any]:
        rows = self._get_rows("case", case_id)
        if len(rows) != 1:
            raise LegalCaseProjectionError(
                f"expected exactly one case row for {case_id}; found {len(rows)}"
            )
        return rows[0]

    def get_bundle(self, case_id: str) -> dict[str, Any]:
        case = self.get_case(case_id)
        bundle: dict[str, Any] = {
            "case": case,
            "actors": self._get_rows("actors", case_id),
            "propositions": self._get_rows("propositions", case_id),
            "contradictions": self._get_rows("contradictions", case_id),
            "evidence_targets": self._get_rows("evidence_targets", case_id),
            "receipts": self._get_rows("receipts", case_id),
        }
        bundle["counts"] = {
            key: 1 if key == "case" else len(value)
            for key, value in bundle.items()
            if key != "counts"
        }
        bundle["projection_semantics"] = {
            "authority": "mission_projection_only",
            "source_bound_case_records_retain_authority": True,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        return bundle

    def readiness(self, case_id: str) -> Mapping[str, Any]:
        bundle = self.get_bundle(case_id)
        counts = bundle["counts"]
        critical_targets = [
            row
            for row in bundle["evidence_targets"]
            if str(row.get("priority", "")).upper() == "CRITICAL"
        ]
        return {
            "case_id": case_id,
            "case_loaded": counts["case"] == 1,
            "has_actors": counts["actors"] > 0,
            "has_propositions": counts["propositions"] > 0,
            "has_contradictions": counts["contradictions"] > 0,
            "has_evidence_targets": counts["evidence_targets"] > 0,
            "has_receipts": counts["receipts"] > 0,
            "critical_targets": len(critical_targets),
            "counts": counts,
            "authority": "mission_projection_only",
        }
