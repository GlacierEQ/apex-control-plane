"""Read-only Supabase legal-case plane for Jack.

Case-specific facts remain in the private data plane. This public adapter only
knows the approved table contract and loads a bundle by stable case_id.
"""
from __future__ import annotations

from dataclasses import dataclass
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

class LegalCasePlaneError(RuntimeError):
    """Fail-closed legal case plane error."""

@dataclass(frozen=True)
class LegalCasePlaneConfig:
    supabase_url: str
    api_key: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "LegalCasePlaneConfig":
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.getenv("SUPABASE_ANON_KEY", "").strip()
        )
        if not url:
            raise LegalCasePlaneError("SUPABASE_URL is required")
        if not key:
            raise LegalCasePlaneError(
                "SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY is required"
            )
        if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise LegalCasePlaneError("SUPABASE_URL must use https (or localhost)")
        return cls(supabase_url=url, api_key=key)

class LegalCasePlane:
    """Read-only loader for one Jack case and its queryable control objects."""

    def __init__(self, config: LegalCasePlaneConfig):
        self.config = config

    @staticmethod
    def _validate_case_id(case_id: str) -> str:
        if not CASE_ID_RE.fullmatch(case_id):
            raise LegalCasePlaneError("invalid case_id")
        return case_id

    def _get_rows(self, table_key: str, *, case_id: str) -> list[dict[str, Any]]:
        if table_key not in TABLES:
            raise LegalCasePlaneError(f"unsupported table key: {table_key}")
        case_id = self._validate_case_id(case_id)
        query = urlencode({"select": "*", "case_id": f"eq.{case_id}"}, safe=".*:,")
        url = f"{self.config.supabase_url}/rest/v1/{TABLES[table_key]}?{query}"
        req = Request(
            url,
            method="GET",
            headers={
                "apikey": self.config.api_key,
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
        except Exception as exc:
            raise LegalCasePlaneError(f"legal case plane read failed for {table_key}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise LegalCasePlaneError("legal case plane returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise LegalCasePlaneError("legal case plane response must be a JSON array")
        return [row for row in payload if isinstance(row, dict)]

    def get_case(self, case_id: str) -> dict[str, Any]:
        rows = self._get_rows("case", case_id=case_id)
        if len(rows) != 1:
            raise LegalCasePlaneError(
                f"expected exactly one case row for {case_id}; found {len(rows)}"
            )
        return rows[0]

    def get_bundle(self, case_id: str) -> dict[str, Any]:
        case = self.get_case(case_id)
        bundle = {
            "case": case,
            "actors": self._get_rows("actors", case_id=case_id),
            "propositions": self._get_rows("propositions", case_id=case_id),
            "contradictions": self._get_rows("contradictions", case_id=case_id),
            "evidence_targets": self._get_rows("evidence_targets", case_id=case_id),
            "receipts": self._get_rows("receipts", case_id=case_id),
        }
        bundle["counts"] = {
            key: (1 if key == "case" else len(value))
            for key, value in bundle.items()
            if key != "counts"
        }
        return bundle

    def readiness(self, case_id: str) -> Mapping[str, Any]:
        bundle = self.get_bundle(case_id)
        counts = bundle["counts"]
        critical_targets = [
            row for row in bundle["evidence_targets"]
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
            "critical_open_targets": len(critical_targets),
            "counts": counts,
        }
