"""CaseBuilder V2 graph validation and bounded internal JACK work compilation.

This module complements ``jack_casebuilder_fabric``. The fabric reconciles peer
projections; this module validates one source-bound CaseBuilder graph and compiles
its unresolved objects into internal work. It never authorizes an external
provider mutation.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol

try:
    from .continuous_impact_selection import ImpactCandidate
except ImportError:
    from continuous_impact_selection import ImpactCandidate

CASE_GRAPH_SCHEMA = "casebuilder4000.case-graph.v2"
CONVERSION_SCHEMA = "casebuilder4000.conversion-bundle.v2"
BUILD_RECEIPT_SCHEMA = "casebuilder4000.build-receipt.v2"

ALLOWED_NODE_TYPES = frozenset({
    "CASE", "SOURCE", "SOURCE_ROOT", "DOCKET", "ACTOR", "EVENT",
    "COMMUNICATION", "EVIDENCE", "AUTHORITY", "FACT", "ELEMENT",
    "ALLEGATION", "THEORY", "CONTRADICTION", "KNOWLEDGE", "PATTERN",
    "DEFENSE", "REBUTTAL", "CAUSATION", "HARM", "DISCOVERY_TARGET",
    "REMEDY", "ACCOUNTABILITY_PATH", "ATTACK", "DEADLINE",
    "FILING_PARAGRAPH", "CROSS_EXAM",
})


class JackCasebuilderContractError(ValueError):
    pass


class DispatchPlane(Protocol):
    def dispatch(self, job_cost: int = 1, capability: str | None = None) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class JackJob:
    job_id: str
    case_id: str
    object_id: str
    object_type: str
    capability: str
    priority: int
    action: str
    reason: str
    external_action_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "case_id": self.case_id,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "capability": self.capability,
            "priority": self.priority,
            "action": self.action,
            "reason": self.reason,
            "external_action_authorized": False,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode()).hexdigest()


def _priority(value: Any, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def validate_case_graph(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if payload.get("schema") != CASE_GRAPH_SCHEMA:
        raise JackCasebuilderContractError(f"case graph schema must be {CASE_GRAPH_SCHEMA}")
    case_id = str(payload.get("case_id") or "").strip()
    nodes_raw = payload.get("nodes")
    edges_raw = payload.get("edges")
    if not case_id or not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        raise JackCasebuilderContractError("case graph requires case_id, nodes, and edges")

    nodes: dict[str, Mapping[str, Any]] = {}
    case_nodes = 0
    for index, row in enumerate(nodes_raw):
        if not isinstance(row, Mapping):
            raise JackCasebuilderContractError(f"nodes[{index}] must be an object")
        node_id = str(row.get("id") or "").strip()
        node_type = str(row.get("type") or "").strip()
        label = str(row.get("label") or "").strip()
        if not node_id or not label or node_type not in ALLOWED_NODE_TYPES:
            raise JackCasebuilderContractError(f"invalid nodes[{index}]")
        if node_id in nodes:
            raise JackCasebuilderContractError(f"duplicate case graph node: {node_id}")
        nodes[node_id] = row
        if node_type == "CASE":
            case_nodes += 1
            if node_id != case_id:
                raise JackCasebuilderContractError("CASE node id must equal case_id")
    if case_nodes != 1:
        raise JackCasebuilderContractError("case graph requires exactly one CASE node")

    for index, edge in enumerate(edges_raw):
        if not isinstance(edge, Mapping):
            raise JackCasebuilderContractError(f"edges[{index}] must be an object")
        source = str(edge.get("from") or "").strip()
        target = str(edge.get("to") or "").strip()
        relation = str(edge.get("type") or "").strip()
        if not source or not target or not relation:
            raise JackCasebuilderContractError(f"edges[{index}] requires from/to/type")
        if source not in nodes:
            raise JackCasebuilderContractError(f"edges[{index}] references missing source node {source}")
        if target not in nodes:
            raise JackCasebuilderContractError(f"edges[{index}] references missing target node {target}")
    return nodes


def validate_bundle(
    graph: Mapping[str, Any], *, conversion: Mapping[str, Any] | None = None,
    build_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = validate_case_graph(graph)
    case_id = str(graph["case_id"])
    if conversion is not None:
        if conversion.get("schema") != CONVERSION_SCHEMA or conversion.get("case_id") != case_id:
            raise JackCasebuilderContractError("conversion bundle does not match case graph")
    if build_receipt is not None:
        if build_receipt.get("schema") != BUILD_RECEIPT_SCHEMA or build_receipt.get("case_id") != case_id:
            raise JackCasebuilderContractError("build receipt does not match case graph")
        if build_receipt.get("validation_errors") not in (None, []):
            raise JackCasebuilderContractError("build receipt contains validation errors")
    return {
        "case_id": case_id,
        "node_count": len(nodes),
        "edge_count": len(graph.get("edges", [])),
        "graph_sha256": _digest(graph),
        "conversion_sha256": _digest(conversion) if conversion is not None else None,
        "build_receipt_sha256": _digest(build_receipt) if build_receipt is not None else None,
    }


_NODE_RULES: dict[str, tuple[str, int, str]] = {
    "DISCOVERY_TARGET": ("legal_discovery", 90, "develop_targeted_record_acquisition"),
    "CONTRADICTION": ("contradiction_resolution", 90, "resolve_material_conflict"),
    "AUTHORITY": ("legal_authority_mapping", 82, "map_authority_to_elements_and_dates"),
    "ATTACK": ("legal_attack_development", 78, "bind_attack_to_supported_claims"),
    "DEFENSE": ("defense_testing", 84, "attack_strongest_defense"),
    "REBUTTAL": ("rebuttal_hardening", 82, "source_lock_rebuttal"),
    "CAUSATION": ("causation_development", 80, "trace_act_to_harm"),
    "REMEDY": ("remedy_projection", 74, "map_remedy_prerequisites"),
    "DEADLINE": ("deadline_review", 98, "verify_deadline_and_required_action"),
    "HARM": ("damage_development", 70, "trace_causation_amount_and_support"),
    "ACCOUNTABILITY_PATH": ("accountability_projection", 75, "map_accountability_path"),
    "CROSS_EXAM": ("cross_exam_generation", 68, "compile_source_locked_questions"),
}


def compile_jack_execution_queue(
    graph: Mapping[str, Any], *, conversion: Mapping[str, Any] | None = None,
) -> list[JackJob]:
    nodes = validate_case_graph(graph)
    case_id = str(graph["case_id"])
    jobs: dict[str, JackJob] = {}

    def add(node_id: str, node_type: str, capability: str, priority: int, action: str, reason: str) -> None:
        job = JackJob(
            job_id=f"JACK::{case_id}::{capability}::{node_id}", case_id=case_id,
            object_id=node_id, object_type=node_type, capability=capability,
            priority=_priority(priority, 50), action=action, reason=reason,
        )
        prior = jobs.get(job.job_id)
        if prior is None or job.priority > prior.priority:
            jobs[job.job_id] = job

    for node_id, node in nodes.items():
        node_type = str(node["type"])
        label = str(node.get("label") or node_id)
        if node_type == "ELEMENT" and str(node.get("state") or "").casefold() in {"missing", "disputed", "legal_defect"}:
            state = str(node.get("state")).casefold()
            add(node_id, node_type, "legal_element_development", 100 if state == "legal_defect" else 95, "resolve_element_support_or_defect", state)
        elif node_type == "ALLEGATION":
            status = str(node.get("status") or "").casefold()
            tier = _priority(node.get("tier"), 5)
            if status in {"raw", "structured", "sourced", "corroborated", "element_mapped"}:
                add(node_id, node_type, "allegation_hardening", 92 if tier <= 2 else 82, "run_proof_stack_and_gap_hardening", status)
            elif status in {"defense_tested", "hardened"}:
                add(node_id, node_type, "legal_conversion", 88 if tier <= 2 else 76, "convert_hardened_allegation", status)
        elif node_type in {"EVIDENCE", "SOURCE", "SOURCE_ROOT"}:
            state = str(node.get("fact_state") or "").casefold()
            if any(token in state for token in ("unresolved", "contradict", "derivative")):
                add(node_id, node_type, "evidence_integrity", 86, "resolve_source_provenance_or_conflict", state)
        elif node_type == "CONTRADICTION" and str(node.get("status") or "open").casefold() in {"resolved", "immaterial", "closed"}:
            continue
        elif node_type in _NODE_RULES:
            capability, priority, action = _NODE_RULES[node_type]
            add(node_id, node_type, capability, _priority(node.get("priority"), priority), action, label)

    if conversion is not None:
        validate_bundle(graph, conversion=conversion)
        for name, capability, priority in (
            ("pleading_map", "pleading_projection", 86),
            ("motion_map", "motion_projection", 84),
            ("referral_map", "referral_projection", 80),
            ("discovery_map", "discovery_projection", 88),
            ("cross_exam_map", "cross_exam_projection", 72),
        ):
            rows = conversion.get(name, [])
            if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
                raise JackCasebuilderContractError(f"{name} must be an array of objects")
            for index, row in enumerate(rows):
                object_id = str(row.get("allegation_id") or row.get("id") or f"{name}-{index:04d}")
                add(object_id, "CONVERSION", capability, priority, f"materialize_{name.removesuffix('_map')}", name)

    return sorted(jobs.values(), key=lambda job: (-job.priority, job.capability, job.object_id))


def queue_to_impact_candidates(jobs: Sequence[JackJob]) -> list[ImpactCandidate]:
    """Bridge validated CaseBuilder work into the current impact selector."""
    return [
        ImpactCandidate(
            candidate_id=job.job_id,
            operation=job.action,
            operation_class="CASE_EXECUTION",
            expected_delta=job.reason,
            features={
                "mission_advancement": job.priority / 100.0,
                "state_change_value": job.priority / 100.0,
                "execution_proximity": 1.0,
                "prior_gain_preservation": 1.0,
                "reversibility": 1.0,
                "failure_risk": 0.1,
            },
            evidence_refs=(f"casebuilder:{job.case_id}:{job.object_id}",),
            metadata={"capability": job.capability, "object_type": job.object_type},
        )
        for job in jobs
    ]


def dispatch_jack_queue(control_plane: DispatchPlane, jobs: Sequence[JackJob]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for job in jobs:
        receipts.append({
            "job": job.as_dict(),
            "dispatch": dict(control_plane.dispatch(1, capability=job.capability)),
            "external_action_authorized": False,
        })
    return receipts


def build_control_plane_receipt(
    graph: Mapping[str, Any], *, conversion: Mapping[str, Any] | None = None,
    build_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validated = validate_bundle(graph, conversion=conversion, build_receipt=build_receipt)
    queue = compile_jack_execution_queue(graph, conversion=conversion)
    body = {
        "schema": "glaciereq.jack-casebuilder-control-receipt.v2",
        **validated,
        "job_count": len(queue),
        "capabilities": sorted({job.capability for job in queue}),
        "jobs": [job.as_dict() for job in queue],
        "external_action_authorized": False,
    }
    return {**body, "receipt_sha256": _digest(body)}
