from __future__ import annotations

import copy
from pathlib import Path

import pytest

from legal_case_control_plane import (
    LegalCaseControlPlaneError,
    load_case_policy_for_case,
    validate_case_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def test_1fdv_jack_policy_is_runtime_resolvable_and_active():
    policy = load_case_policy_for_case(ROOT / "config", "1FDV-23-0001009")
    assert policy["status"] == "ACTIVE"
    assert policy["engine"] == "JACK_THE_RIPPER_CASEBUILDER"
    assert policy["authority"]["case_state_repository"] == "GlacierEQ/apex-legal-case"
    assert policy["runtime_controls"]["event_date_law_required"] is True
    assert policy["runtime_controls"]["adverse_evidence_required_before_promotion"] is True
    assert policy["runtime_controls"]["filing_state_requires_external_receipt"] is True
    assert policy["runtime_controls"]["substantial_run_requires_write_and_readback"] is True
    assert policy["runtime_controls"]["reconstruct_from_scratch"] is False
    assert policy["peer_mesh"]["master_controller"] is False
    assert policy["peer_mesh"]["failed_peer_blocks_only_dependent_work"] is True


def test_1fdv_jack_policy_preserves_required_quarantines():
    policy = load_case_policy_for_case(ROOT / "config", "1FDV-23-0001009")
    quarantine = {row["id"]: row for row in policy["quarantine"]}
    assert quarantine["JACK-Q-001"]["state"] == "QUARANTINED"
    assert quarantine["JACK-Q-002"]["state"] == "QUARANTINED"
    assert "Gonsalves" in quarantine["JACK-Q-001"]["reason"]
    assert "primary proof" in quarantine["JACK-Q-002"]["reason"]


def test_external_filing_receipt_gate_cannot_be_disabled():
    policy = load_case_policy_for_case(ROOT / "config", "1FDV-23-0001009")
    weakened = copy.deepcopy(policy)
    weakened["runtime_controls"]["filing_state_requires_external_receipt"] = False
    with pytest.raises(LegalCaseControlPlaneError, match="filing_state_requires_external_receipt"):
        validate_case_policy(weakened)


def test_write_readback_gate_cannot_be_disabled():
    policy = load_case_policy_for_case(ROOT / "config", "1FDV-23-0001009")
    weakened = copy.deepcopy(policy)
    weakened["runtime_controls"]["substantial_run_requires_write_and_readback"] = False
    with pytest.raises(LegalCaseControlPlaneError, match="substantial_run_requires_write_and_readback"):
        validate_case_policy(weakened)


def test_peer_mesh_cannot_be_promoted_to_master_controller():
    policy = load_case_policy_for_case(ROOT / "config", "1FDV-23-0001009")
    weakened = copy.deepcopy(policy)
    weakened["peer_mesh"]["master_controller"] = True
    with pytest.raises(LegalCaseControlPlaneError, match="master controller"):
        validate_case_policy(weakened)


def test_unknown_case_policy_fails_closed():
    with pytest.raises(LegalCaseControlPlaneError, match="no Jack Casebuilder runtime policy"):
        load_case_policy_for_case(ROOT / "config", "UNREGISTERED-CASE")
