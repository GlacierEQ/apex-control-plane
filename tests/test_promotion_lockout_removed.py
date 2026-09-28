"""Regression contract for retiring the legacy secret-bound promotion layer."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_secret_bound_promotion_artifacts_are_retired() -> None:
    assert not (ROOT / "src/promotion_authority.py").exists()
    assert not (ROOT / "machine/promotion_authority.json").exists()
    assert not (ROOT / "tests/test_promotion_authority.py").exists()


def test_receipt_proof_remains_non_authorizing() -> None:
    assert (ROOT / "machine/proof_receipt.json").is_file()
    state = json.loads((ROOT / "machine/excellence-state.json").read_text())
    assert "AUTHORITY_BOUND" not in state["gates"]
    assert state["gates"]["PROMOTION_LOCKOUT_REMOVED"]["status"] == "PASS"
    assert state["state"] == "DISCOVERED"
