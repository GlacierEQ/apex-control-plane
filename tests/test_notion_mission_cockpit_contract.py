import json
from pathlib import Path

import pytest

from notion_mission_cockpit_contract import (
    CockpitContractError,
    build_projection_plan,
    load_contract,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[1]


def mission():
    return {
        "mission_id": "MIS-1",
        "objective": "Continue donor harvest",
        "status": "VERIFYING",
        "correlation_id": "RUN-1",
        "priority": "high",
        "repositories": ["GlacierEQ/apex-control-plane"],
        "created_at": "2026-09-25T00:00:00Z",
    }


def test_contract_preserves_donor_field_model_without_donor_authority():
    contract = load_contract(
        ROOT / "config" / "notion_mission_cockpit_projection.v1.json"
    )
    validate_contract(contract)
    assert contract["donor"]["branch"] == "feat/durable-workflow-machine"
    assert contract["donor"]["path"] == "adapters/notion/adapter.py"
    assert contract["semantics"]["authority"] == "projection_only"
    assert contract["semantics"]["provider_write_enabled"] is False
    assert contract["semantics"]["provider_receipt_required"] is True
    assert contract["semantics"]["mock_success_allowed"] is False
    assert contract["semantics"]["in_memory_readback_allowed"] is False
    assert contract["fields"]["Current Step"] == "current_step"
    assert contract["fields"]["Verified Mutations"] == "verified_mutations"
    assert contract["fields"]["Failed Mutations"] == "failed_mutations"
    assert contract["fields"]["Open Blocker"] == "open_blocker"
    assert contract["fields"]["Receipt"] == "receipt_id"


def test_plan_is_non_authorizing_and_never_claims_notion_sync():
    contract = load_contract(
        ROOT / "config" / "notion_mission_cockpit_projection.v1.json"
    )
    plan = build_projection_plan(
        mission(),
        current_step="donor_compare",
        verified_mutations=3,
        failed_mutations=1,
        open_blocker="notion write route disabled",
        receipt_id="receipt-123",
        worker="continuity-repair-peer",
        contract=contract,
    )
    assert plan["status"] == "PLANNED"
    assert plan["provider"] == "notion"
    assert plan["external_action_authorized"] is False
    assert "SYNCED" not in json.dumps(plan)
    assert plan["properties"]["Mission"] == "Continue donor harvest"
    assert plan["properties"]["Status"] == "VERIFYING"
    assert plan["properties"]["Run"] == "RUN-1"
    assert plan["properties"]["Current Step"] == "donor_compare"
    assert plan["properties"]["Verified Mutations"] == 3
    assert plan["properties"]["Failed Mutations"] == 1
    assert plan["properties"]["Open Blocker"] == "notion write route disabled"
    assert plan["properties"]["Receipt"] == "receipt-123"


def test_missing_mission_identity_is_rejected():
    contract = load_contract(
        ROOT / "config" / "notion_mission_cockpit_projection.v1.json"
    )
    bad = mission()
    bad["mission_id"] = ""
    with pytest.raises(CockpitContractError, match="mission_id"):
        build_projection_plan(
            bad,
            current_step="x",
            contract=contract,
        )
