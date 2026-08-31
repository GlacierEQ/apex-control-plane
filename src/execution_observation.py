"""Execution observation stamps for APEX.

This module is deliberately NOT an authorization layer.

It preserves the useful cryptographic property of the retired promotion-grant
mechanism: an observation can be bound to one repository, exact source SHA, and
proof-receipt digest. Verification reports whether that evidence binding is
intact. It never grants, withholds, promotes, demotes, or pauses execution.

Operator/mission intent remains the authority for project direction. Runtime
checks may report identity, integrity, reversibility, or execution failures, but
this module cannot create a stop condition.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

LOCAL_OBSERVATION_SECRET = b"glaciereq-local-execution-observation-v1"


def _digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ExecutionObservation:
    repository: str
    source_sha: str
    proof_receipt_digest: str
    observed_at: float
    mac: str

    def fingerprint(self) -> str:
        return _digest(
            {
                "repository": self.repository,
                "source_sha": self.source_sha,
                "proof_receipt_digest": self.proof_receipt_digest,
                "observed_at": self.observed_at,
                "mac": self.mac,
            }
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionObservation":
        return cls(
            repository=str(value["repository"]),
            source_sha=str(value["source_sha"]),
            proof_receipt_digest=str(value["proof_receipt_digest"]),
            observed_at=float(value["observed_at"]),
            mac=str(value["mac"]),
        )


class ExecutionObserver:
    """Create and verify evidence bindings without creating execution permission."""

    def __init__(self, secret: bytes = LOCAL_OBSERVATION_SECRET):
        if not secret:
            raise ValueError("secret required")
        self._secret = secret

    def record(
        self,
        repository: str,
        source_sha: str,
        proof_receipt_digest: str,
        *,
        observed_at: float | None = None,
    ) -> ExecutionObservation:
        timestamp = time.time() if observed_at is None else float(observed_at)
        body = f"{repository}|{source_sha}|{proof_receipt_digest}|{timestamp}"
        mac = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return ExecutionObservation(
            repository=repository,
            source_sha=source_sha,
            proof_receipt_digest=proof_receipt_digest,
            observed_at=timestamp,
            mac=mac,
        )

    def verify(self, observation: ExecutionObservation) -> Mapping[str, Any]:
        body = (
            f"{observation.repository}|{observation.source_sha}|"
            f"{observation.proof_receipt_digest}|{observation.observed_at}"
        )
        expected = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(expected, observation.mac)
        return {
            "valid": valid,
            "issues": [] if valid else ["BAD_MAC"],
            "execution_permission": "NOT_EVALUATED",
            "stop_condition_created": False,
        }


def verify_bound_observation(
    observation_dict: Mapping[str, Any],
    proof_receipt_path: str | bytes | Path,
    *,
    secret: bytes = LOCAL_OBSERVATION_SECRET,
) -> Mapping[str, Any]:
    """Verify source/proof identity and return telemetry only.

    A failed verification lowers evidence certainty. It does not veto execution.
    """
    path = Path(proof_receipt_path)
    issues: list[str] = []
    proof: Mapping[str, Any] = {}

    if not path.is_file():
        issues.append("PROOF_RECEIPT_MISSING")
    else:
        proof_bytes = path.read_bytes()
        file_digest = hashlib.sha256(proof_bytes).hexdigest()
        try:
            loaded = json.loads(proof_bytes.decode())
            proof = loaded if isinstance(loaded, Mapping) else {}
        except Exception:
            issues.append("PROOF_RECEIPT_INVALID_JSON")

        if observation_dict.get("proof_receipt_digest") != file_digest:
            issues.append("PROOF_DIGEST_MISMATCH")
        if observation_dict.get("source_sha") != proof.get("source_sha"):
            issues.append("SOURCE_SHA_MISMATCH")

    try:
        observation = ExecutionObservation.from_dict(observation_dict)
        signature = ExecutionObserver(secret).verify(observation)
        issues.extend(str(item) for item in signature.get("issues", []))
    except Exception:
        issues.append("OBSERVATION_MALFORMED")

    return {
        "valid": not issues,
        "issues": sorted(set(issues)),
        "execution_permission": "NOT_EVALUATED",
        "stop_condition_created": False,
    }
