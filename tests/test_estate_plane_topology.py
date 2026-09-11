from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "config/estate_plane_topology.json"


def topology() -> dict:
    return json.loads(TOPOLOGY.read_text(encoding="utf-8"))


def test_mission_plane_is_projection_not_universal_case_authority() -> None:
    cfg = topology()
    mission = cfg["planes"]["mission"]
    assert mission["role"] == "MISSION_DATA_AND_SUBSTANTIVE_OPERATIONAL_PROJECTION_PLANE"
    assert "projects_and_operates" in mission
    assert "owns" not in mission
    assert "source_bound_case_graph_authority" in mission["does_not_own"]
    assert "provider_native_evidence_bytes" in mission["does_not_own"]
    assert "operator_firsthand_testimony" in mission["does_not_own"]


def test_source_authority_remains_proposition_specific_and_polycentric() -> None:
    cfg = topology()
    authority = cfg["source_authority"]
    assert "operator_firsthand" in authority
    assert "case_repositories" in authority
    assert "provider_native_systems" in authority
    assert "evidence_artifacts" in authority
    assert "supabase_glaciereq" in authority
    assert "projection" in authority["supabase_glaciereq"].lower()


def test_cross_plane_rules_forbid_projection_authority_inversion() -> None:
    cfg = topology()
    rules = "\n".join(cfg["cross_plane_rules"])
    assert "projection or storage location does not displace" in rules
    assert "No source-bearing case repository is replaced by a Supabase projection" in rules
    assert "No provider-native source is replaced by a Supabase projection" in rules
