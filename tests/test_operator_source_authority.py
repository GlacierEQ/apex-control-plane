from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.operator_source_authority import (
    OperatorSourceAuthorityError,
    enforce_operator_source_authority,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_operator_source_authority_contract_is_valid() -> None:
    policy = enforce_operator_source_authority()
    assert policy["personalization"]["highest_user_authority_layer"] is True
    assert policy["source_state"]["operator_words_are_source_state"] is True


def test_operator_source_authority_fails_closed_on_override(monkeypatch, tmp_path: Path) -> None:
    policy = json.loads(
        (ROOT / "config" / "operator_source_authority_contract.json").read_text(encoding="utf-8")
    )
    policy["personalization"]["summary_may_override"] = True
    policy_path = tmp_path / "operator_source_authority_contract.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    import src.operator_source_authority as module

    monkeypatch.setattr(module, "POLICY_PATH", policy_path)
    with pytest.raises(OperatorSourceAuthorityError, match="summary_may_override"):
        module.enforce_operator_source_authority()
