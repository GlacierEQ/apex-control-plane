from __future__ import annotations

import copy
import json
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
    validate_bundle,
    validate_case_graph,
)


def graph() -> dict:
    return {
        "schema": "casebuilder4000.case-graph.v2",
        "case_id": "CASE-001",
        "nodes": [
            {"id": "CASE-001", "type": "CASE", "label": "Case"},
            {"id": "ACT-1", "type": "ACTOR", "label": "Actor One"},
            {
                "id": "EVT-1",
                "type": "EVENT",
                "label": "Detention",
                "start": "2026-08-14T20:14:00-10:00",
            },
            {"id": "FCT-1", "type": "FACT", "label": "Control over departure", "state": "closed"},
            {
                "id": "ELM-1",
                "type": "ELEMENT",
                "label": "lawful privilege",
                "state": "missing",
            },
            {
                "id": "ALG-1",
                "type": "ALLEGATION",
                "label": "Detention claim",
                "status": "element_mapped",
                "tier": 2,
                "score": 68.0,
            },
            {
                "id": "CON-1",
                "type": "CONTRADICTION",
                "label": "Voluntary versus restrained",
                "status": "open",
            },
            {
                "id": "HRM-1",
                "type": "HARM",
                "label": "Loss of liberty",
                "category": "loss_of_liberty",
            },
            {
                "id": "DSC-1",
                "type": "DISCOVERY_TARGET",
                "label": "Authority record",
                "priority": 96,
            },
            {
                "id": "ACP-1",
                "type": "ACCOUNTABILITY_PATH",
                "label": "Civil path",
                "kind": "civil",
            },
            {
                "id": "XEX-1",
                "type": "CROSS_EXAM",
                "label": "Lock voluntary characterization",
            },
        ],
        "edges": [
            {"from": "CASE-001", "to": "ACT-1", "type": "HAS_ACTOR"},
            {"from": "CASE-001", "to": "EVT-1", "type": "HAS_EVENT"},
            {"from": "EVT-1", "to": "FCT-1", "type": "CONTAINS_FACT"},
            {"from": "FCT-1", "to": "ELM-1", "type": "SUPPORTS_ELEMENT"},
            {"from": "ELM-1", "to": "ALG-1", "type": "ELEMENT_OF"},
            {"from": "CON-1", "to": "ALG-1", "type": "TESTS"},
            {"from": "ALG-1", "to": "HRM-1", "type": "CAUSES"},
            {"from": "ALG-1", "to": "DSC-1", "type": "DEVELOPS_THROUGH"},
            {"from": "ALG-1", "to": "ACP-1", "type": "SUPPORTS_ACCOUNTABILITY"},
            {"from": "ALG-1", "to": "XEX-1", "type": "GENERATES_CROSS_EXAM"},
        ],
    }


def conversion() -> dict:
    base = {
        "allegation_id": "ALG-1",
        "title": "Detention claim",
    }
    return {
        "schema": "casebuilder4000.conversion-bundle.v2",
        "case_id": "CASE-001",
        "pleading_map": [base],
        "motion_map": [base],
        "referral_map": [base],
        "discovery_map": [{"allegation_id": "ALG-1", "id": "DSC-1"}],
        "cross_exam_map": [{"allegation_id": "ALG-1", "id": "XEX-1"}],
    }


def build_receipt() -> dict:
    return {
        "schema": "casebuilder4000.build-receipt.v2",
        "case_id": "CASE-001",
        "validation_errors": [],
    }


def test_graph_contract_rejects_dangling_lineage() -> None:
    broken = copy.deepcopy(graph())
    broken["edges"].append({"from": "FCT-NOT-THERE", "to": "ALG-1", "type": "SUPPORTS"})
    with pytest.raises(JackCasebuilderContractError, match="missing source node"):
        validate_case_graph(broken)


def test_bundle_binds_graph_conversion_and_build_receipt() -> None:
    validated = validate_bundle(
        graph(),
        conversion=conversion(),
        build_receipt=build_receipt(),
    )
    assert validated["case_id"] == "CASE-001"
    assert validated["node_count"] == len(graph()["nodes"])
    assert len(validated["graph_sha256"]) == 64


