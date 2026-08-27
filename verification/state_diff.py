"""
APEX STATE DIFF & VERIFICATION ENGINE
Standard: Mathematical proof of mutation.
Enforces: mutation + readback + (expected delta == observed delta) == COMPLETE.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class VerificationResult:
    is_verified: bool
    expected_delta: Dict[str, Any]
    observed_delta: Dict[str, Any]
    discrepancies: list[str]
    verification_hash: str


class StateVerifier:
    """
    Validates that a physical mutation matches the exact expected change.
    Bars hallucinated completion.
    """

    @classmethod
    def verify_mutation(
        cls,
        expected_state: Dict[str, Any],
        readback_state: Dict[str, Any],
    ) -> VerificationResult:
        discrepancies = []

        for key, exp_val in expected_state.items():
            obs_val = readback_state.get(key)
            if obs_val != exp_val:
                discrepancies.append(
                    f"Mismatch on '{key}': expected '{exp_val}', observed '{obs_val}'"
                )

        is_verified = len(discrepancies) == 0

        # Compute deterministic verification hash
        v_raw = f"{is_verified}:{sorted(expected_state.items())}:{sorted(readback_state.items())}"
        v_hash = hashlib.sha256(v_raw.encode("utf-8")).hexdigest()

        return VerificationResult(
            is_verified=is_verified,
            expected_delta=expected_state,
            observed_delta=readback_state,
            discrepancies=discrepancies,
            verification_hash=v_hash,
        )
