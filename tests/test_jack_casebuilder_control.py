from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from control_plane import ControlPlane, Worker  # noqa: E402
from jack_casebuilder_control import (  # noqa: E402
    JackCasebuilderContractError,
    build_control_plane_receipt,
    compile_jack_execution_queue,
    dispatch_jack_queue,
    queue_to_impact_candidates,
    validate_bundle,
    validate_case_graph,
)


def graph() -> dict:
    return {
        "schema": "casebuilder4000.case-graph.v2",
        "case_id": "CASE-001",
        "nodes": [
            {"id": "CASE-001", "type": "CASE", "label": "Case"},
            {"id": "ELM-1", "type": "ELEMENT", "label": "lawful privilege", "state": "missing"},
            {"id": "ALG-1", "type": "ALLEGATION", "label": "Claim", "status": "element_mapped", "tier": 2},
            {"id": "CON-1", "type": "CONTRADICTION", "label": "Conflict", "status": "open"},
            {"id": "DSC-1", "type": "DISCOVERY_TARGET", "label": "Authority record", "priority": 96},
            {"id": "AUTH-1", "type": "AUTHORITY", "label": "Controlling authority"},
            {"id": "HRM-1", "type": "HARM", "label": "Loss of liberty"},
        ],
        "edges": [
            {"from": "CASE-001", "to": "ELM-1", "type": "HAS_ELEMENT"},
            {"from": "ELM-1", "to": "ALG-1", "type": "ELEMENT_OF"},
            {"from": "CON-1", "to": "ALG-1", "type": "TESTS"},
            {"from": "ALG-1", "to": "DSC-1", "type": "DEVELOPS_THROUGH"},
            {"from": "ALG-1", "to": "HRM-1", "type": "CAUSES"},
            {"from": "CASE-001", "to": "AUTH-1", "type": "HAS_AUTHORITY"},
        ],
    }


def conversion() -> dict:
    return {
        "schema": "casebuilder4000.conversion-bundle.v2",
        "case_id": "CASE-001",
        "pleading_map": [{"allegation_id": "ALG-1"}],
        "motion_map": [],
        "referral_map": [{"allegation_id": "ALG-1"}],
        "discovery_map": [{"id": "DSC-1"}],
        "cross_exam_map": [],
    }


def test_graph_rejects_dangling_lineage() -> None:
    broken = copy.deepcopy(graph())
    broken["edges"].append({"from": "MISSING", "to": "ALG-1", "type": "SUPPORTS"})
    with pytest.raises(JackCasebuilderContractError, match="missing source node"):
        validate_case_graph(broken)


def test_bundle_and_receipt_are_source_bound_and_deterministic() -> None:
    validated = validate_bundle(graph(), conversion=conversion())
    assert validated["case_id"] == "CASE-001"
    assert len(validated["graph_sha256"]) == 64
    first = build_control_plane_receipt(graph(), conversion=conversion())
    second = build_control_plane_receipt(graph(), conversion=conversion())
    assert first == second
    assert first["external_action_authorized"] is False
    assert len(first["receipt_sha256"]) == 64


def test_queue_routes_unresolved_objects_without_external_authority() -> None:
    jobs = compile_jack_execution_queue(graph(), conversion=conversion())
    capabilities = {job.capability for job in jobs}
    assert {
        "legal_discovery",
        "legal_element_development",
        "allegation_hardening",
        "contradiction_resolution",
        "legal_authority_mapping",
        "damage_development",
        "pleading_projection",
        "referral_projection",
        "discovery_projection",
    } <= capabilities
    assert all(job.external_action_authorized is False for job in jobs)


def test_queue_bridges_into_current_impact_selector_contract() -> None:
    jobs = compile_jack_execution_queue(graph())
    candidates = queue_to_impact_candidates(jobs)
    assert len(candidates) == len(jobs)
    assert all(candidate.operation_class == "CASE_EXECUTION" for candidate in candidates)
    assert all(candidate.evidence_refs for candidate in candidates)


def test_dispatch_is_internal_capability_routing_only() -> None:
    jobs = compile_jack_execution_queue(graph())
    plane = ControlPlane()
    for capability in {job.capability for job in jobs}:
        plane.register(Worker(id=f"worker-{capability}", capacity=10, capabilities=frozenset({capability})))
    receipts = dispatch_jack_queue(plane, jobs)
    assert len(receipts) == len(jobs)
    assert all(row["dispatch"]["ok"] is True for row in receipts)
    assert all(row["external_action_authorized"] is False for row in receipts)