def test_execution_queue_routes_each_case_object_to_specialized_capability() -> None:
    jobs = compile_jack_execution_queue(graph(), conversion=conversion())
    capabilities = {job.capability for job in jobs}

    assert {
        "legal_discovery",
        "legal_element_development",
        "contradiction_resolution",
        "allegation_hardening",
        "damage_development",
        "accountability_projection",
        "cross_exam_generation",
        "pleading_projection",
        "motion_projection",
        "referral_projection",
        "discovery_projection",
        "cross_exam_projection",
    } <= capabilities
    assert all(job.external_action_authorized is False for job in jobs)


def test_control_plane_dispatches_internal_case_work_by_capability() -> None:
    jobs = compile_jack_execution_queue(graph(), conversion=conversion())
    plane = ControlPlane()
    for capability in {job.capability for job in jobs}:
        plane.register(
            Worker(
                id=f"worker-{capability}",
                capacity=10,
                capabilities=frozenset({capability}),
            )
        )

    receipts = dispatch_jack_queue(plane, jobs)

    assert len(receipts) == len(jobs)
    assert all(row["dispatch"]["ok"] is True for row in receipts)
    assert all(row["external_action_authorized"] is False for row in receipts)


def test_control_receipt_is_deterministic_and_source_bound() -> None:
    first = build_control_plane_receipt(
        graph(),
        conversion=conversion(),
        build_receipt=build_receipt(),
    )
    second = build_control_plane_receipt(
        graph(),
        conversion=conversion(),
        build_receipt=build_receipt(),
    )

    assert first == second
    assert len(first["receipt_sha256"]) == 64
    assert first["external_action_authorized"] is False
    assert first["job_count"] > 0



def test_live_legal_graph_vocabulary_is_lossless_and_actionable() -> None:
    expanded = graph()
    legacy_nodes = [
        {"id": "DKT-10", "type": "DOCKET", "label": "Docket 10"},
        {
            "id": "EVD-1",
            "type": "EVIDENCE",
            "label": "Derivative evidence",
            "fact_state": "SOURCE_BOUND_DERIVATIVE",
        },
        {"id": "AUTH-1", "type": "AUTHORITY", "label": "Controlling authority"},
        {"id": "ATK-1", "type": "ATTACK", "label": "Attack lane"},
        {"id": "DEF-1", "type": "DEFENSE", "label": "Best defense"},
        {"id": "REB-1", "type": "REBUTTAL", "label": "Rebuttal"},
        {"id": "CAU-1", "type": "CAUSATION", "label": "Causation chain"},
        {"id": "REM-1", "type": "REMEDY", "label": "Relief path"},
        {"id": "COM-1", "type": "COMMUNICATION", "label": "Notice communication"},
    ]
    expanded["nodes"].extend(legacy_nodes)
    for node in legacy_nodes:
        expanded["edges"].append(
            {"from": "CASE-001", "to": node["id"], "type": "PRESERVES"}
        )

    validate_case_graph(expanded)
    jobs = compile_jack_execution_queue(expanded)
    capabilities = {job.capability for job in jobs}

    assert {
        "evidence_integrity",
        "legal_authority_mapping",
        "legal_attack_development",
        "defense_testing",
        "rebuttal_hardening",
        "causation_development",
        "remedy_projection",
    } <= capabilities

def test_execution_queue_has_no_fixed_case_object_ceiling() -> None:
    expanded = graph()
    for index in range(120):
        node_id = f"DSC-{index + 100:03d}"
        expanded["nodes"].append(
            {
                "id": node_id,
                "type": "DISCOVERY_TARGET",
                "label": f"Record target {index:03d}",
                "priority": 80,
            }
        )
        expanded["edges"].append(
            {"from": "ALG-1", "to": node_id, "type": "DEVELOPS_THROUGH"}
        )

    jobs = compile_jack_execution_queue(expanded)
    discovery_jobs = [job for job in jobs if job.capability == "legal_discovery"]

    assert len(discovery_jobs) == 121
